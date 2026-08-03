from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from core.paths import VOC_RUNTIME_DIR
from services import voc_defect_service, voc_report_service, voc_run_store


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _gate(gate_id: str, label: str, passed: bool, evidence: str) -> dict:
    return {
        "gate_id": gate_id,
        "label": label,
        "status": "PASS" if passed else "HOLD",
        "evidence": evidence,
    }


def _count_value(counts: dict | None, key: str) -> int:
    if not isinstance(counts, dict):
        return 0
    return int(counts.get(key) or 0)


def _linked_retest_evidence_text(release_scope: dict) -> str:
    linked = release_scope.get("linked_retest_evidence")
    if not isinstance(linked, list) or not linked:
        return "연결 RETEST 없음"
    labels = [
        f"{item.get('case_id', '-')} → {item.get('retest_run_id', '-')}"
        for item in linked[:3]
    ]
    suffix = "" if len(linked) <= 3 else f" 외 {len(linked) - 3}건"
    return f"연결 RETEST {len(linked)}건 · " + ", ".join(labels) + suffix


def latest_full_run_id() -> str:
    for item in voc_run_store.list_voc_runs(recover=False):
        selected_count = item.get("selected_count")
        if selected_count is None:
            selected_count = len(item.get("selected_case_ids", []))
        scope = item.get("verification_scope", {}) if isinstance(item.get("verification_scope"), dict) else {}
        catalog_total = int(scope.get("catalog_total_cases") or 35)
        if item.get("status") == "COMPLETED" and selected_count == catalog_total:
            return str(item["run_id"])
    return ""


def load_verification_snapshot() -> dict:
    path = VOC_RUNTIME_DIR.parent / "docs" / "voc_quality" / "step10_verification.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _workflow_coverage(run_id: str, report: dict) -> list[dict]:
    history = voc_run_store.list_voc_runs(recover=False)
    run_types = {str(item.get("run_type") or "") for item in history}
    evaluation = report["evaluation"]
    release_scope = report.get("release_scope", {})
    linked_retest_count = int(release_scope.get("linked_retest_count") or 0)
    defects = voc_defect_service.list_defects()
    checks = (
        ("수동 TC 수행", "MANUAL" in run_types, "MANUAL Run 이력"),
        ("일괄 TC 수행", release_scope.get("full_catalog_selected"), f"{run_id} · {release_scope.get('selected_count', report['run']['selected_count'])}건"),
        ("수행 이력", bool(history), f"저장 Run {len(history)}건"),
        ("독립 LLM 평가", evaluation["judge_evaluated"] > 0, f"독립 LLM 평가 증적 {evaluation['judge_evaluated']}건"),
        ("개선안 타당성 평가", evaluation["validity_evaluated"] > 0, f"개선안 타당성 평가 증적 {evaluation['validity_evaluated']}건"),
        ("장애·결함 관리", bool(defects), f"등록 결함·후보 {len(defects)}건"),
        ("품질 보고서", bool(report.get("report_id")), report.get("report_id", "")),
        (
            "연결 RETEST",
            linked_retest_count > 0 or release_scope.get("voc_pass_ready"),
            _linked_retest_evidence_text(release_scope) if linked_retest_count else "보완 재시험 필요 없음",
        ),
        ("최종 인수 범위", release_scope.get("release_scope_ready"), release_scope.get("basis", "실행 가능 Case PASS + 후속 구현 Case 승인")),
    )
    return [
        {"workflow": label, "status": "PASS" if passed else "HOLD", "evidence": evidence}
        for label, passed, evidence in checks
    ]


def build_acceptance_snapshot(
    run_id: str,
    baseline_run_id: str = "",
    *,
    runtime: dict | None = None,
    agents: dict | None = None,
    verification: dict | None = None,
) -> dict:
    report = voc_report_service.build_quality_report_model(run_id, baseline_run_id)
    counts = report["run"]["counts"]
    evaluation = report["evaluation"]
    release_scope = report.get("release_scope", {})
    executable_count = int(release_scope.get("executable_count") or 35)
    voc_count = int(release_scope.get("voc_count") or executable_count)
    fault_count = int(release_scope.get("fault_count") or 0)
    judge_required_count = int(release_scope.get("judge_required_count") or voc_count)
    validity_required_count = int(release_scope.get("validity_required_count") or voc_count)
    pending_count = int(release_scope.get("pending_count") or 0)
    voc_counts = release_scope.get("voc_counts", {}) if isinstance(release_scope.get("voc_counts"), dict) else {}
    fault_counts = release_scope.get("fault_counts", {}) if isinstance(release_scope.get("fault_counts"), dict) else {}
    pending_counts = release_scope.get("pending_counts", {}) if isinstance(release_scope.get("pending_counts"), dict) else {}
    judge_counts = release_scope.get("executable_judge_counts", evaluation["judge_counts"])
    validity_counts = release_scope.get("executable_validity_counts", evaluation["validity_counts"])
    linked_retest_count = int(release_scope.get("linked_retest_count") or 0)
    defects = report["defects"]
    confirmed_blocking_defects = [
        item for item in defects
        if item.get("severity") in {"CRITICAL", "HIGH"} and item.get("status") != "CLOSED"
        and item.get("evidence_status") == "CONFIRMED"
    ]
    pending_important = [
        item for item in defects
        if item.get("severity") in {"CRITICAL", "HIGH"} and item.get("status") != "CLOSED"
        and item.get("evidence_status") != "CONFIRMED"
    ]
    runtime = runtime or {}
    agents = agents or {}
    verification = verification or {}
    gates = [
        _gate("full_scope", "35건 검증 범위 구성", bool(release_scope.get("full_catalog_selected")), f"전체 {release_scope.get('selected_count', report['run']['selected_count'])}/{release_scope.get('catalog_total_cases', 35)}건"),
        _gate("integrity", "Run·Case 증적 무결성", bool(report["integrity"].get("ok")), "; ".join(report["integrity"].get("errors", [])) or "무결성 검증 완료"),
        _gate("voc_pipeline", f"VOC 개선 Case {voc_count}건 PASS", bool(release_scope.get("voc_pass_ready", release_scope.get("executable_pass_ready"))), f"PASS {_count_value(voc_counts, 'PASS')}/{voc_count} · {_linked_retest_evidence_text(release_scope)}"),
        _gate("fault_execution", f"장애 검증 Case {fault_count}건 실행 확인", bool(release_scope.get("fault_execution_ready", fault_count == 0)), f"통과 {_count_value(fault_counts, 'PASS')}건 · 검토 필요 {_count_value(fault_counts, 'REVIEW_REQUIRED')}건 · 실패/오류 {_count_value(fault_counts, 'FAIL') + _count_value(fault_counts, 'ERROR')}건"),
        _gate("judge", f"VOC 개선 Case 독립 LLM 평가 PASS", bool(release_scope.get("judge_pass_ready")), f"PASS {_count_value(judge_counts, 'PASS')}/{judge_required_count}"),
        _gate("validity", f"VOC 개선 Case 업무 승인 완료", bool(release_scope.get("validity_approval_ready")), f"업무 승인 {_count_value(validity_counts, 'BUSINESS_APPROVED')}/{validity_required_count}"),
        _gate("followup", f"후속 구현 Case {pending_count}건 승인", bool(release_scope.get("pending_plan_approved")), f"NOT_RUN {_count_value(pending_counts, 'NOT_RUN')}/{pending_count} · {release_scope.get('pending_policy', '')}"),
        _gate("defects", "확정 Critical/High 결함 0건", not confirmed_blocking_defects, f"확정 미종결 {len(confirmed_blocking_defects)}건 · 미확정 후보 {len(pending_important)}건"),
        _gate("runtime", "실행환경·6개 Agent 정상", bool(runtime.get("ok")) and bool(agents.get("all_running")), f"Agent {agents.get('running', 0)}/{agents.get('total', 6)}"),
        _gate("regression", "전체 자동 회귀 신규 실패 0건", bool(verification.get("regression_ok")), verification.get("regression_summary", "이번 인수 검증 결과 미등록")),
        _gate("security", "산출물 비밀값 검사 0건", verification.get("secret_pattern_count") == 0, f"탐지 {verification.get('secret_pattern_count', '미검사')}건"),
    ]
    if linked_retest_count:
        gates.insert(
            5,
            _gate(
                "linked_retest",
                "연결 RETEST 보완 반영",
                True,
                _linked_retest_evidence_text(release_scope),
            ),
        )
    passed = sum(item["status"] == "PASS" for item in gates)
    decision = "READY_FOR_UAT" if passed == len(gates) else "HOLD"
    return {
        "schema_version": "1.0",
        "acceptance_id": f"VOC-ACCEPTANCE-{run_id}",
        "generated_at": _now_iso(),
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "decision": decision,
        "user_signoff": "PENDING",
        "gate_summary": {"pass": passed, "hold": len(gates) - passed, "total": len(gates)},
        "gates": gates,
        "workflow_coverage": _workflow_coverage(run_id, report),
        "quantitative": {
            "case_counts": counts,
            "failure_rate_percent": round((max(executable_count, 1) - release_scope.get("executable_counts", {}).get("PASS", 0)) / max(executable_count, 1) * 100, 1),
            "judge_counts": evaluation["judge_counts"],
            "validity_counts": evaluation["validity_counts"],
            "release_scope": release_scope,
            "trace_cases": evaluation["trace_cases"],
            "trace_events": evaluation["trace_events"],
            "cost_krw": "NOT_AVAILABLE",
            "response_time": "Run 시작·종료 시각과 Case별 시각을 수행 이력에서 확인",
        },
        "remaining_risks": report["risks"],
        "report_state": report.get("report_state", ""),
        "release_report_decision": report["release_decision"],
        "release_scope_summary": {
            "basis": release_scope.get("basis", ""),
            "voc_count": voc_count,
            "fault_count": fault_count,
            "pending_count": pending_count,
            "linked_retest_count": linked_retest_count,
            "judge_required_count": judge_required_count,
            "validity_required_count": validity_required_count,
            "release_scope_ready": bool(release_scope.get("release_scope_ready")),
        },
        "verification": verification,
    }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def generate_acceptance_evidence(snapshot: dict) -> dict:
    run_id = voc_run_store._validate_run_id(snapshot.get("run_id", ""))
    target = voc_run_store._run_dir(run_id) / "evidence"
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    lines = [
        "# VOC Step 10 최종 운영 인수 증적",
        "",
        f"- Run ID: `{run_id}`",
        f"- 판정: `{snapshot['decision']}`",
        f"- 사용자 최종 승인: `{snapshot['user_signoff']}`",
        f"- 품질 게이트: PASS {snapshot['gate_summary']['pass']} / HOLD {snapshot['gate_summary']['hold']}",
        "",
        "## 품질 게이트",
        "",
    ]
    lines.extend(
        f"- [{item['status']}] {item['label']} — {item['evidence']}"
        for item in snapshot["gates"]
    )
    lines.extend(["", "## 잔여 위험", ""])
    lines.extend(
        f"- [{item['level']}] {item['risk']} → {item['action']}"
        for item in snapshot["remaining_risks"]
    )
    lines.extend(["", "이 문서는 선택 Run의 자동 게이트 판정 스냅샷입니다.", ""])
    markdown_text = "\n".join(lines)
    json_path = target / "step10_acceptance.json"
    markdown_path = target / "step10_acceptance.md"
    _atomic_write(json_path, json_text)
    _atomic_write(markdown_path, markdown_text)
    return {
        "paths": {"json": str(json_path), "markdown": str(markdown_path)},
        "sha256": {
            "json": hashlib.sha256(json_path.read_bytes()).hexdigest(),
            "markdown": hashlib.sha256(markdown_path.read_bytes()).hexdigest(),
        },
        "contents": {"json": json_text, "markdown": markdown_text},
        "snapshot": snapshot,
    }
