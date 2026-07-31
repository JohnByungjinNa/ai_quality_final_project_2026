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


def latest_full_run_id() -> str:
    for item in voc_run_store.list_voc_runs(recover=False):
        selected_count = item.get("selected_count")
        if selected_count is None:
            selected_count = len(item.get("selected_case_ids", []))
        if item.get("status") == "COMPLETED" and selected_count == 35:
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
    defects = voc_defect_service.list_defects()
    checks = (
        ("수동 TC 수행", "MANUAL" in run_types, "MANUAL Run 이력"),
        ("일괄 TC 수행", report["run"]["selected_count"] == 35, f"{run_id} · 35건"),
        ("수행 이력", bool(history), f"저장 Run {len(history)}건"),
        ("독립 LLM 평가", evaluation["judge_evaluated"] > 0, f"독립 LLM 평가 증적 {evaluation['judge_evaluated']}건"),
        ("개선안 타당성 평가", evaluation["validity_evaluated"] > 0, f"개선안 타당성 평가 증적 {evaluation['validity_evaluated']}건"),
        ("장애·결함 관리", bool(defects), f"등록 결함·후보 {len(defects)}건"),
        ("품질 보고서", bool(report.get("report_id")), report.get("report_id", "")),
        ("연결 재시험", "RETEST" in run_types, "재시험 Run 이력"),
        ("동일 조건 A/B", report["claims"]["improvement_verified"], "33/2 → 35 증적 대조"),
    )
    return [
        {"workflow": label, "status": "PASS" if passed else "HOLD", "evidence": evidence}
        for label, passed, evidence in checks
    ]


def _evaluation_checklist(report: dict) -> dict:
    run = report["run"]
    counts = run["counts"]
    evaluation = report["evaluation"]
    peer = [
        ("프로젝트 목적 이해도", True, "README 목적·배포 게이트"),
        ("고객 불만 분석의 적절성", evaluation["trace_cases"] > 0, f"실행 Trace Case {evaluation['trace_cases']}건"),
        ("정책 개선안의 타당성", evaluation["validity_evaluated"] > 0, f"개선안 타당성 평가 {evaluation['validity_evaluated']}건"),
        ("멀티 에이전트 역할 설명", evaluation["trace_cases"] > 0, "6개 Agent 실행 Trace·역할 문서"),
        ("내부 품질진단의 충실성", run["selected_count"] == 35, "35건 수행 이력·Case 증적"),
        ("독립 LLM 평가 설명", evaluation["judge_evaluated"] > 0, f"독립 LLM 평가 {evaluation['judge_evaluated']}건"),
        ("테스트 결과의 객관성", sum(counts.values()) == 35, str(counts)),
        ("장애 및 결함관리 내용", bool(report["defects"]), f"결함·후보 {len(report['defects'])}건"),
        ("발표 구성 및 전달력", bool(report.get("report_id")), "품질 보고서·시연 순서"),
        ("팀 협업 및 질의응답", evaluation["validity_counts"].get("BUSINESS_APPROVED", 0) > 0, "QA·업무 승인 감사 기록"),
    ]
    professor = [
        ("요구사항·품질 계약", True, "35건 Catalog·Rubric·증적 계약"),
        ("멀티 에이전트 구조·정확성", evaluation["trace_cases"] > 0, "Agent 실행 Trace와 최종 산출물"),
        ("독립 LLM 평가·객관성", evaluation["judge_evaluated"] == 35, "독립 LLM 평가 35건 완료 여부"),
        ("장애·보안·운영성", not report["risks"], "잔여 위험·결함·복구 정책"),
        ("증적·배포 게이트", report["release_decision"] == "FORMAL_APPROVED", "보고서 무결성·최종 판정"),
    ]

    def rows(items: list[tuple[str, bool, str]], maximum: int) -> list[dict]:
        return [
            {
                "item": item,
                "max_points": maximum,
                "evidence_status": "READY" if ready else "PARTIAL",
                "evidence": evidence,
            }
            for item, ready, evidence in items
        ]

    return {
        "notice": "평가 점수를 자동 부여하지 않고 증적 준비 상태만 표시합니다.",
        "peer_80": rows(peer, 8),
        "professor_20": rows(professor, 4),
    }


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
    defects = report["defects"]
    open_important = [
        item for item in defects
        if item.get("severity") in {"CRITICAL", "HIGH"} and item.get("status") != "CLOSED"
    ]
    runtime = runtime or {}
    agents = agents or {}
    verification = verification or {}
    gates = [
        _gate("full_suite", "35건 최종 실행 완료", report["run"]["selected_count"] == 35, str(counts)),
        _gate("integrity", "Run·Case 증적 무결성", bool(report["integrity"].get("ok")), "; ".join(report["integrity"].get("errors", [])) or "무결성 검증 완료"),
        _gate("pipeline", "Agent 파이프라인 35건 PASS", counts.get("PASS") == 35, f"PASS {counts.get('PASS', 0)}/35"),
        _gate("judge", "독립 LLM 평가 35건 PASS", evaluation["judge_evaluated"] == 35 and evaluation["judge_counts"].get("PASS") == 35, str(evaluation["judge_counts"])),
        _gate("validity", "개선안 타당성 평가 업무 승인 35건", evaluation["validity_counts"].get("BUSINESS_APPROVED") == 35, str(evaluation["validity_counts"])),
        _gate("defects", "미종결 Critical/High 0건", not open_important, f"미종결 {len(open_important)}건"),
        _gate("comparison", "33/2 → 35 동일 조건 개선 증명", report["claims"]["improvement_verified"], report["claims"]["claim_text"]),
        _gate("runtime", "실행환경·6개 Agent 정상", bool(runtime.get("ok")) and bool(agents.get("all_running")), f"Agent {agents.get('running', 0)}/{agents.get('total', 6)}"),
        _gate("regression", "전체 자동 회귀 신규 실패 0건", bool(verification.get("regression_ok")), verification.get("regression_summary", "이번 인수 검증 결과 미등록")),
        _gate("security", "산출물 비밀값 검사 0건", verification.get("secret_pattern_count") == 0, f"탐지 {verification.get('secret_pattern_count', '미검사')}건"),
    ]
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
        "evaluation_checklist": _evaluation_checklist(report),
        "quantitative": {
            "case_counts": counts,
            "failure_rate_percent": round((35 - counts.get("PASS", 0)) / 35 * 100, 1),
            "judge_counts": evaluation["judge_counts"],
            "validity_counts": evaluation["validity_counts"],
            "trace_cases": evaluation["trace_cases"],
            "trace_events": evaluation["trace_events"],
            "cost_krw": "NOT_AVAILABLE",
            "response_time": "Run 시작·종료 시각과 Case별 시각을 수행 이력에서 확인",
        },
        "remaining_risks": report["risks"],
        "release_report_decision": report["release_decision"],
        "presentation_flow": [
            "프로젝트 목적", "6개 Agent", "수동·일괄 수행", "Agent 파이프라인 실행 Trace",
            "독립 LLM 평가", "개선안 타당성 평가", "장애·결함", "연결 재시험·A/B",
            "품질 보고서", "배포 판정",
        ],
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
    lines.extend([
        "", "## 발표 순서", "",
        " → ".join(snapshot["presentation_flow"]),
        "", "이 문서는 자동 판정 증적이며 사용자 최종 승인을 대신하지 않습니다. 최종 서명은 별도로 남겨야 합니다.", "",
    ])
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
