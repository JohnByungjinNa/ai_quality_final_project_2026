import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.services import voc_acceptance_service


def _report_model(*, formal=False):
    pass_count = 18 if formal else 1
    review_count = 8 if formal else 23
    error_count = 0 if formal else 2
    judge_count = 18 if formal else 1
    validity = {"BUSINESS_APPROVED": 18} if formal else {"REVISION_REQUIRED": 1}
    release_scope = {
        "basis": "VOC 개선 Case PASS·승인 + 장애 검증 실행 확인 + 후속 구현 Case 승인",
        "catalog_total_cases": 35,
        "selected_count": 35,
        "executable_count": 26,
        "voc_count": 18,
        "fault_count": 8,
        "judge_required_count": 18,
        "validity_required_count": 18,
        "pending_count": 9,
        "executable_counts": {
            "PASS": pass_count,
            "FAIL": 0,
            "ERROR": error_count,
            "REVIEW_REQUIRED": review_count,
            "NOT_RUN": 0,
        },
        "voc_counts": {
            "PASS": pass_count,
            "FAIL": 0,
            "ERROR": error_count,
            "REVIEW_REQUIRED": 0 if formal else 15,
            "NOT_RUN": 0,
        },
        "fault_counts": {
            "PASS": 0,
            "FAIL": 0,
            "ERROR": 0,
            "REVIEW_REQUIRED": 8 if formal else 6,
            "NOT_RUN": 0 if formal else 2,
        },
        "pending_counts": {
            "PASS": 0,
            "FAIL": 0,
            "ERROR": 0,
            "REVIEW_REQUIRED": 0,
            "NOT_RUN": 9,
        },
        "executable_judge_counts": {"PASS": judge_count},
        "executable_validity_counts": validity,
        "linked_retest_evidence": [],
        "linked_retest_count": 0,
        "full_catalog_selected": True,
        "executable_pass_ready": False,
        "voc_pass_ready": formal,
        "fault_execution_ready": formal,
        "pending_plan_approved": True,
        "judge_pass_ready": formal,
        "validity_approval_ready": formal,
        "release_scope_ready": formal,
        "pending_policy": "후속 구현 Case는 카탈로그에 DEFINED로 승인된 항목이며 이번 회차에서는 NOT_RUN이 정상 상태입니다.",
    }
    return {
        "report_id": "VOC-REPORT-RUN-TEST",
        "release_decision": "FORMAL_APPROVED" if formal else "NOT_APPROVED",
        "run": {
            "selected_count": 35,
            "counts": {
                "PASS": pass_count,
                "FAIL": 0,
                "ERROR": error_count,
                "REVIEW_REQUIRED": review_count,
                "NOT_RUN": 0 if formal else 9,
            },
        },
        "integrity": {"ok": True, "errors": []},
        "claims": {
            "improvement_verified": formal,
            "claim_text": "실행 가능 Case PASS + 후속 구현 Case 승인",
        },
        "evaluation": {
            "judge_evaluated": judge_count,
            "judge_counts": {"PASS": judge_count},
            "validity_evaluated": sum(validity.values()),
            "validity_counts": validity,
            "trace_cases": 26,
            "trace_events": 180,
        },
        "defects": [] if formal else [
            {"defect_id": "VOC-DEF-1", "severity": "HIGH", "status": "OPEN", "evidence_status": "CONFIRMED"}
        ],
        "risks": [] if formal else [
            {"level": "HIGH", "risk": "최종 35 PASS 미충족", "action": "재시험"}
        ],
        "verification_scope": {
            "catalog_total_cases": 35,
            "selected_count": 35,
            "executable_count": 26,
            "pending_count": 9,
        },
        "release_scope": release_scope,
    }


def _patch_sources(monkeypatch, model):
    monkeypatch.setattr(
        voc_acceptance_service.voc_report_service,
        "build_quality_report_model",
        lambda *_args, **_kwargs: model,
    )
    monkeypatch.setattr(
        voc_acceptance_service.voc_run_store,
        "list_voc_runs",
        lambda **_kwargs: [
            {"run_id": "RUN-20260716-000000-000000-aaaa", "status": "COMPLETED", "selected_count": 35, "run_type": "BATCH"},
            {"run_id": "RUN-20260716-000001-000001-bbbb", "status": "COMPLETED", "selected_count": 1, "run_type": "MANUAL"},
            {"run_id": "RUN-20260716-000002-000002-cccc", "status": "COMPLETED", "selected_count": 1, "run_type": "RETEST"},
        ],
    )
    monkeypatch.setattr(voc_acceptance_service.voc_defect_service, "list_defects", lambda: model["defects"])


def test_acceptance_gate_holds_unproven_release(monkeypatch):
    model = _report_model(formal=False)
    _patch_sources(monkeypatch, model)

    snapshot = voc_acceptance_service.build_acceptance_snapshot(
        "RUN-20260716-000000-000000-aaaa",
        runtime={"ok": True},
        agents={"all_running": True, "running": 6, "total": 6},
        verification={"regression_ok": True, "regression_summary": "신규 실패 0건", "secret_pattern_count": 0},
    )

    assert snapshot["decision"] == "HOLD"
    assert snapshot["user_signoff"] == "PENDING"
    assert {item["gate_id"] for item in snapshot["gates"] if item["status"] == "HOLD"} >= {
        "voc_pipeline", "fault_execution", "judge", "validity", "defects"
    }
    assert snapshot["quantitative"]["cost_krw"] == "NOT_AVAILABLE"
    assert voc_acceptance_service.latest_full_run_id() == "RUN-20260716-000000-000000-aaaa"


def test_acceptance_is_ready_for_uat_only_when_every_gate_passes(monkeypatch):
    model = _report_model(formal=True)
    _patch_sources(monkeypatch, model)

    snapshot = voc_acceptance_service.build_acceptance_snapshot(
        "RUN-20260716-000000-000000-aaaa",
        runtime={"ok": True},
        agents={"all_running": True, "running": 6, "total": 6},
        verification={"regression_ok": True, "regression_summary": "PASS", "secret_pattern_count": 0},
    )

    assert snapshot["decision"] == "READY_FOR_UAT"
    assert snapshot["release_report_decision"] == "FORMAL_APPROVED"
    assert snapshot["gate_summary"] == {"pass": 11, "hold": 0, "total": 11}
    assert snapshot["user_signoff"] == "PENDING"
    gates = {item["gate_id"]: item for item in snapshot["gates"]}
    assert gates["voc_pipeline"]["evidence"].startswith("PASS 18/18")
    assert gates["fault_execution"]["status"] == "PASS"
    assert gates["defects"]["evidence"] == "확정 미종결 0건 · 미확정 후보 0건"


def test_acceptance_evidence_writes_json_and_markdown(monkeypatch, tmp_path):
    store = voc_acceptance_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    run = store.start_voc_run(
        run_type="BATCH",
        selected_case_ids=["TC-01"],
        suite_id="VOC-QA-35",
        catalog_version="1.0",
        test_case_hash="hash",
        rubric_versions={},
        model_snapshot={},
        judge_enabled=False,
        environment_fingerprint={},
    )
    snapshot = {
        "run_id": run["run_id"],
        "decision": "HOLD",
        "user_signoff": "PENDING",
        "gate_summary": {"pass": 1, "hold": 1, "total": 2},
        "gates": [{"status": "HOLD", "label": "35 PASS", "evidence": "1/35"}],
        "remaining_risks": [{"level": "HIGH", "risk": "미통과", "action": "재시험"}],
        "presentation_flow": ["목적", "배포 판정"],
    }

    generated = voc_acceptance_service.generate_acceptance_evidence(snapshot)

    assert Path(generated["paths"]["json"]).is_file()
    assert Path(generated["paths"]["markdown"]).is_file()
    assert json.loads(generated["contents"]["json"])["decision"] == "HOLD"
    assert "사용자 최종 승인을 대신하지 않습니다" in generated["contents"]["markdown"]
    assert len(generated["sha256"]["json"]) == 64


def test_acceptance_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_acceptance_app.py", default_timeout=30)
    app.run()

    assert not app.exception
    assert any(selectbox.label == "최종 인수 대상 Run" for selectbox in app.selectbox)
    assert app.metric[0].label == "인수 판정"
    metric_values = {metric.label: metric.value for metric in app.metric}
    assert metric_values["정식 승인"] == "정식 승인"
    assert metric_values["품질 게이트"] == "12/12"
    assert metric_values["HOLD"] == "0"
    assert metric_values["VOC 개선 PASS"] == "18/18"
    assert metric_values["장애 검증 실행"] == "8/8"
    assert metric_values["독립 LLM PASS"] == "18/18"
    assert metric_values["업무 승인 완료"] == "18/18"
