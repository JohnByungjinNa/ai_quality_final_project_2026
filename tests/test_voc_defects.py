import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.services import voc_quality_service


def test_defect_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_defects_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    assert app.segmented_control[0].options == ["결함 목록", "신규 등록", "격리 장애시험"]


def _configure_store(monkeypatch, tmp_path):
    service = voc_quality_service.voc_defect_service
    store = service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "voc_quality_runs")
    store._ACTIVE_RUN_IDS.clear()
    return service, store


def _start_run(store, *, run_type="MANUAL", parent_run_id=""):
    return store.start_voc_run(
        run_type=run_type,
        selected_case_ids=["TC-01"],
        suite_id="VOC-QA-35",
        catalog_version="1.0",
        test_case_hash="abc123",
        rubric_versions={"internal_pipeline": {"version": "1.0", "sha256": "hash"}},
        model_snapshot={"summary": {"provider": "openai", "model": "test"}},
        judge_enabled=False,
        environment_fingerprint={"fingerprint_sha256": "env"},
        run_metadata={"parent_run_id": parent_run_id} if parent_run_id else None,
    )


def _complete(store, run, status):
    store.save_case_artifacts(
        run["run_id"],
        "TC-01",
        pipeline_result={"ok": status == "PASS"},
        trace={"trace_id": "trace-1", "events": []},
        rule_result={"status": status},
    )
    store.complete_voc_run(
        run["run_id"],
        [{"case_id": "TC-01", "status": status, "attempt_count": 1}],
        lifecycle_status="COMPLETED",
    )


def _create(service, baseline_id):
    return service.create_defect(
        title="분기 인터페이스 오류",
        severity="HIGH",
        category="INTERFACE_BRANCH",
        description="특정 분기에서 요청 형식이 일치하지 않음",
        actor="QA",
        evidence_status="CONFIRMED",
        related_run_ids=[baseline_id],
        related_case_ids=["TC-01"],
        related_trace_ids=["trace-1"],
        candidate_key="branch_interface_error",
    )


def test_defect_registration_builds_index_and_run_link(monkeypatch, tmp_path):
    service, store = _configure_store(monkeypatch, tmp_path)
    baseline = _start_run(store)
    _complete(store, baseline, "FAIL")

    defect = _create(service, baseline["run_id"])

    assert defect["status"] == "OPEN"
    assert service.list_defects()[0]["defect_id"] == defect["defect_id"]
    index = json.loads((tmp_path / "voc_quality_defects" / "index.json").read_text(encoding="utf-8"))
    assert index["defects"][0]["candidate_key"] == "branch_interface_error"
    run_defects = json.loads((Path(baseline["run_dir"]) / "defects.json").read_text(encoding="utf-8"))
    assert run_defects["defects"][0]["defect_id"] == defect["defect_id"]

    with pytest.raises(ValueError, match="이미 등록된 후보"):
        _create(service, baseline["run_id"])


def test_defect_requires_linear_state_and_required_analysis(monkeypatch, tmp_path):
    service, store = _configure_store(monkeypatch, tmp_path)
    baseline = _start_run(store)
    _complete(store, baseline, "FAIL")
    defect = _create(service, baseline["run_id"])

    with pytest.raises(ValueError, match="ANALYZED"):
        service.transition_defect(
            defect["defect_id"], target_status="FIXED", actor="QA", comment="skip"
        )
    with pytest.raises(ValueError, match="원인"):
        service.transition_defect(
            defect["defect_id"],
            target_status="ANALYZED",
            actor="QA",
            comment="분석",
            fields={"root_cause": "", "impact": "영향"},
        )


def test_defect_closes_only_after_linked_pass_retest(monkeypatch, tmp_path):
    service, store = _configure_store(monkeypatch, tmp_path)
    baseline = _start_run(store)
    _complete(store, baseline, "FAIL")
    defect = _create(service, baseline["run_id"])
    service.transition_defect(
        defect["defect_id"], target_status="ANALYZED", actor="QA", comment="분석",
        fields={"root_cause": "분기 계약 불일치", "impact": "정책 생성 실패"},
    )
    service.transition_defect(
        defect["defect_id"], target_status="FIXED", actor="QA", comment="수정",
        fields={"corrective_action": "요청 계약 통일", "owner": "QA", "due_date": "2026-07-16"},
    )

    failed_retest = _start_run(store, run_type="RETEST", parent_run_id=baseline["run_id"])
    _complete(store, failed_retest, "FAIL")
    with pytest.raises(ValueError, match="모두 PASS"):
        service.transition_defect(
            defect["defect_id"], target_status="RETESTED", actor="QA", comment="실패 재시험",
            fields={"retest_run_id": failed_retest["run_id"]},
        )

    passed_retest = _start_run(store, run_type="RETEST", parent_run_id=baseline["run_id"])
    _complete(store, passed_retest, "PASS")
    retested = service.transition_defect(
        defect["defect_id"], target_status="RETESTED", actor="QA", comment="PASS 확인",
        fields={"retest_run_id": passed_retest["run_id"]},
    )
    assert retested["retest_evidence"][-1]["outcome"] == "PASS"
    closed = service.transition_defect(
        defect["defect_id"], target_status="CLOSED", actor="QA", comment="종료 승인",
        fields={"closure_comment": "원본 FAIL 및 연결 RETEST PASS 확인"},
    )
    assert closed["status"] == "CLOSED"
    assert [item["to_status"] for item in closed["history"]] == [
        "OPEN", "ANALYZED", "FIXED", "RETESTED", "CLOSED"
    ]
