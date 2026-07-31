from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

from services import voc_run_store


DEFECT_STATES = ("OPEN", "ANALYZED", "FIXED", "RETESTED", "CLOSED")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
EVIDENCE_STATUSES = ("PENDING", "CONFIRMED")
DEFECT_ID_PATTERN = re.compile(r"VOC-DEF-\d{8}-\d{6}-[a-f0-9]{4}")
SAFE_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_LOCK = threading.RLock()


def _root() -> Path:
    return voc_run_store.VOC_QUALITY_RUNS_DIR.parent / "voc_quality_defects"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _new_id() -> str:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"VOC-DEF-{timestamp}-{uuid.uuid4().hex[:4]}"


def _validate_id(defect_id: str) -> str:
    value = str(defect_id or "")
    if not DEFECT_ID_PATTERN.fullmatch(value):
        raise ValueError("유효하지 않은 결함 ID입니다.")
    return value


def _path(defect_id: str) -> Path:
    defect_id = _validate_id(defect_id)
    root = _root().resolve()
    path = (root / defect_id / "defect.json").resolve()
    if path.parent.parent != root:
        raise ValueError("결함 저장 경로를 벗어날 수 없습니다.")
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _clean_text(value, label: str, *, required: bool = False, maximum: int = 2000) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{label}을(를) 입력하세요.")
    if len(text) > maximum:
        raise ValueError(f"{label}은(는) {maximum}자 이하여야 합니다.")
    return text


def _safe_keys(values: list[str] | None, label: str) -> list[str]:
    result: list[str] = []
    for value in values or []:
        value = str(value or "").strip()
        if not SAFE_KEY_PATTERN.fullmatch(value):
            raise ValueError(f"유효하지 않은 {label}입니다: {value}")
        if value not in result:
            result.append(value)
    return result


def create_defect(
    *,
    title: str,
    severity: str,
    category: str,
    description: str,
    actor: str,
    evidence_status: str = "PENDING",
    related_run_ids: list[str] | None = None,
    related_case_ids: list[str] | None = None,
    related_trace_ids: list[str] | None = None,
    candidate_key: str = "",
    jira_key: str = "",
) -> dict:
    severity = str(severity or "").upper()
    evidence_status = str(evidence_status or "").upper()
    if severity not in SEVERITIES:
        raise ValueError("지원하지 않는 결함 심각도입니다.")
    if evidence_status not in EVIDENCE_STATUSES:
        raise ValueError("증적 상태는 PENDING 또는 CONFIRMED여야 합니다.")

    runs = [voc_run_store._validate_run_id(value) for value in related_run_ids or []]
    for run_id in runs:
        voc_run_store.load_voc_run(run_id)
    cases = _safe_keys(related_case_ids, "Case ID")
    traces = _safe_keys(related_trace_ids, "실행 Trace ID")
    candidate_key = _clean_text(candidate_key, "후보 결함 키", maximum=100)
    if candidate_key and not SAFE_KEY_PATTERN.fullmatch(candidate_key):
        raise ValueError("후보 결함 키에는 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.")

    with _LOCK:
        if candidate_key and any(
            item.get("candidate_key") == candidate_key for item in list_defects()
        ):
            raise ValueError(f"이미 등록된 후보 결함 키입니다: {candidate_key}")
        defect_id = _new_id()
        now = _now_iso()
        payload = {
            "schema_version": "1.0",
            "defect_id": defect_id,
            "candidate_key": candidate_key,
            "title": _clean_text(title, "결함 제목", required=True, maximum=200),
            "severity": severity,
            "category": _clean_text(category, "결함 분류", required=True, maximum=100),
            "description": _clean_text(description, "현상", required=True),
            "evidence_status": evidence_status,
            "status": "OPEN",
            "related_run_ids": runs,
            "related_case_ids": cases,
            "related_trace_ids": traces,
            "root_cause": "",
            "impact": "",
            "corrective_action": "",
            "owner": "",
            "due_date": "",
            "jira_key": _clean_text(jira_key, "Jira Key", maximum=100),
            "retest_evidence": [],
            "closure_comment": "",
            "created_at": now,
            "updated_at": now,
            "history": [
                {
                    "at": now,
                    "actor": _clean_text(actor, "등록자", required=True, maximum=100),
                    "action": "CREATE",
                    "from_status": None,
                    "to_status": "OPEN",
                    "comment": "결함 등록",
                }
            ],
        }
        _write(_path(defect_id), payload)
        _sync_run_links(payload)
        rebuild_index()
        return payload


def list_defects() -> list[dict]:
    root = _root()
    if not root.exists():
        return []
    items = []
    for path in root.glob("VOC-DEF-*/defect.json"):
        try:
            items.append(_read(path))
        except Exception:
            continue
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def load_defect(defect_id: str) -> dict:
    path = _path(defect_id)
    if not path.exists():
        raise FileNotFoundError(f"결함을 찾을 수 없습니다: {defect_id}")
    return _read(path)


def rebuild_index() -> list[dict]:
    items = list_defects()
    rows = [
        {
            key: item.get(key)
            for key in (
                "defect_id",
                "candidate_key",
                "title",
                "severity",
                "category",
                "evidence_status",
                "status",
                "owner",
                "due_date",
                "related_run_ids",
                "related_case_ids",
                "updated_at",
            )
        }
        for item in items
    ]
    _write(
        _root() / "index.json",
        {"schema_version": "1.0", "updated_at": _now_iso(), "defects": rows},
    )
    return rows


def transition_defect(
    defect_id: str,
    *,
    target_status: str,
    actor: str,
    comment: str,
    fields: dict | None = None,
) -> dict:
    target = str(target_status or "").upper()
    actor = _clean_text(actor, "처리자", required=True, maximum=100)
    comment = _clean_text(comment, "처리 의견", required=True, maximum=1000)
    fields = fields or {}

    with _LOCK:
        payload = load_defect(defect_id)
        current = payload.get("status")
        expected = {
            "OPEN": "ANALYZED",
            "ANALYZED": "FIXED",
            "FIXED": "RETESTED",
            "RETESTED": "CLOSED",
        }.get(current)
        if target != expected:
            raise ValueError(
                f"{current} 상태에서는 {expected or '추가 상태'}로만 전환할 수 있습니다."
            )

        if target == "ANALYZED":
            payload["root_cause"] = _clean_text(
                fields.get("root_cause"), "원인", required=True
            )
            payload["impact"] = _clean_text(fields.get("impact"), "영향", required=True)
            if fields.get("evidence_status"):
                evidence_status = str(fields["evidence_status"]).upper()
                if evidence_status not in EVIDENCE_STATUSES:
                    raise ValueError("지원하지 않는 증적 상태입니다.")
                payload["evidence_status"] = evidence_status
        elif target == "FIXED":
            payload["corrective_action"] = _clean_text(
                fields.get("corrective_action"), "조치 내용", required=True
            )
            payload["owner"] = _clean_text(
                fields.get("owner"), "담당자", required=True, maximum=100
            )
            due_date = _clean_text(
                fields.get("due_date"), "조치 기한", required=True, maximum=10
            )
            try:
                date.fromisoformat(due_date)
            except ValueError as exc:
                raise ValueError("조치 기한은 YYYY-MM-DD 형식이어야 합니다.") from exc
            payload["due_date"] = due_date
        elif target == "RETESTED":
            retest_run_id = voc_run_store._validate_run_id(fields.get("retest_run_id"))
            evidence = _verify_retest(payload, retest_run_id)
            payload.setdefault("retest_evidence", []).append(evidence)
            if retest_run_id not in payload["related_run_ids"]:
                payload["related_run_ids"].append(retest_run_id)
        elif target == "CLOSED":
            if (
                not payload.get("retest_evidence")
                or payload["retest_evidence"][-1].get("outcome") != "PASS"
            ):
                raise ValueError("PASS 재시험 증적 없이는 결함을 종료할 수 없습니다.")
            payload["closure_comment"] = _clean_text(
                fields.get("closure_comment"), "종료 근거", required=True
            )

        now = _now_iso()
        payload["status"] = target
        payload["updated_at"] = now
        payload.setdefault("history", []).append(
            {
                "at": now,
                "actor": actor,
                "action": f"TRANSITION_{target}",
                "from_status": current,
                "to_status": target,
                "comment": comment,
            }
        )
        _write(_path(defect_id), payload)
        _sync_run_links(payload)
        rebuild_index()
        return payload


def _verify_retest(defect: dict, retest_run_id: str) -> dict:
    stored = voc_run_store.load_voc_run(retest_run_id)
    manifest = stored.get("manifest", {})
    summary = stored.get("summary", {})
    if manifest.get("status") != "COMPLETED":
        raise ValueError("완료된 재시험 Run만 연결할 수 있습니다.")

    parent = manifest.get("run_metadata", {}).get("parent_run_id")
    original_runs = [
        run_id for run_id in defect.get("related_run_ids", []) if run_id != retest_run_id
    ]
    if manifest.get("run_type") != "RETEST" or parent not in original_runs:
        raise ValueError("결함의 원본 Run과 연결된 RETEST만 사용할 수 있습니다.")

    related_cases = defect.get("related_case_ids", [])
    selected = manifest.get("selected_case_ids", [])
    if related_cases and any(case_id not in selected for case_id in related_cases):
        raise ValueError("재시험 Run에 결함 관련 Case가 모두 포함되지 않았습니다.")

    results = {item.get("case_id"): item for item in summary.get("case_results", [])}
    checked = related_cases or selected
    case_outcomes = []
    for case_id in checked:
        item = results.get(case_id, {})
        passed = item.get("status") == "PASS"
        if not passed:
            artifact = voc_run_store.load_case_artifacts(retest_run_id, case_id)
            passed = artifact.get("rule_result", {}).get("status") == "PASS"
        case_outcomes.append(
            {
                "case_id": case_id,
                "status": item.get("status", "NOT_RUN"),
                "passed": passed,
            }
        )
    if not case_outcomes or not all(item["passed"] for item in case_outcomes):
        raise ValueError("관련 Case가 모두 PASS인 재시험만 RETESTED로 전환할 수 있습니다.")

    return {
        "run_id": retest_run_id,
        "parent_run_id": parent,
        "verified_at": _now_iso(),
        "outcome": "PASS",
        "case_outcomes": case_outcomes,
    }


def _sync_run_links(defect: dict) -> None:
    reference = {
        key: defect.get(key)
        for key in (
            "defect_id",
            "candidate_key",
            "title",
            "severity",
            "status",
            "evidence_status",
            "related_case_ids",
            "owner",
            "updated_at",
        )
    }
    for run_id in defect.get("related_run_ids", []):
        try:
            stored = voc_run_store.load_voc_run(run_id)
            path = Path(stored["run_dir"]) / "defects.json"
            payload = _read(path) if path.exists() else {"run_id": run_id, "defects": []}
            rows = [
                item
                for item in payload.get("defects", [])
                if item.get("defect_id") != defect["defect_id"]
            ]
            rows.append(reference)
            payload["defects"] = rows
            payload["updated_at"] = _now_iso()
            voc_run_store._atomic_write_json(path, payload)
        except Exception:
            # 결함 원장은 저장하되, 삭제되었거나 손상된 과거 Run 링크는 건너뛴다.
            continue
