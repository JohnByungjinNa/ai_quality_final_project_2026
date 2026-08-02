import json
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.services import voc_quality_service
from dashboard.services.voc_quality_state_model import build_verification_scope


def _configure_store(monkeypatch, tmp_path):
    report_service = voc_quality_service.voc_report_service
    store = report_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "voc_quality_runs")
    store._ACTIVE_RUN_IDS.clear()
    return report_service, store


def _start_run(store, case_ids, *, run_type="BATCH", run_metadata=None):
    return store.start_voc_run(
        run_type=run_type,
        selected_case_ids=case_ids,
        suite_id="VOC-QA-35",
        catalog_version="1.0",
        test_case_hash="same-test-hash",
        rubric_versions={"internal_pipeline": {"version": "1.0", "sha256": "same-rubric"}},
        model_snapshot={"summary": {"provider": "openai", "model": "test"}},
        judge_enabled=False,
        environment_fingerprint={"fingerprint_sha256": "env"},
        run_metadata=run_metadata or {},
    )


def _complete(store, run, statuses):
    results = []
    for case_id, status in statuses.items():
        store.save_case_artifacts(
            run["run_id"],
            case_id,
            pipeline_result={"execution": {"result": {"summary": "요약", "policy": "개선안"}}},
            trace={"trace_id": f"trace-{case_id}", "events": [{"status": "success"}]},
            rule_result={"status": status},
        )
        results.append({"case_id": case_id, "status": status, "attempt_count": 1})
    store.complete_voc_run(run["run_id"], results, lifecycle_status="COMPLETED")


def test_report_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_quality_report_app.py", default_timeout=20)
    app.run()

    assert not app.exception
    assert app.radio[0].options == ["최종 품질 보고서", "증적 초안"]
    assert app.segmented_control[0].options == list(voc_quality_service.REPORT_CATEGORIES)


def test_report_generation_keeps_txt_xml_html_counts_consistent(monkeypatch, tmp_path):
    report_service, store = _configure_store(monkeypatch, tmp_path)
    statuses = {"TC-01": "PASS", "TC-02": "ERROR", "TC-03": "REVIEW_REQUIRED"}
    run = _start_run(store, list(statuses))
    _complete(store, run, statuses)

    generated = report_service.generate_quality_report_evidence(run["run_id"])
    model = generated["model"]
    xml_root = ET.fromstring(generated["contents"]["xml"])

    assert model["report_state"] == "EVIDENCE_DRAFT"
    assert model["release_decision"] == "NOT_APPROVED"
    assert model["run"]["counts"] == {
        "PASS": 1, "FAIL": 0, "ERROR": 1, "REVIEW_REQUIRED": 1, "NOT_RUN": 0
    }
    assert "PASS 1" in generated["contents"]["txt"]
    assert "NOT_VERIFIED" in generated["contents"]["html"]
    assert xml_root.attrib == {
        "name": "VOC Quality Evidence",
        "tests": "3",
        "failures": "0",
        "errors": "1",
        "skipped": "1",
        "timestamp": model["generated_at"],
    }
    for name in ("result.txt", "junit.xml", "report.html", "report_model.json", "report_manifest.json"):
        assert (Path(run["run_dir"]) / "evidence" / name).is_file()
    manifest = json.loads((Path(run["run_dir"]) / "evidence" / "report_manifest.json").read_text(encoding="utf-8"))
    assert manifest["shared_counts"] == model["run"]["counts"]
    for key in ("txt", "xml", "html"):
        path = Path(run["run_dir"]) / "evidence" / manifest["files"][key]["name"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["files"][key]["sha256"]


def test_33_2_to_35_claim_requires_matching_full_runs_and_defect_links(monkeypatch, tmp_path):
    report_service, store = _configure_store(monkeypatch, tmp_path)
    catalog = report_service._catalog()
    case_ids = [item["case_id"] for item in catalog["cases"]]
    baseline_statuses = {case_id: "PASS" for case_id in case_ids}
    baseline_statuses[case_ids[-2]] = "FAIL"
    baseline_statuses[case_ids[-1]] = "FAIL"
    baseline = _start_run(store, case_ids, run_type="BASELINE")
    _complete(store, baseline, baseline_statuses)
    store._atomic_write_json(
        Path(baseline["run_dir"]) / "defects.json",
        {
            "run_id": baseline["run_id"],
            "defects": [
                {"candidate_key": "branch_interface_error"},
                {"candidate_key": "api_429_rate_limit"},
            ],
        },
    )
    final = _start_run(store, case_ids)
    _complete(store, final, {case_id: "PASS" for case_id in case_ids})

    verified = report_service.build_quality_report_model(final["run_id"], baseline["run_id"])
    unlinked = report_service.build_quality_report_model(final["run_id"])

    assert verified["claims"]["baseline"]["verified"] is True
    assert verified["claims"]["final"]["verified"] is True
    assert verified["claims"]["improvement_verified"] is True
    assert verified["release_decision"] == "NOT_APPROVED"
    assert unlinked["claims"]["improvement_verified"] is False


def test_formal_report_uses_executable_scope_and_approved_followup_cases(monkeypatch, tmp_path):
    report_service, store = _configure_store(monkeypatch, tmp_path)
    monkeypatch.setattr(report_service.voc_defect_service, "list_defects", lambda: [])
    catalog = report_service._catalog()
    case_ids = [item["case_id"] for item in catalog["cases"]]
    scope = build_verification_scope(catalog["cases"], case_ids)
    executable_ids = set(scope["executable_case_ids"])
    pending_ids = set(scope["pending_case_ids"])
    run = _start_run(store, case_ids, run_metadata={"verification_scope": scope})
    results = []

    for case_id in case_ids:
        if case_id in executable_ids:
            store.save_case_artifacts(
                run["run_id"],
                case_id,
                pipeline_result={"execution": {"result": {"summary": "요약", "policy": "개선안"}}},
                trace={"trace_id": f"trace-{case_id}", "events": [{"status": "success"}]},
                rule_result={"status": "PASS"},
                judge_result={"decision": "PASS", "status": "PASS", "total_score": 90},
            )
            results.append(
                {
                    "case_id": case_id,
                    "status": "PASS",
                    "attempt_count": 1,
                    "judge_status": "PASS",
                    "judge_score": 90,
                }
            )
        else:
            store.save_case_artifacts(
                run["run_id"],
                case_id,
                pipeline_result={"execution": {"result": {}, "message": "후속 구현 계획 승인"}},
                trace={"trace_id": "", "events": []},
                rule_result={"status": "NOT_RUN"},
                judge_result={"decision": "NOT_RUN", "status": "NOT_RUN", "message": "후속 구현 Case"},
            )
            results.append({"case_id": case_id, "status": "NOT_RUN", "attempt_count": 0, "judge_status": "NOT_RUN"})

    store.complete_voc_run(run["run_id"], results, lifecycle_status="COMPLETED")
    for case_id in sorted(executable_ids):
        store.save_validity_evaluation(
            run["run_id"],
            case_id,
            {
                "decision": "AI_PASS",
                "status": "AI_PASS",
                "workflow_state": "BUSINESS_APPROVED",
                "formal_approval": True,
                "total_score": 92,
                "immediate_hold_rules_triggered": [],
            },
        )

    model = report_service.build_quality_report_model(run["run_id"])

    assert len(executable_ids) == 26
    assert len(pending_ids) == 9
    assert model["release_decision"] == "FORMAL_APPROVED"
    assert model["release_scope"]["executable_pass_ready"] is True
    assert model["release_scope"]["pending_plan_approved"] is True
    assert model["release_scope"]["judge_pass_ready"] is True
    assert model["release_scope"]["validity_approval_ready"] is True
    assert model["integrity"]["ok"] is True
