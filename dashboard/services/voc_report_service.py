from __future__ import annotations

import hashlib
import html
import json
import os
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

from core.paths import VOC_RUNTIME_DIR
from services import voc_defect_service, voc_run_store
from services.voc_quality_state_model import build_verification_scope


STATUS_ORDER = ("PASS", "FAIL", "ERROR", "REVIEW_REQUIRED", "NOT_RUN")
STATUS_LABELS = {
    "PASS": "통과",
    "FAIL": "실패",
    "ERROR": "오류",
    "REVIEW_REQUIRED": "검토 필요",
    "NOT_RUN": "미실행",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _catalog() -> dict:
    return _load_json(VOC_RUNTIME_DIR / "quality_diagnosis" / "quality_test_catalog.json")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_bytes(content.encode("utf-8"))
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _normalized_counts(summary: dict) -> dict[str, int]:
    results = summary.get("case_results", [])
    counted = Counter(str(item.get("status") or "ERROR") for item in results)
    return {status: int(counted.get(status, 0)) for status in STATUS_ORDER}


def _counts_for_case_ids(summary: dict, case_ids: set[str]) -> dict[str, int]:
    counted = Counter(
        str(item.get("status") or "ERROR")
        for item in summary.get("case_results", [])
        if str(item.get("case_id") or "") in case_ids
    )
    return {status: int(counted.get(status, 0)) for status in STATUS_ORDER}


def _scope_from_manifest(catalog: dict, manifest: dict, summary: dict) -> dict:
    metadata = manifest.get("run_metadata", {}) if isinstance(manifest.get("run_metadata"), dict) else {}
    scope = metadata.get("verification_scope") if isinstance(metadata.get("verification_scope"), dict) else {}
    selected = list(manifest.get("selected_case_ids") or [])
    if not selected:
        selected = [
            str(item.get("case_id") or "")
            for item in summary.get("case_results", [])
            if item.get("case_id")
        ]
    if not scope or not scope.get("selected_case_ids"):
        scope = build_verification_scope(catalog.get("cases", []), selected)
    return scope


def _evaluation_counts_for_case_ids(evaluation: dict, case_ids: set[str], field: str) -> dict[str, int]:
    counted = Counter()
    for item in evaluation.get("case_evaluations", []):
        case_id = str(item.get("case_id") or "")
        if case_id not in case_ids:
            continue
        value = str(item.get(field) or "")
        if value:
            counted[value] += 1
    return dict(counted)


def _release_scope_model(catalog: dict, manifest: dict, summary: dict, evaluation: dict) -> dict:
    scope = _scope_from_manifest(catalog, manifest, summary)
    executable_ids = {str(case_id) for case_id in scope.get("executable_case_ids", [])}
    pending_ids = {str(case_id) for case_id in scope.get("pending_case_ids", [])}
    executable_counts = _counts_for_case_ids(summary, executable_ids)
    pending_counts = _counts_for_case_ids(summary, pending_ids)
    executable_judge_counts = _evaluation_counts_for_case_ids(evaluation, executable_ids, "judge_decision")
    executable_validity_counts = _evaluation_counts_for_case_ids(evaluation, executable_ids, "validity_state")
    catalog_total = int(scope.get("catalog_total_cases") or len(catalog.get("cases", [])) or 0)
    selected_count = int(scope.get("selected_count") or len(scope.get("selected_case_ids", [])) or 0)
    executable_total = int(scope.get("executable_count") or len(executable_ids))
    pending_total = int(scope.get("pending_count") or len(pending_ids))

    full_catalog_selected = (
        selected_count == catalog_total
        and not scope.get("unknown_case_ids")
        and executable_total + pending_total == selected_count
    )
    executable_pass_ready = executable_total > 0 and executable_counts.get("PASS", 0) == executable_total
    pending_plan_approved = pending_counts.get("NOT_RUN", 0) == pending_total
    judge_pass_ready = executable_total > 0 and executable_judge_counts.get("PASS", 0) == executable_total
    validity_approval_ready = (
        executable_total > 0
        and executable_validity_counts.get("BUSINESS_APPROVED", 0) == executable_total
    )
    release_scope_ready = all(
        (
            full_catalog_selected,
            executable_pass_ready,
            pending_plan_approved,
            judge_pass_ready,
            validity_approval_ready,
        )
    )
    return {
        "basis": "실행 가능 Case PASS + 후속 구현 Case 승인",
        "catalog_total_cases": catalog_total,
        "selected_count": selected_count,
        "executable_case_ids": sorted(executable_ids),
        "pending_case_ids": sorted(pending_ids),
        "executable_count": executable_total,
        "pending_count": pending_total,
        "executable_counts": executable_counts,
        "pending_counts": pending_counts,
        "executable_judge_counts": executable_judge_counts,
        "executable_validity_counts": executable_validity_counts,
        "full_catalog_selected": full_catalog_selected,
        "executable_pass_ready": executable_pass_ready,
        "pending_plan_approved": pending_plan_approved,
        "judge_pass_ready": judge_pass_ready,
        "validity_approval_ready": validity_approval_ready,
        "release_scope_ready": release_scope_ready,
        "pending_policy": (
            "후속 구현 Case는 카탈로그에 DEFINED로 승인된 항목이며 이번 회차에서는 NOT_RUN이 정상 상태입니다."
        ),
    }


def _claim_check(
    stored: dict | None,
    *,
    expected_counts: dict[str, int],
    catalog: dict,
    reference_manifest: dict | None = None,
    require_defect_links: bool = False,
) -> dict:
    errors: list[str] = []
    if not stored:
        return {"verified": False, "errors": ["연결된 Run이 없습니다."], "run_id": ""}
    manifest = stored.get("manifest", {})
    summary = stored.get("summary", {})
    run_id = manifest.get("run_id", "")
    expected_ids = {item["case_id"] for item in catalog.get("cases", [])}
    selected_ids = set(manifest.get("selected_case_ids", []))
    if manifest.get("status") != "COMPLETED":
        errors.append("완료된 Run이 아닙니다.")
    if selected_ids != expected_ids:
        errors.append(f"35건 Case 범위가 일치하지 않습니다: {len(selected_ids)}/35")
    if manifest.get("suite_id") != catalog.get("suite_id"):
        errors.append("Suite ID가 기준 세트와 다릅니다.")
    counts = _normalized_counts(summary)
    for status, expected in expected_counts.items():
        if counts.get(status, 0) != expected:
            errors.append(f"{status} 실제 {counts.get(status, 0)}건, 기대 {expected}건")
    if sum(counts.values()) != int(catalog.get("total_cases", 35)):
        errors.append(f"실제 결과 합계가 35건이 아닙니다: {sum(counts.values())}건")
    if reference_manifest:
        for field in ("suite_id", "catalog_version", "test_case_hash", "rubric_versions"):
            if manifest.get(field) != reference_manifest.get(field):
                errors.append(f"비교 Run과 {field}가 다릅니다.")
    if require_defect_links:
        linked_keys = {
            item.get("candidate_key") for item in stored.get("defects", {}).get("defects", [])
        }
        required_keys = {
            item.get("defect_key")
            for item in catalog.get("baseline_claim", {}).get("candidate_defects", [])
        }
        missing = sorted(value for value in required_keys if value and value not in linked_keys)
        if missing:
            errors.append("기준선 결함 링크가 없습니다: " + ", ".join(missing))
    return {
        "verified": not errors,
        "errors": errors,
        "run_id": run_id,
        "actual_counts": counts,
    }


def _group_coverage(catalog: dict, summary: dict) -> list[dict]:
    case_map = {item["case_id"]: item for item in catalog.get("cases", [])}
    groups = catalog.get("groups", {})
    rows = {
        group_id: {
            "group_id": group_id,
            "group": spec.get("label", group_id),
            "expected": int(spec.get("expected_count", 0)),
            "selected": 0,
            **{status: 0 for status in STATUS_ORDER},
        }
        for group_id, spec in groups.items()
    }
    for item in summary.get("case_results", []):
        case = case_map.get(item.get("case_id"), {})
        group_id = case.get("group", "unknown")
        if group_id not in rows:
            rows[group_id] = {
                "group_id": group_id,
                "group": group_id,
                "expected": 0,
                "selected": 0,
                **{status: 0 for status in STATUS_ORDER},
            }
        rows[group_id]["selected"] += 1
        status = item.get("status")
        if status in STATUS_ORDER:
            rows[group_id][status] += 1
    return list(rows.values())


def _case_evaluation_stats(run_id: str, summary: dict) -> dict:
    judge = Counter()
    validity = Counter()
    trace_events = 0
    trace_cases = 0
    examples = []
    case_evaluations = []
    for result in summary.get("case_results", []):
        case_id = result.get("case_id")
        case_row = {
            "case_id": case_id,
            "judge_decision": "",
            "validity_state": "",
            "trace_event_count": 0,
        }
        try:
            artifact = voc_run_store.load_case_artifacts(run_id, case_id)
        except Exception:
            case_evaluations.append(case_row)
            continue
        events = artifact.get("trace", {}).get("events", [])
        if events:
            trace_cases += 1
            trace_events += len(events)
            case_row["trace_event_count"] = len(events)
        judge_result = artifact.get("judge_result", {})
        if judge_result:
            judge_decision = judge_result.get("decision") or judge_result.get("status") or "UNKNOWN"
            judge[judge_decision] += 1
            case_row["judge_decision"] = judge_decision
        validity_result = artifact.get("validity_result", {})
        if validity_result:
            validity_state = validity_result.get("workflow_state") or validity_result.get("decision") or "UNKNOWN"
            validity[validity_state] += 1
            case_row["validity_state"] = validity_state
        pipeline = artifact.get("pipeline_result", {})
        execution_result = pipeline.get("execution", {}).get("result", {})
        if execution_result and len(examples) < 3:
            examples.append(
                {
                    "case_id": case_id,
                    "question": pipeline.get("execution", {}).get("question", ""),
                    "summary_present": bool(execution_result.get("summary")),
                    "policy_present": bool(execution_result.get("policy")),
                    "trace_id": artifact.get("trace", {}).get("trace_id", ""),
                }
            )
        case_evaluations.append(case_row)
    return {
        "judge_counts": dict(judge),
        "judge_evaluated": sum(judge.values()),
        "validity_counts": dict(validity),
        "validity_evaluated": sum(validity.values()),
        "trace_cases": trace_cases,
        "trace_events": trace_events,
        "voc_examples": examples,
        "case_evaluations": case_evaluations,
    }


def _risk_rows(
    counts: dict,
    defects: list[dict],
    integrity: dict,
    claims: dict,
    release_scope: dict | None = None,
) -> list[dict]:
    risks = []
    scope = release_scope or {}
    if not integrity.get("ok"):
        risks.append({"level": "HIGH", "risk": "Run 증적 무결성 오류", "action": "누락·불일치 증적 복구"})
    executable_counts = scope.get("executable_counts") if isinstance(scope.get("executable_counts"), dict) else counts
    pending_counts = scope.get("pending_counts") if isinstance(scope.get("pending_counts"), dict) else {}
    if executable_counts.get("ERROR"):
        risks.append({"level": "HIGH", "risk": f"실행 가능 Case 오류 {executable_counts['ERROR']}건", "action": "오류 원인 조치 후 연결 재시험"})
    if executable_counts.get("FAIL"):
        risks.append({"level": "HIGH", "risk": f"실행 가능 Case 실패 {executable_counts['FAIL']}건", "action": "결함 등록과 재시험"})
    if executable_counts.get("REVIEW_REQUIRED"):
        risks.append({"level": "MEDIUM", "risk": f"실행 가능 Case 검토 필요 {executable_counts['REVIEW_REQUIRED']}건", "action": "독립 LLM 평가·QA 검토 수행"})
    if pending_counts.get("NOT_RUN") and not scope.get("pending_plan_approved"):
        risks.append({"level": "MEDIUM", "risk": f"후속 구현 Case 승인 확인 필요 {pending_counts['NOT_RUN']}건", "action": "후속 구현 계획과 제외 사유 승인"})
    pending = [item for item in defects if item.get("evidence_status") == "PENDING"]
    if pending:
        risks.append({"level": "MEDIUM", "risk": f"미확정 결함 후보 {len(pending)}건", "action": "원본 Run·실행 Trace 확보 전 PENDING 유지"})
    if not scope.get("release_scope_ready"):
        risks.append({"level": "HIGH", "risk": "최종 인수 범위 미충족", "action": "실행 가능 Case PASS·독립 LLM PASS·업무 승인과 후속 구현 승인 상태를 맞추세요."})
    return risks


def build_quality_report_model(run_id: str, baseline_run_id: str = "") -> dict:
    selected = voc_run_store.load_voc_run(run_id)
    if selected.get("errors"):
        raise ValueError("선택 Run을 완전하게 읽을 수 없습니다: " + ", ".join(selected["errors"]))
    manifest = selected.get("manifest", {})
    summary = selected.get("summary", {})
    catalog = _catalog()
    integrity = voc_run_store.verify_run_integrity(run_id)
    counts = _normalized_counts(summary)
    baseline = voc_run_store.load_voc_run(baseline_run_id) if baseline_run_id else None
    baseline_check = _claim_check(
        baseline,
        expected_counts={"PASS": 33, "FAIL": 2, "ERROR": 0, "REVIEW_REQUIRED": 0, "NOT_RUN": 0},
        catalog=catalog,
        reference_manifest=manifest,
        require_defect_links=True,
    )
    final_check = _claim_check(
        selected,
        expected_counts={"PASS": 35, "FAIL": 0, "ERROR": 0, "REVIEW_REQUIRED": 0, "NOT_RUN": 0},
        catalog=catalog,
        reference_manifest=baseline.get("manifest", {}) if baseline else None,
    )
    claims = {
        "baseline": baseline_check,
        "final": final_check,
        "improvement_verified": baseline_check["verified"] and final_check["verified"],
        "claim_text": "초기 33 PASS / 2 FAIL → 최종 35 PASS",
    }
    defects = voc_defect_service.list_defects()
    evaluation = _case_evaluation_stats(run_id, summary)
    release_scope = _release_scope_model(catalog, manifest, summary, evaluation)
    formal_approval = (
        release_scope["release_scope_ready"]
        and integrity.get("ok")
        and not [item for item in defects if item.get("status") != "CLOSED" and item.get("severity") in {"HIGH", "CRITICAL"}]
    )
    decision = "FORMAL_APPROVED" if formal_approval else "NOT_APPROVED"
    risks = _risk_rows(counts, defects, integrity, claims, release_scope)
    coverage = _group_coverage(catalog, summary)
    generated_at = _now_iso()
    return {
        "schema_version": "1.0",
        "report_id": f"VOC-REPORT-{run_id}",
        "generated_at": generated_at,
        "report_state": "FINAL" if formal_approval else "EVIDENCE_DRAFT",
        "release_decision": decision,
        "run": {
            "run_id": run_id,
            "run_type": manifest.get("run_type"),
            "lifecycle": manifest.get("status"),
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
            "suite_id": manifest.get("suite_id"),
            "catalog_version": manifest.get("catalog_version"),
            "selected_count": len(manifest.get("selected_case_ids", [])),
            "counts": counts,
        },
        "integrity": integrity,
        "claims": claims,
        "verification_scope": _scope_from_manifest(catalog, manifest, summary),
        "release_scope": release_scope,
        "coverage": coverage,
        "evaluation": evaluation,
        "defects": [
            {
                key: item.get(key)
                for key in ("defect_id", "candidate_key", "title", "severity", "status", "evidence_status", "owner", "related_run_ids")
            }
            for item in defects
        ],
        "risks": risks,
        "roles": [
            {"role": "Evaluator", "scope": "Agent 파이프라인 내부 후보 상대평가", "independence": "내부"},
            {"role": "Critic", "scope": "Agent 파이프라인 내부 결함·위험 탐지와 수정 지침", "independence": "내부"},
            {"role": "독립 LLM 평가", "scope": "최종 산출물의 별도 100점 Rubric 평가", "independence": "별도 호출·모델 등급 기록"},
        ],
        "formula": {
            "status_count": "각 Case summary.status의 단순 건수",
            "coverage": "그룹별 선택 Case 수 / Catalog 그룹 기대 건수",
            "success_rate": "실행 가능 Case PASS / 실행 가능 Case 수 × 100; 후속 구현 Case는 별도 승인 상태로 판단",
            "improvement_claim": "동일 suite·catalog·TC hash·Rubric·35 Case인 33/2 기준선과 35 PASS 최종 Run이 모두 검증될 때만 참",
            "release": "실행 가능 Case PASS + 실행 가능 Case 독립 LLM PASS + 실행 가능 Case 업무 승인 + 후속 구현 Case 승인 + 미종결 High/Critical 0건",
        },
    }


def _table_html(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{html.escape(str(value))}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value if value is not None else '-'))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_report_txt(model: dict) -> str:
    run = model["run"]
    counts = run["counts"]
    release_scope = model.get("release_scope", {})
    executable_total = int(release_scope.get("executable_count") or run["selected_count"] or 0)
    pending_total = int(release_scope.get("pending_count") or 0)
    executable_counts = release_scope.get("executable_counts", {}) if isinstance(release_scope.get("executable_counts"), dict) else {}
    pending_counts = release_scope.get("pending_counts", {}) if isinstance(release_scope.get("pending_counts"), dict) else {}
    lines = [
        "VOC 품질평가 증적 보고서",
        "=" * 30,
        f"보고서 상태: {model['report_state']}",
        f"최종 판정: {model['release_decision']}",
        f"Run ID: {run['run_id']}",
        f"실행 시각: {run['started_at']} ~ {run['finished_at']}",
        f"정량 결과: 전체 {run['selected_count']} / " + " / ".join(f"{status} {counts[status]}" for status in STATUS_ORDER),
        "",
        "1단계: VOC 분석 및 정책 개선안 생성",
        f"- 산출물 확인 Case: {len(model['evaluation']['voc_examples'])}건(대표 표본)",
        "2단계: 6개 멀티 에이전트 내부 품질진단",
        f"- 실행 Trace 보유 Case: {model['evaluation']['trace_cases']}건, 이벤트: {model['evaluation']['trace_events']}건",
        "3단계: 독립 LLM 평가",
        f"- 독립 LLM 평가 Case: {model['evaluation']['judge_evaluated']}건, 판정: {model['evaluation']['judge_counts']}",
        "",
        "검증 범위 정량 분석",
        f"- 인수 기준: {release_scope.get('basis', '실행 가능 Case PASS + 후속 구현 Case 승인')}",
        f"- 실행 가능 Case: PASS {executable_counts.get('PASS', 0)}/{executable_total}건",
        f"- 후속 구현 Case: NOT_RUN {pending_counts.get('NOT_RUN', 0)}/{pending_total}건 · 후속 구현 계획 승인 기준",
    ]
    for row in model["coverage"]:
        lines.append(
            f"- {row['group']}: 선택 {row['selected']}/{row['expected']}, "
            + ", ".join(f"{status} {row[status]}" for status in STATUS_ORDER)
        )
    lines.extend([
        "",
        "최종 인수 범위",
        f"- 검증 여부: {'VERIFIED' if release_scope.get('release_scope_ready') else 'NOT_VERIFIED'}",
        f"- 실행 가능 Case 독립 LLM: {release_scope.get('executable_judge_counts', {})}",
        f"- 실행 가능 Case 업무 승인: {release_scope.get('executable_validity_counts', {})}",
        "",
        "결함관리",
    ])
    for item in model["defects"]:
        lines.append(
            f"- {item['defect_id']} | {item['title']} | {item['severity']} | {item['status']} | 증적 {item['evidence_status']}"
        )
    lines.extend(["", "Evaluator·Critic과 독립 LLM 평가 역할 구분"])
    for item in model["roles"]:
        lines.append(f"- {item['role']}: {item['scope']} ({item['independence']})")
    lines.extend(["", "잔여 위험과 운영 권고"])
    for item in model["risks"]:
        lines.append(f"- [{item['level']}] {item['risk']} → {item['action']}")
    lines.extend([
        "",
        "완료 판정",
        f"- {model['release_decision']}",
        "- 미검증 수치는 성공으로 표현하지 않으며, EVIDENCE_DRAFT는 정식 품질 승인이 아닙니다.",
        "",
        f"생성 시각: {model['generated_at']}",
    ])
    return "\n".join(lines) + "\n"


def render_report_xml(model: dict) -> str:
    run = model["run"]
    counts = run["counts"]
    suite = ET.Element(
        "testsuite",
        name="VOC Quality Evidence",
        tests=str(run["selected_count"]),
        failures=str(counts["FAIL"]),
        errors=str(counts["ERROR"]),
        skipped=str(counts["REVIEW_REQUIRED"] + counts["NOT_RUN"]),
        timestamp=str(model["generated_at"]),
    )
    properties = ET.SubElement(suite, "properties")
    for name, value in (
        ("run_id", run["run_id"]),
        ("report_state", model["report_state"]),
        ("release_decision", model["release_decision"]),
        ("improvement_verified", str(model["claims"]["improvement_verified"]).lower()),
    ):
        ET.SubElement(properties, "property", name=name, value=str(value))
    stored = voc_run_store.load_voc_run(run["run_id"])
    for result in stored.get("summary", {}).get("case_results", []):
        case = ET.SubElement(suite, "testcase", classname="VOC-QA-35", name=str(result.get("case_id")))
        status = result.get("status")
        message = str(result.get("message") or STATUS_LABELS.get(status, status))
        if status == "FAIL":
            ET.SubElement(case, "failure", message=message).text = message
        elif status == "ERROR":
            ET.SubElement(case, "error", message=message).text = message
        elif status in {"REVIEW_REQUIRED", "NOT_RUN"}:
            ET.SubElement(case, "skipped", message=message)
    ET.indent(suite, space="  ")
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_report_html(model: dict) -> str:
    run = model["run"]
    counts = run["counts"]
    release_scope = model.get("release_scope", {})
    executable_total = int(release_scope.get("executable_count") or run["selected_count"] or 0)
    pending_total = int(release_scope.get("pending_count") or 0)
    executable_counts = release_scope.get("executable_counts", {}) if isinstance(release_scope.get("executable_counts"), dict) else {}
    pending_counts = release_scope.get("pending_counts", {}) if isinstance(release_scope.get("pending_counts"), dict) else {}
    max_count = max(max(counts.values()), 1)
    bars = "".join(
        f"<div class='bar-row'><span>{status}</span><i style='width:{counts[status] / max_count * 100:.1f}%'></i><b>{counts[status]}</b></div>"
        for status in STATUS_ORDER
    )
    coverage_table = _table_html(
        ["점검 범위", "선택/기대", *STATUS_ORDER],
        [[row["group"], f"{row['selected']}/{row['expected']}", *[row[s] for s in STATUS_ORDER]] for row in model["coverage"]],
    )
    defect_table = _table_html(
        ["결함 ID", "제목", "심각도", "상태", "증적"],
        [[item["defect_id"], item["title"], item["severity"], item["status"], item["evidence_status"]] for item in model["defects"]],
    )
    risk_table = _table_html(
        ["등급", "잔여 위험", "운영 권고"],
        [[item["level"], item["risk"], item["action"]] for item in model["risks"]],
    )
    claim_state = "VERIFIED" if release_scope.get("release_scope_ready") else "NOT_VERIFIED"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>VOC 품질평가 증적 보고서</title>
<style>
body{{font-family:'Malgun Gothic',Arial,sans-serif;max-width:1100px;margin:36px auto;color:#1d2b3a;line-height:1.55}}
h1,h2{{color:#174f86}} .meta,.card{{border:1px solid #d8e3ef;border-radius:12px;padding:18px;margin:14px 0}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} .kpi{{background:#f3f7fb;padding:14px;border-radius:10px}}
.kpi b{{display:block;font-size:22px;color:#174f86}} table{{width:100%;border-collapse:collapse;margin:12px 0}}
th,td{{border:1px solid #dce5ee;padding:8px;text-align:left}} th{{background:#edf4fa}}
.bar-row{{display:grid;grid-template-columns:130px 1fr 35px;gap:10px;align-items:center;margin:8px 0}}
.bar-row i{{display:block;height:18px;background:#2e78b7;border-radius:6px;min-width:2px}} .warning{{background:#fff4dc;border-color:#e9bd65}}
.footer{{color:#66788a;font-size:12px;margin-top:30px}} @media print{{body{{margin:12mm}}}}
</style></head><body>
<h1>VOC 품질평가 증적 보고서</h1>
<div class="meta"><b>상태: {html.escape(model['report_state'])}</b> · 최종 판정: <b>{html.escape(model['release_decision'])}</b><br>
Run ID: {html.escape(run['run_id'])}<br>실행: {html.escape(str(run['started_at']))} ~ {html.escape(str(run['finished_at']))}</div>
<div class="kpis"><div class="kpi">전체<b>{run['selected_count']}</b></div><div class="kpi">PASS<b>{counts['PASS']}</b></div><div class="kpi">검토 필요<b>{counts['REVIEW_REQUIRED']}</b></div><div class="kpi">오류·실패<b>{counts['ERROR'] + counts['FAIL']}</b></div></div>
<h2>1단계: VOC 분석 및 정책 개선안 생성</h2><p>대표 산출물 확인 {len(model['evaluation']['voc_examples'])}건. 원문 전체가 아닌 산출물 존재와 실행 Trace 연결 여부를 증적으로 집계했습니다.</p>
<h2>2단계: 6개 멀티 에이전트 내부 품질진단</h2><p>실행 Trace 보유 Case {model['evaluation']['trace_cases']}건, 실행 Trace 이벤트 {model['evaluation']['trace_events']}건.</p>
<h2>3단계: 독립 LLM 평가</h2><p>독립 LLM 평가 {model['evaluation']['judge_evaluated']}건 · {html.escape(str(model['evaluation']['judge_counts']))}</p>
<h2>전체 테스트 정량 분석</h2><div class="card">{bars}</div>{coverage_table}
<h2>최종 인수 범위</h2><div class="card warning"><b>{html.escape(str(release_scope.get('basis', '실행 가능 Case PASS + 후속 구현 Case 승인')))}: {claim_state}</b><br>
실행 가능 Case: PASS {executable_counts.get('PASS', 0)}/{executable_total}건<br>
후속 구현 Case: NOT_RUN {pending_counts.get('NOT_RUN', 0)}/{pending_total}건 · 후속 구현 계획 승인 기준<br>
독립 LLM: {html.escape(str(release_scope.get('executable_judge_counts', {})))} · 업무 승인: {html.escape(str(release_scope.get('executable_validity_counts', {})))}</div>
<h2>분기 인터페이스 오류와 API 429 결함관리</h2>{defect_table}
<h2>Evaluator·Critic과 독립 LLM 평가 역할 구분</h2>{_table_html(['역할','범위','독립성'], [[r['role'],r['scope'],r['independence']] for r in model['roles']])}
<h2>성공적인 품질평가 판단 근거</h2><p>수행 이력 수치, Case 증적, 독립 LLM 평가, 개선안 타당성 평가 승인, 결함 상태를 서로 대조합니다. 현재 미충족 항목이 있어 정식 품질 승인으로 판정하지 않았습니다.</p>
<h2>잔여 위험과 운영 권고</h2>{risk_table}
<h2>최종 완료 판정</h2><div class="card"><b>{html.escape(model['release_decision'])}</b><p>EVIDENCE_DRAFT는 재현 가능한 현재 상태 보고서이며 정식 완료 판정이 아닙니다.</p></div>
<h2>산식</h2><pre>{html.escape(json.dumps(model['formula'], ensure_ascii=False, indent=2))}</pre>
<div class="footer">생성 시각 {html.escape(model['generated_at'])} · TXT/XML/HTML은 동일 report model에서 생성</div>
</body></html>"""


def generate_quality_report_evidence(run_id: str, baseline_run_id: str = "") -> dict:
    model = build_quality_report_model(run_id, baseline_run_id)
    txt = render_report_txt(model)
    xml = render_report_xml(model)
    report_html = render_report_html(model)
    output_dir = Path(voc_run_store.load_voc_run(run_id)["run_dir"]) / "evidence"
    paths = {
        "txt": output_dir / "result.txt",
        "xml": output_dir / "junit.xml",
        "html": output_dir / "report.html",
        "model": output_dir / "report_model.json",
        "manifest": output_dir / "report_manifest.json",
    }
    _atomic_write(paths["txt"], txt)
    _atomic_write(paths["xml"], xml)
    _atomic_write(paths["html"], report_html)
    _atomic_write(paths["model"], json.dumps(model, ensure_ascii=False, indent=2) + "\n")
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "generated_at": model["generated_at"],
        "report_state": model["report_state"],
        "release_decision": model["release_decision"],
        "files": {
            key: {"name": path.name, "sha256": _sha256_text(value)}
            for key, path, value in (
                ("txt", paths["txt"], txt),
                ("xml", paths["xml"], xml),
                ("html", paths["html"], report_html),
            )
        },
        "shared_counts": model["run"]["counts"],
    }
    _atomic_write(paths["manifest"], json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {
        "model": model,
        "contents": {"txt": txt, "xml": xml, "html": report_html},
        "paths": {key: str(path) for key, path in paths.items()},
        "manifest": manifest,
    }
