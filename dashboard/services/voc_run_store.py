from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
import zipfile
from io import BytesIO
from datetime import datetime
from pathlib import Path

from core.paths import VOC_QUALITY_RUNS_DIR
from services.voc_quality_state_model import (
    CASE_EXECUTION_STATUSES,
    RUN_LIFECYCLE_STATUSES,
    RUN_TYPES as QUALITY_RUN_TYPES,
    STATE_MODEL_VERSION,
)


SCHEMA_VERSION = "1.0"
RUN_TYPES = set(QUALITY_RUN_TYPES)
RUN_LIFECYCLE_STATUS_SET = set(RUN_LIFECYCLE_STATUSES)
CASE_STATUSES = set(CASE_EXECUTION_STATUSES)
RUN_ID_PATTERN = re.compile(r"RUN-\d{8}-\d{6}-\d{6}-[a-f0-9]{4}")
SAFE_CASE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_STORE_LOCK = threading.RLock()
_ACTIVE_RUN_IDS: set[str] = set()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def canonical_sha256(payload) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _new_run_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return f"RUN-{stamp}-{uuid.uuid4().hex[:4]}"


def _validate_run_id(run_id: str) -> str:
    run_id = str(run_id or "")
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("유효하지 않은 VOC Run ID입니다.")
    return run_id


def _run_dir(run_id: str) -> Path:
    run_id = _validate_run_id(run_id)
    root = VOC_QUALITY_RUNS_DIR.resolve()
    path = (root / run_id).resolve()
    if path.parent != root:
        raise ValueError("VOC 실행 저장 경로를 벗어날 수 없습니다.")
    return path


def _index_path() -> Path:
    return VOC_QUALITY_RUNS_DIR / "index.json"


def _safe_case_id(case_id: str) -> str:
    case_id = str(case_id or "")
    if not SAFE_CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("유효하지 않은 Case ID입니다.")
    return case_id


def _index_entry(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    summary_path = run_dir / "summary.json"
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return {
            "run_id": run_dir.name,
            "run_type": "UNKNOWN",
            "status": "ERROR",
            "started_at": "",
            "finished_at": "",
            "selected_case_ids": [],
            "counts": {"ERROR": 1},
            "integrity_error": f"{type(exc).__name__}: manifest를 읽을 수 없습니다.",
        }
    try:
        summary = _read_json(summary_path)
    except Exception:
        summary = {}
    return {
        "run_id": manifest.get("run_id", run_dir.name),
        "state_model_version": manifest.get("state_model_version", STATE_MODEL_VERSION),
        "run_type": manifest.get("run_type", "UNKNOWN"),
        "status": manifest.get("status", "ERROR"),
        "started_at": manifest.get("started_at", ""),
        "finished_at": manifest.get("finished_at", ""),
        "suite_id": manifest.get("suite_id", ""),
        "catalog_version": manifest.get("catalog_version", ""),
        "selected_case_ids": manifest.get("selected_case_ids", []),
        "judge_enabled": bool(manifest.get("judge_enabled")),
        "validity_reviewed": bool(manifest.get("validity_reviewed")),
        "parent_run_id": manifest.get("run_metadata", {}).get("parent_run_id", ""),
        "validity_state": summary.get("validity_state", "DRAFT"),
        "deployment_decision": summary.get("deployment_decision", "미판정"),
        "verification_scope": manifest.get("run_metadata", {}).get("verification_scope", {}),
        "counts": summary.get("counts", {}),
        "judge_counts": summary.get("judge_counts", {}),
    }


def rebuild_run_index() -> list[dict]:
    with _STORE_LOCK:
        VOC_QUALITY_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        entries = [
            _index_entry(path)
            for path in VOC_QUALITY_RUNS_DIR.iterdir()
            if path.is_dir() and RUN_ID_PATTERN.fullmatch(path.name)
        ]
        entries.sort(key=lambda item: item.get("started_at", ""), reverse=True)
        _atomic_write_json(
            _index_path(),
            {"schema_version": SCHEMA_VERSION, "updated_at": _now_iso(), "runs": entries},
        )
        return entries


def start_voc_run(
    *,
    run_type: str,
    selected_case_ids: list[str],
    suite_id: str,
    catalog_version: str,
    test_case_hash: str,
    rubric_versions: dict,
    model_snapshot: dict,
    judge_enabled: bool,
    environment_fingerprint: dict,
    snapshots: dict[str, object] | None = None,
    run_metadata: dict | None = None,
) -> dict:
    if run_type not in RUN_TYPES:
        raise ValueError("지원하지 않는 VOC 실행 유형입니다.")
    case_ids = [_safe_case_id(case_id) for case_id in selected_case_ids]
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("선택 Case ID는 한 건 이상이며 중복될 수 없습니다.")
    safe_snapshots = []
    for relative_name, snapshot in (snapshots or {}).items():
        name_path = Path(relative_name)
        if name_path.is_absolute() or ".." in name_path.parts:
            raise ValueError("스냅샷 경로는 실행 폴더 내부의 안전한 상대 경로여야 합니다.")
        safe_snapshots.append((name_path, snapshot))

    with _STORE_LOCK:
        VOC_QUALITY_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = ""
        run_dir = None
        for _ in range(10):
            candidate = _new_run_id()
            candidate_dir = VOC_QUALITY_RUNS_DIR / candidate
            try:
                candidate_dir.mkdir(parents=False, exist_ok=False)
                run_id, run_dir = candidate, candidate_dir
                break
            except FileExistsError:
                continue
        if not run_id or run_dir is None:
            raise RuntimeError("중복되지 않는 VOC Run ID를 생성하지 못했습니다.")

        started_at = _now_iso()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "state_model_version": STATE_MODEL_VERSION,
            "run_id": run_id,
            "run_type": run_type,
            "status": "RUNNING",
            "started_at": started_at,
            "finished_at": None,
            "suite_id": suite_id,
            "catalog_version": catalog_version,
            "test_case_hash": test_case_hash,
            "selected_case_ids": case_ids,
            "rubric_versions": rubric_versions,
            "model_snapshot": model_snapshot,
            "judge_enabled": bool(judge_enabled),
            "environment_fingerprint": environment_fingerprint,
        }
        if run_metadata:
            manifest["run_metadata"] = run_metadata
        _atomic_write_json(run_dir / "manifest.json", manifest)
        _atomic_write_json(
            run_dir / "summary.json",
            {
                "run_id": run_id,
                "state_model_version": STATE_MODEL_VERSION,
                "status": "RUNNING",
                "total": len(case_ids),
                "counts": {status: 0 for status in sorted(CASE_STATUSES)},
                "judge_counts": {
                    status: 0 for status in ("PASS", "FAIL", "REVIEW_REQUIRED", "ERROR", "NOT_RUN")
                },
                "case_results": [],
            },
        )
        _atomic_write_json(run_dir / "defects.json", {"run_id": run_id, "defects": []})
        for name_path, snapshot in safe_snapshots:
            _atomic_write_json(run_dir / "snapshots" / name_path, snapshot)
        _ACTIVE_RUN_IDS.add(run_id)
        rebuild_run_index()
        return {"run_id": run_id, "run_dir": str(run_dir), "manifest": manifest}


def update_voc_run_progress(
    run_id: str,
    case_results: list[dict],
    *,
    runtime_progress: dict | None = None,
) -> dict:
    """진행 중인 Run의 부분 결과를 원자적으로 저장합니다."""
    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        manifest = _read_json(run_dir / "manifest.json")
        if manifest.get("status") != "RUNNING":
            raise ValueError("RUNNING 상태의 VOC Run만 진행률을 갱신할 수 있습니다.")

        selected = manifest.get("selected_case_ids", [])
        normalized = []
        seen = set()
        for result in case_results:
            case_id = _safe_case_id(result.get("case_id"))
            if case_id not in selected or case_id in seen:
                raise ValueError("선택되지 않았거나 중복된 Case 결과입니다.")
            status = str(result.get("status") or "ERROR")
            if status not in CASE_STATUSES:
                raise ValueError(f"지원하지 않는 Case 상태입니다: {status}")
            seen.add(case_id)
            normalized.append(
                {
                    "case_id": case_id,
                    "status": status,
                    "mode": result.get("mode", ""),
                    "trace_id": result.get("trace_id", ""),
                    "started_at": result.get("started_at", ""),
                    "finished_at": result.get("finished_at", ""),
                    "message": result.get("message", ""),
                    "attempt_count": int(result.get("attempt_count") or 0),
                    "judge_status": result.get("judge_status", "NOT_RUN"),
                    "judge_score": result.get("judge_score"),
                    "judge_independence_grade": result.get("judge_independence_grade", ""),
                }
            )

        counts = {status: 0 for status in sorted(CASE_STATUSES)}
        for item in normalized:
            counts[item["status"]] += 1
        judge_counts = {status: 0 for status in ("PASS", "FAIL", "REVIEW_REQUIRED", "ERROR", "NOT_RUN")}
        for item in normalized:
            judge_status = item.get("judge_status", "NOT_RUN")
            if judge_status in judge_counts:
                judge_counts[judge_status] += 1
        summary = {
            "run_id": run_id,
            "state_model_version": manifest.get("state_model_version", STATE_MODEL_VERSION),
            "status": "RUNNING",
            "total": len(selected),
            "completed": len(normalized),
            "counts": counts,
            "judge_counts": judge_counts,
            "case_results": normalized,
            "updated_at": _now_iso(),
        }
        previous_summary = _read_json(run_dir / "summary.json")
        current_runtime = previous_summary.get("runtime_progress", {})
        if runtime_progress is not None:
            current_runtime = {
                **current_runtime,
                **runtime_progress,
                "updated_at": _now_iso(),
            }
        if current_runtime:
            summary["runtime_progress"] = current_runtime
        _atomic_write_json(run_dir / "summary.json", summary)
        rebuild_run_index()
        return summary


def save_case_artifacts(
    run_id: str,
    case_id: str,
    *,
    pipeline_result: dict,
    trace: dict,
    rule_result: dict,
    judge_result: dict | None = None,
) -> dict:
    run_dir = _run_dir(run_id)
    case_id = _safe_case_id(case_id)
    manifest = _read_json(run_dir / "manifest.json")
    if case_id not in manifest.get("selected_case_ids", []):
        raise ValueError("실행 manifest에 없는 Case ID입니다.")
    case_dir = run_dir / "cases" / case_id
    _atomic_write_json(case_dir / "pipeline_result.json", pipeline_result)
    _atomic_write_json(case_dir / "trace.json", trace)
    _atomic_write_json(case_dir / "rule_result.json", rule_result)
    if judge_result is not None:
        _atomic_write_json(case_dir / "judge_result.json", judge_result)
    return {"case_dir": str(case_dir)}


def complete_voc_run(run_id: str, case_results: list[dict], *, lifecycle_status: str | None = None) -> dict:
    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        manifest = _read_json(run_dir / "manifest.json")
        normalized = []
        for result in case_results:
            case_id = _safe_case_id(result.get("case_id"))
            status = str(result.get("status") or "ERROR")
            if status not in CASE_STATUSES:
                raise ValueError(f"지원하지 않는 Case 상태입니다: {status}")
            normalized.append(
                {
                    "case_id": case_id,
                    "status": status,
                    "mode": result.get("mode", ""),
                    "trace_id": result.get("trace_id", ""),
                    "started_at": result.get("started_at", ""),
                    "finished_at": result.get("finished_at", ""),
                    "message": result.get("message", ""),
                    "attempt_count": int(result.get("attempt_count") or 0),
                    "judge_status": result.get("judge_status", "NOT_RUN"),
                    "judge_score": result.get("judge_score"),
                    "judge_independence_grade": result.get("judge_independence_grade", ""),
                }
            )
        result_ids = {item["case_id"] for item in normalized}
        for case_id in manifest.get("selected_case_ids", []):
            if case_id not in result_ids:
                normalized.append(
                    {
                        "case_id": case_id,
                        "status": "NOT_RUN",
                        "mode": "",
                        "trace_id": "",
                        "started_at": "",
                        "finished_at": "",
                        "message": "실행 결과가 생성되지 않았습니다.",
                        "attempt_count": 0,
                        "judge_status": "NOT_RUN",
                        "judge_score": None,
                        "judge_independence_grade": "",
                    }
                )
        counts = {status: 0 for status in sorted(CASE_STATUSES)}
        for item in normalized:
            counts[item["status"]] += 1
        judge_counts = {status: 0 for status in ("PASS", "FAIL", "REVIEW_REQUIRED", "ERROR", "NOT_RUN")}
        for item in normalized:
            judge_status = item.get("judge_status", "NOT_RUN")
            if judge_status in judge_counts:
                judge_counts[judge_status] += 1
        if lifecycle_status is None:
            lifecycle_status = "ERROR" if counts["ERROR"] else "COMPLETED"
        if lifecycle_status not in RUN_LIFECYCLE_STATUS_SET:
            raise ValueError(f"지원하지 않는 Run lifecycle 상태입니다: {lifecycle_status}")
        finished_at = _now_iso()
        manifest["status"] = lifecycle_status
        manifest["finished_at"] = finished_at
        _atomic_write_json(run_dir / "manifest.json", manifest)
        summary = {
            "run_id": run_id,
            "state_model_version": manifest.get("state_model_version", STATE_MODEL_VERSION),
            "status": lifecycle_status,
            "total": len(normalized),
            "counts": counts,
            "judge_counts": judge_counts,
            "case_results": normalized,
            "finished_at": finished_at,
            "validity_state": "DRAFT",
            "deployment_decision": "미판정",
        }
        _atomic_write_json(run_dir / "summary.json", summary)
        _ACTIVE_RUN_IDS.discard(run_id)
        rebuild_run_index()
        return {"manifest": manifest, "summary": summary, "run_dir": str(run_dir)}


def recover_incomplete_runs() -> list[str]:
    recovered = []
    with _STORE_LOCK:
        if not VOC_QUALITY_RUNS_DIR.exists():
            return recovered
        for run_dir in VOC_QUALITY_RUNS_DIR.iterdir():
            if not run_dir.is_dir() or not RUN_ID_PATTERN.fullmatch(run_dir.name):
                continue
            if run_dir.name in _ACTIVE_RUN_IDS:
                continue
            manifest_path = run_dir / "manifest.json"
            try:
                manifest = _read_json(manifest_path)
            except Exception:
                continue
            if manifest.get("status") != "RUNNING":
                continue
            case_results = []
            summary_path = run_dir / "summary.json"
            try:
                case_results = _read_json(summary_path).get("case_results", [])
            except Exception:
                case_results = []
            complete_voc_run(run_dir.name, case_results, lifecycle_status="INTERRUPTED")
            recovered.append(run_dir.name)
        rebuild_run_index()
    return recovered


def list_voc_runs(*, recover: bool = False) -> list[dict]:
    """Run 목록을 조회합니다. 복구는 다른 프로세스의 실행을 보호하기 위해 명시적으로만 수행합니다."""
    if recover:
        recover_incomplete_runs()
    index_path = _index_path()
    if not index_path.exists():
        return rebuild_run_index()
    try:
        return _read_json(index_path).get("runs", [])
    except Exception:
        return rebuild_run_index()


def load_voc_run(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    result = {"run_id": run_id, "run_dir": str(run_dir)}
    for name in ("manifest", "summary", "defects"):
        path = run_dir / f"{name}.json"
        try:
            result[name] = _read_json(path)
        except Exception as exc:
            result.setdefault("errors", []).append(f"{name}: {type(exc).__name__}")
    plan_path = run_dir / "rubric_reevaluation_plan.json"
    if plan_path.exists():
        try:
            result["rubric_reevaluation_plan"] = _read_json(plan_path)
        except Exception as exc:
            result.setdefault("errors", []).append(f"rubric_reevaluation_plan: {type(exc).__name__}")
    return result


def load_rubric_reevaluation_plan(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    path = run_dir / "rubric_reevaluation_plan.json"
    if not path.exists():
        return {}
    return _read_json(path)


def save_rubric_reevaluation_plan(run_id: str, plan: dict) -> dict:
    """Store a run-level Rubric reevaluation plan without mutating case results."""
    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        manifest = _read_json(run_dir / "manifest.json")
        summary = _read_json(run_dir / "summary.json")
        if manifest.get("status") == "RUNNING":
            raise ValueError("실행 중인 Run에는 Rubric 재평가 계획을 저장할 수 없습니다.")

        path = run_dir / "rubric_reevaluation_plan.json"
        history = []
        if path.exists():
            previous = _read_json(path)
            history.extend(previous.pop("plan_history", []))
            history.append(previous)

        saved = dict(plan or {})
        saved["run_id"] = run_id
        saved["saved_at"] = _now_iso()
        saved["plan_history"] = history
        _atomic_write_json(path, saved)

        metadata = manifest.setdefault("run_metadata", {})
        metadata["rubric_reevaluation"] = {
            "status": saved.get("status", ""),
            "recommendation": saved.get("recommendation", ""),
            "changed_scopes": saved.get("changed_scopes", []),
            "saved_at": saved["saved_at"],
            "plan_file": path.name,
        }
        _atomic_write_json(run_dir / "manifest.json", manifest)
        rebuild_run_index()
        return {"manifest": manifest, "summary": summary, "plan": saved}


def load_case_artifacts(run_id: str, case_id: str) -> dict:
    run_dir = _run_dir(run_id)
    case_id = _safe_case_id(case_id)
    case_dir = run_dir / "cases" / case_id
    result = {"run_id": run_id, "case_id": case_id, "case_dir": str(case_dir)}
    for name in (
        "pipeline_result",
        "trace",
        "rule_result",
        "judge_result",
        "validity_supplement",
        "validity_result",
    ):
        path = case_dir / f"{name}.json"
        if not path.exists():
            continue
        try:
            result[name] = _read_json(path)
        except Exception as exc:
            result.setdefault("errors", []).append(f"{name}: {type(exc).__name__}")
    return result


def verify_run_integrity(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    errors = []
    warnings = []
    manifest = {}
    summary = {}
    for name in ("manifest", "summary", "defects"):
        path = run_dir / f"{name}.json"
        if not path.exists():
            errors.append(f"필수 파일 누락: {name}.json")
            continue
        try:
            payload = _read_json(path)
            if name == "manifest":
                manifest = payload
            elif name == "summary":
                summary = payload
        except Exception as exc:
            errors.append(f"JSON 손상: {name}.json ({type(exc).__name__})")

    selected = manifest.get("selected_case_ids", [])
    metadata = manifest.get("run_metadata", {}) if isinstance(manifest.get("run_metadata"), dict) else {}
    verification_scope = (
        metadata.get("verification_scope")
        if isinstance(metadata.get("verification_scope"), dict)
        else {}
    )
    pending_case_ids = {
        str(case_id)
        for case_id in verification_scope.get("pending_case_ids", [])
        if case_id
    }
    results = summary.get("case_results", [])
    result_ids = [item.get("case_id") for item in results]
    if len(result_ids) != len(set(result_ids)):
        errors.append("summary에 중복 Case 결과가 있습니다.")
    if any(case_id not in selected for case_id in result_ids):
        errors.append("선택 목록에 없는 Case 결과가 있습니다.")
    if manifest.get("status") != "RUNNING" and set(result_ids) != set(selected):
        errors.append("완료 Run의 선택 Case와 결과 Case가 일치하지 않습니다.")
    if manifest.get("status") == "RUNNING" and len(results) < len(selected):
        warnings.append(f"실행 중 부분 결과: {len(results)}/{len(selected)}건")

    counted = {status: 0 for status in CASE_STATUSES}
    for item in results:
        status = item.get("status")
        if status not in CASE_STATUSES:
            errors.append(f"지원하지 않는 Case 상태: {status}")
        else:
            counted[status] += 1
        case_id = item.get("case_id")
        if not case_id:
            continue
        case_dir = run_dir / "cases" / str(case_id)
        for filename in ("pipeline_result.json", "trace.json", "rule_result.json"):
            if not (case_dir / filename).exists():
                errors.append(f"Case 증적 누락: {case_id}/{filename}")
        scope_pending = str(case_id) in pending_case_ids
        if manifest.get("judge_enabled") and not scope_pending and not (case_dir / "judge_result.json").exists():
            errors.append(f"독립 LLM 평가 증적 누락: {case_id}/judge_result.json")
        if manifest.get("validity_reviewed") and not scope_pending and not (case_dir / "validity_result.json").exists():
            errors.append(f"개선안 타당성 평가 증적 누락: {case_id}/validity_result.json")
    stored_counts = summary.get("counts", {})
    if any(int(stored_counts.get(status, 0)) != counted[status] for status in CASE_STATUSES):
        errors.append("summary 상태별 건수와 Case 결과 집계가 일치하지 않습니다.")

    index_entries = list_voc_runs(recover=False)
    index_entry = next((item for item in index_entries if item.get("run_id") == run_id), None)
    if not index_entry:
        errors.append("중앙 index에 Run이 없습니다.")
    elif index_entry.get("status") != manifest.get("status"):
        errors.append("index와 manifest의 lifecycle 상태가 일치하지 않습니다.")
    return {
        "run_id": run_id,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "selected_count": len(selected),
        "result_count": len(results),
        "checked_at": _now_iso(),
    }


def build_run_evidence_zip(run_id: str) -> bytes:
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"VOC Run을 찾을 수 없습니다: {run_id}")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                archive.write(path, arcname=str(Path(run_id) / path.relative_to(run_dir)))
    return buffer.getvalue()


def save_judge_reevaluation(run_id: str, case_id: str, judge_result: dict) -> dict:
    """동일 Agent 파이프라인 결과의 독립 LLM 재평가를 이전 결과와 함께 보존합니다."""
    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        case_id = _safe_case_id(case_id)
        manifest = _read_json(run_dir / "manifest.json")
        summary = _read_json(run_dir / "summary.json")
        if manifest.get("status") == "RUNNING":
            raise ValueError("실행 중인 Run은 독립 LLM 재평가할 수 없습니다.")
        case_dir = run_dir / "cases" / case_id
        pipeline_path = case_dir / "pipeline_result.json"
        if not pipeline_path.exists():
            raise FileNotFoundError("독립 LLM 재평가에 필요한 Agent 파이프라인 증적이 없습니다.")

        judge_path = case_dir / "judge_result.json"
        history = []
        if judge_path.exists():
            previous = _read_json(judge_path)
            history.extend(previous.pop("evaluation_history", []))
            history.append(previous)
        saved = dict(judge_result)
        saved["evaluation_history"] = history
        _atomic_write_json(judge_path, saved)

        target = next(
            (item for item in summary.get("case_results", []) if item.get("case_id") == case_id),
            None,
        )
        if target is None:
            raise ValueError("summary에 독립 LLM 재평가 대상 Case가 없습니다.")
        decision = saved.get("decision", "ERROR")
        target["judge_status"] = decision
        target["judge_score"] = saved.get("total_score")
        target["judge_independence_grade"] = saved.get("independence_grade", "")
        if target.get("status") != "ERROR" and decision in {"PASS", "FAIL", "REVIEW_REQUIRED"}:
            target["status"] = decision

        counts = {status: 0 for status in sorted(CASE_STATUSES)}
        judge_counts = {status: 0 for status in ("PASS", "FAIL", "REVIEW_REQUIRED", "ERROR", "NOT_RUN")}
        for item in summary.get("case_results", []):
            counts[item.get("status", "ERROR")] += 1
            judge_status = item.get("judge_status", "NOT_RUN")
            if judge_status in judge_counts:
                judge_counts[judge_status] += 1
        summary["counts"] = counts
        summary["judge_counts"] = judge_counts
        summary["judge_updated_at"] = _now_iso()
        _atomic_write_json(run_dir / "summary.json", summary)

        manifest["judge_enabled"] = True
        manifest.setdefault("model_snapshot", {})["judge"] = {
            "enabled": True,
            "provider": saved.get("provider", ""),
            "model": saved.get("model", ""),
        }
        _atomic_write_json(run_dir / "manifest.json", manifest)
        rebuild_run_index()
        return {"manifest": manifest, "summary": summary, "judge_result": saved}


def save_validity_supplement(run_id: str, case_id: str, supplement: dict) -> dict:
    """Store user-provided improvement validity evidence without changing the source Agent pipeline result."""
    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        case_id = _safe_case_id(case_id)
        manifest = _read_json(run_dir / "manifest.json")
        summary = _read_json(run_dir / "summary.json")
        if manifest.get("status") == "RUNNING":
            raise ValueError("실행 중인 Run에는 개선안 타당성 평가 보완 입력을 저장할 수 없습니다.")
        case_dir = run_dir / "cases" / case_id
        if not (case_dir / "pipeline_result.json").exists():
            raise FileNotFoundError("개선안 타당성 평가 보완 입력에 필요한 Agent 파이프라인 증적이 없습니다.")

        saved = dict(supplement or {})
        saved["run_id"] = run_id
        saved["case_id"] = case_id
        saved["updated_at"] = _now_iso()
        path = case_dir / "validity_supplement.json"
        _atomic_write_json(path, saved)
        return {
            "manifest": manifest,
            "summary": summary,
            "validity_supplement": saved,
            "case_dir": str(case_dir),
        }


def save_validity_evaluation(run_id: str, case_id: str, validity_result: dict) -> dict:
    """개선안 타당성 재평가를 보존하고 사람 검토 이력은 이어받습니다."""
    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        case_id = _safe_case_id(case_id)
        manifest = _read_json(run_dir / "manifest.json")
        summary = _read_json(run_dir / "summary.json")
        if manifest.get("status") == "RUNNING":
            raise ValueError("실행 중인 Run은 개선안 타당성 평가를 수행할 수 없습니다.")
        case_dir = run_dir / "cases" / case_id
        if not (case_dir / "pipeline_result.json").exists():
            raise FileNotFoundError("개선안 타당성 평가에 필요한 Agent 파이프라인 증적이 없습니다.")

        path = case_dir / "validity_result.json"
        evaluation_history = []
        human_reviews = []
        if path.exists():
            previous = _read_json(path)
            previous_evaluations = previous.pop("evaluation_history", [])
            previous_reviews = previous.pop("human_reviews", [])
            if isinstance(previous_evaluations, list):
                evaluation_history.extend(previous_evaluations)
            if isinstance(previous_reviews, list):
                human_reviews = previous_reviews
            evaluation_history.append(previous)
        saved = dict(validity_result)
        saved["evaluation_history"] = evaluation_history
        saved["human_reviews"] = human_reviews
        saved["evaluation_sequence"] = len(evaluation_history) + 1
        if human_reviews:
            saved["approval_history_preserved"] = True
            saved["approval_reset_reason"] = (
                "개선안 타당성 재평가로 기존 사람 검토는 감사 이력으로 보존하고, "
                "최신 평가 결과 기준으로 QA·업무 승인 단계를 다시 진행합니다."
            )
        _atomic_write_json(path, saved)

        target = next(
            (item for item in summary.get("case_results", []) if item.get("case_id") == case_id),
            None,
        )
        if target is None:
            raise ValueError("summary에 개선안 타당성 평가 대상 Case가 없습니다.")
        target["validity_status"] = saved.get("decision", "ERROR")
        target["validity_score"] = saved.get("total_score")
        target["approval_state"] = saved.get("workflow_state", "DRAFT")
        target["formal_approval"] = bool(saved.get("formal_approval"))
        immediate_holds = saved.get("immediate_hold_rules_triggered") or []
        if isinstance(immediate_holds, str):
            immediate_hold_count = 1 if immediate_holds.strip() else 0
        else:
            try:
                immediate_hold_count = len(immediate_holds)
            except TypeError:
                immediate_hold_count = int(bool(immediate_holds))
        target["immediate_hold_count"] = immediate_hold_count
        target["validity_evaluation_count"] = saved["evaluation_sequence"]
        _refresh_validity_summary(summary, manifest)
        _atomic_write_json(run_dir / "summary.json", summary)

        manifest["validity_reviewed"] = True
        _atomic_write_json(run_dir / "manifest.json", manifest)
        rebuild_run_index()
        return {"manifest": manifest, "summary": summary, "validity_result": saved}


def apply_validity_human_review(
    run_id: str,
    case_id: str,
    *,
    reviewer_role: str,
    reviewer_name_or_id: str,
    decision: str,
    comment: str,
) -> dict:
    """QA와 업무 담당자의 순차 결정을 append-only 감사 이력으로 저장합니다."""
    role = str(reviewer_role or "").upper()
    decision = str(decision or "").upper()
    reviewer = str(reviewer_name_or_id or "").strip()
    comment = str(comment or "").strip()
    if role not in {"QA", "BUSINESS"}:
        raise ValueError("검토자 역할은 QA 또는 BUSINESS여야 합니다.")
    if decision not in {"APPROVE", "REVISION_REQUIRED", "REJECTED"}:
        raise ValueError("지원하지 않는 사람 검토 결정입니다.")
    if not reviewer or len(reviewer) > 100:
        raise ValueError("검토자 이름 또는 ID를 100자 이내로 입력하세요.")
    if not comment or len(comment) > 1000:
        raise ValueError("검토 의견을 1~1,000자로 입력하세요.")

    with _STORE_LOCK:
        run_dir = _run_dir(run_id)
        case_id = _safe_case_id(case_id)
        manifest = _read_json(run_dir / "manifest.json")
        summary = _read_json(run_dir / "summary.json")
        path = run_dir / "cases" / case_id / "validity_result.json"
        if not path.exists():
            raise FileNotFoundError("개선안 타당성 평가를 먼저 수행하세요.")
        payload = _read_json(path)
        current = payload.get("workflow_state", "DRAFT")
        if payload.get("decision") != "AI_PASS" or payload.get("immediate_hold_rules_triggered"):
            raise ValueError("AI_PASS이고 즉시 보류 규칙이 없는 개선안만 사람 승인할 수 있습니다.")
        if role == "QA" and current != "AI_REVIEWED":
            raise ValueError("QA 검토는 AI_REVIEWED 상태에서 한 번만 수행할 수 있습니다.")
        if role == "BUSINESS" and current != "QA_REVIEWED":
            raise ValueError("업무 승인은 QA_REVIEWED 이후에만 수행할 수 있습니다.")

        if decision == "APPROVE":
            next_state = "QA_REVIEWED" if role == "QA" else "BUSINESS_APPROVED"
        else:
            next_state = decision
        review = {
            "reviewer_role": role,
            "reviewer_name_or_id": reviewer,
            "reviewed_at": _now_iso(),
            "decision": decision,
            "comment": comment,
            "from_state": current,
            "to_state": next_state,
        }
        payload.setdefault("human_reviews", []).append(review)
        payload["workflow_state"] = next_state
        payload["formal_approval"] = next_state == "BUSINESS_APPROVED"
        payload["updated_at"] = _now_iso()
        _atomic_write_json(path, payload)

        target = next(
            (item for item in summary.get("case_results", []) if item.get("case_id") == case_id),
            None,
        )
        if target is None:
            raise ValueError("summary에 사람 검토 대상 Case가 없습니다.")
        target["approval_state"] = next_state
        target["formal_approval"] = payload["formal_approval"]
        _refresh_validity_summary(summary, manifest)
        _atomic_write_json(run_dir / "summary.json", summary)
        rebuild_run_index()
        return {"summary": summary, "validity_result": payload, "review": review}


def _refresh_validity_summary(summary: dict, manifest: dict | None = None) -> None:
    all_cases = summary.get("case_results", [])
    metadata = manifest.get("run_metadata", {}) if isinstance(manifest, dict) else {}
    verification_scope = (
        metadata.get("verification_scope")
        if isinstance(metadata.get("verification_scope"), dict)
        else {}
    )
    executable_ids = {
        str(case_id)
        for case_id in verification_scope.get("executable_case_ids", [])
        if case_id
    }
    scoped_cases = [
        item for item in all_cases
        if not executable_ids or str(item.get("case_id") or "") in executable_ids
    ]
    reviewed = [item for item in scoped_cases if item.get("validity_status")]
    states = [item.get("approval_state", "DRAFT") for item in reviewed]
    formally_approved = sum(bool(item.get("formal_approval")) for item in reviewed)
    if scoped_cases and formally_approved == len(scoped_cases):
        validity_state = "BUSINESS_APPROVED"
        deployment = "FORMAL_QUALITY_APPROVED"
    elif formally_approved:
        validity_state = "PARTIALLY_APPROVED"
        deployment = "REMAINING_CASE_REVIEW_REQUIRED"
    elif "REJECTED" in states:
        validity_state = "REJECTED"
        deployment = "REJECTED"
    elif "REVISION_REQUIRED" in states:
        validity_state = "REVISION_REQUIRED"
        deployment = "REVISION_REQUIRED"
    elif "QA_REVIEWED" in states:
        validity_state = "QA_REVIEWED"
        deployment = "BUSINESS_REVIEW_REQUIRED"
    elif "AI_REVIEWED" in states:
        validity_state = "AI_REVIEWED"
        deployment = "HUMAN_REVIEW_REQUIRED"
    else:
        validity_state = "DRAFT"
        deployment = "미판정"
    summary["validity_state"] = validity_state
    summary["deployment_decision"] = deployment
    summary["validity_counts"] = {
        state: states.count(state)
        for state in (
            "DRAFT", "AI_REVIEWED", "QA_REVIEWED", "BUSINESS_APPROVED",
            "REVISION_REQUIRED", "REJECTED",
        )
    }
    summary["validity_scope"] = {
        "basis": "실행 가능 Case 기준",
        "eligible_count": len(scoped_cases),
        "excluded_pending_count": max(len(all_cases) - len(scoped_cases), 0),
    }
    summary["validity_updated_at"] = _now_iso()


def delete_voc_runs(run_ids: list[str]) -> dict:
    """완료된 Run 폴더와 index 항목을 함께 삭제합니다. RUNNING Run은 거부합니다."""
    unique_ids = list(dict.fromkeys(_validate_run_id(run_id) for run_id in run_ids))
    if not unique_ids:
        raise ValueError("삭제할 Run을 선택하세요.")
    with _STORE_LOCK:
        targets = []
        for run_id in unique_ids:
            run_dir = _run_dir(run_id)
            if not run_dir.exists():
                raise FileNotFoundError(f"VOC Run을 찾을 수 없습니다: {run_id}")
            manifest = _read_json(run_dir / "manifest.json")
            if manifest.get("status") == "RUNNING":
                raise ValueError(f"실행 중인 Run은 삭제할 수 없습니다: {run_id}")
            targets.append((run_id, run_dir))

        staged = []
        try:
            for run_id, run_dir in targets:
                staged_dir = run_dir.with_name(f".deleting-{run_id}-{uuid.uuid4().hex[:8]}")
                os.replace(run_dir, staged_dir)
                staged.append((run_dir, staged_dir))
            rebuild_run_index()
            for _, staged_dir in staged:
                shutil.rmtree(staged_dir)
        except Exception:
            for original, staged_dir in reversed(staged):
                if staged_dir.exists() and not original.exists():
                    os.replace(staged_dir, original)
            rebuild_run_index()
            raise
        return {"deleted_run_ids": unique_ids, "deleted_count": len(unique_ids)}
