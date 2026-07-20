from __future__ import annotations

import json
import hashlib
import locale
import os
import platform
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from core.paths import VOC_REPORTS_DIR, VOC_REUSE_DOCS_DIR, VOC_RUNTIME_DIR
from services import (
    voc_acceptance_service,
    voc_defect_service,
    voc_judge_service,
    voc_report_service,
    voc_run_store,
    voc_validity_service,
)


REPORT_CATEGORIES = {
    "종합 Summary": "Summary",
    "정의 검증 Validation": "Validation",
    "장애 진단 Fault": "Fault",
    "Agent 연결 A2A": "A2A",
    "VOC 분석 결과": "VOC",
}
DIAGNOSTIC_MODES = {"all", "validation", "fault", "a2a"}
AGENT_ACTIONS = {"init", "start", "status", "stop", "restart"}
FAULT_TEST_CASES = {"TC-19": "FT-01", "TC-20": "FT-03"}
DIRECT_FAULT_CASE_IDS = {f"FT-{number:02d}" for number in range(1, 7)}
TRANSIENT_ERROR_MARKERS = (
    "429", "rate limit", "rate_limit", "too many requests", "timeout",
    "timed out", "deadline_exceeded", "deadline exceeded",
)
_BATCH_LOCK = threading.RLock()
_ACTIVE_BATCH_SIGNATURES: dict[tuple[str, ...], str] = {}
_BATCH_STOP_EVENTS: dict[str, threading.Event] = {}
AGENT_DEFINITIONS = (
    ("interpreter", "Interpreter", 6101),
    ("retriever", "Retriever", 6102),
    ("summarizer", "Summarizer", 6103),
    ("evaluator", "Evaluator", 6104),
    ("critic", "Critic", 6105),
    ("improver", "Improver", 6106),
)
REQUIRED_A2A_LINKS = (
    ("Orchestrator", "Interpreter"),
    ("Orchestrator", "Summarizer"),
    ("Summarizer", "Retriever"),
    ("Retriever", "Summarizer"),
    ("Summarizer", "Evaluator"),
    ("Summarizer", "Critic"),
    ("Summarizer", "Improver"),
)
SECRET_PATTERNS = (
    re.compile(r"sk-proj-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{12,}"),
    re.compile(r"tvly-[A-Za-z0-9_-]{12,}"),
)
PERSONAL_DATA_PATTERNS = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)"), "[REDACTED_PERSONAL_ID]"),
)
QUALITY_RUBRIC_SPECS = {
    "internal_pipeline": {
        "relative_path": "quality_diagnosis/system_quality_rubric.json",
        "items_key": "categories",
        "decisions_key": "deployment_decisions",
        "hold_rules_key": "immediate_deployment_hold",
        "decision_min_key": "min",
        "decision_max_key": "max",
    },
    "independent_judge": {
        "relative_path": "quality_diagnosis/independent_judge_rubric.json",
        "items_key": "dimensions",
        "decisions_key": "decisions",
        "hold_rules_key": "immediate_fail_rules",
        "decision_min_key": "min_score",
        "decision_max_key": "max_score",
        "rubric_id": "VOC-INDEPENDENT-JUDGE-100",
    },
    "improvement_validity": {
        "relative_path": "quality_diagnosis/improvement_validity_rubric.json",
        "items_key": "dimensions",
        "decisions_key": "automatic_decisions",
        "hold_rules_key": "immediate_hold_rules",
        "decision_min_key": "min_score",
        "decision_max_key": "max_score",
        "rubric_id": "VOC-IMPROVEMENT-VALIDITY-100",
    },
}


def _safe_text(value: str) -> str:
    text = value or ""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_CREDENTIAL]", text)
    return text


def runtime_health() -> dict:
    required = [
        VOC_RUNTIME_DIR / "agents",
        VOC_RUNTIME_DIR / "scripts" / "agents.cmd",
        VOC_RUNTIME_DIR / "scripts" / "quality-diagnosis.cmd",
        VOC_RUNTIME_DIR / "quality_diagnosis" / "test_cases.json",
        VOC_RUNTIME_DIR / "quality_diagnosis" / "system_quality_rubric.json",
        VOC_RUNTIME_DIR / "quality_diagnosis" / "quality_test_catalog.json",
        VOC_RUNTIME_DIR / "quality_diagnosis" / "independent_judge_rubric.json",
        VOC_RUNTIME_DIR / "quality_diagnosis" / "improvement_validity_rubric.json",
        VOC_RUNTIME_DIR / "quality_diagnosis" / "quality_evidence_contract.json",
        VOC_RUNTIME_DIR / "voc.csv",
    ]
    missing = [str(path.relative_to(VOC_RUNTIME_DIR)) for path in required if not path.exists()]
    runtime_env_file = VOC_RUNTIME_DIR / ".env"
    workspace_env_file = VOC_RUNTIME_DIR.parent / ".env"
    env_file = (
        runtime_env_file
        if runtime_env_file.exists()
        else workspace_env_file if workspace_env_file.exists() else None
    )
    return {
        "ok": not missing,
        "runtime_dir": str(VOC_RUNTIME_DIR),
        "reports_dir": str(VOC_REPORTS_DIR),
        "missing": missing,
        "env_configured": env_file is not None,
        "env_file": str(env_file) if env_file else "",
        "env_source": (
            "runtime" if env_file == runtime_env_file
            else "workspace" if env_file == workspace_env_file
            else "missing"
        ),
    }


def _run_cmd(script: Path, argument: str | list[str], timeout: int) -> dict:
    if not script.exists():
        return {"ok": False, "return_code": -1, "output": f"실행 파일 없음: {script}", "duration_seconds": 0}

    arguments = [argument] if isinstance(argument, str) else list(argument)
    command = [str(script), *arguments]
    if os.name == "nt":
        command = ["cmd.exe", "/d", "/c", str(script), *arguments]

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=VOC_RUNTIME_DIR,
            capture_output=True,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        return {
            "ok": completed.returncode == 0,
            "return_code": completed.returncode,
            "output": _safe_text(output or "출력 없음"),
            "duration_seconds": round(time.perf_counter() - started, 2),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "return_code": -2,
            "output": f"허용시간 {timeout}초를 초과해 UI 실행을 중단했습니다. 런타임 로그를 확인하세요.",
            "duration_seconds": round(time.perf_counter() - started, 2),
        }
    except Exception as exc:
        return {
            "ok": False,
            "return_code": -3,
            "output": _safe_text(f"{type(exc).__name__}: {exc}"),
            "duration_seconds": round(time.perf_counter() - started, 2),
        }


def run_agent_action(action: str, agent_name: str | None = None) -> dict:
    if action not in AGENT_ACTIONS:
        raise ValueError(f"허용되지 않은 Agent 명령: {action}")
    arguments = [action]
    if agent_name:
        allowed_agents = {item[0] for item in AGENT_DEFINITIONS}
        if agent_name not in allowed_agents:
            raise ValueError(f"허용되지 않은 Agent 이름: {agent_name}")
        if action == "init":
            raise ValueError("환경 파일 초기화는 개별 Agent를 지정할 수 없습니다.")
        arguments.append(agent_name)
    return _run_cmd(VOC_RUNTIME_DIR / "scripts" / "agents.cmd", arguments, timeout=40)


def parse_agent_status_output(output: str) -> list[dict]:
    """agents.ps1의 상태 출력을 화면용 구조로 변환합니다."""
    parsed = {}
    pattern = re.compile(
        r"^(?P<name>[a-z]+)\s+port=(?P<port>\d+)\s+pid=(?P<pid>\S+)"
        r"(?:\s+started_at=(?P<started_at>\S+))?\s+status=(?P<status>.+)$",
        re.MULTILINE,
    )
    for match in pattern.finditer(output or ""):
        parsed[match.group("name")] = match.groupdict()

    rows = []
    for key, label, port in AGENT_DEFINITIONS:
        item = parsed.get(key, {})
        status = item.get("status", "UNKNOWN").strip()
        rows.append({
            "key": key,
            "name": label,
            "port": int(item.get("port", port)),
            "pid": item.get("pid", "-"),
            "started_at": item.get("started_at") or "",
            "status": status,
            "healthy": status == "RUNNING",
        })
    return rows


def agent_status_snapshot() -> dict:
    result = run_agent_action("status")
    agents = parse_agent_status_output(result.get("output", ""))
    running = sum(agent["healthy"] for agent in agents)
    return {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agents": agents,
        "running": running,
        "total": len(agents),
        "all_running": result.get("ok", False) and running == len(agents),
        "command_ok": result.get("ok", False),
        "error": "" if result.get("ok") else result.get("output", "상태 조회 실패"),
    }


def _read_recent_audit_events(max_bytes: int = 2_000_000) -> tuple[Path, list[dict]]:
    path = VOC_RUNTIME_DIR / ".runtime" / "audit" / "a2a_events.jsonl"
    if not path.exists():
        return path, []
    with path.open("rb") as stream:
        size = stream.seek(0, os.SEEK_END)
        start = max(0, size - max_bytes)
        stream.seek(start)
        if start:
            stream.readline()
        text = stream.read().decode("utf-8-sig", errors="replace")
    events = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("trace_id"):
            events.append(event)
    return path, events


def summarize_a2a_events(events: list[dict], recent_minutes: int = 30) -> dict:
    grouped = defaultdict(list)
    for event in events:
        grouped[event.get("trace_id")].append(event)

    traces = []
    required = set(REQUIRED_A2A_LINKS)
    for trace_id, trace_events in grouped.items():
        ordered = sorted(trace_events, key=lambda item: item.get("timestamp", ""))
        successful_links = {
            (item.get("source"), item.get("target"))
            for item in ordered
            if item.get("status") == "success"
        }
        failed = [item for item in ordered if item.get("status") == "failure"]
        traces.append({
            "trace_id": trace_id,
            "timestamp": ordered[-1].get("timestamp", ""),
            "events": len(ordered),
            "success": sum(item.get("status") == "success" for item in ordered),
            "failure": len(failed),
            "duration_ms": round(sum(float(item.get("duration_ms", 0) or 0) for item in ordered), 2),
            "successful_links": successful_links,
            "missing_links": required - successful_links,
            "complete": not failed and required.issubset(successful_links),
            "items": ordered,
        })
    traces.sort(key=lambda item: item["timestamp"], reverse=True)

    cutoff = datetime.now().astimezone() - timedelta(minutes=recent_minutes)
    recent_traces = []
    for trace in traces:
        try:
            observed_at = datetime.fromisoformat(trace["timestamp"])
        except (TypeError, ValueError):
            continue
        if observed_at >= cutoff:
            recent_traces.append(trace)

    recent_complete = next((trace for trace in recent_traces if trace["complete"]), None)
    latest = traces[0] if traces else None
    latest_recent = recent_traces[0] if recent_traces else None
    if recent_complete:
        decision = "PASS"
        reason = "최근 완전 Trace에서 필수 gRPC 연결과 데이터 전달이 모두 성공했습니다."
        evidence = recent_complete
    elif latest_recent and latest_recent["failure"]:
        decision = "FAIL"
        reason = "최근 Trace에 gRPC 호출 실패가 기록돼 있습니다."
        evidence = latest_recent
    else:
        decision = "NOT_VERIFIED"
        reason = f"최근 {recent_minutes}분 안에 전체 연결을 통과한 완전 Trace가 없습니다."
        evidence = latest_recent or latest
    return {
        "decision": decision,
        "reason": reason,
        "recent_minutes": recent_minutes,
        "latest": latest,
        "evidence": evidence,
        "traces": traces[:20],
        "events": len(events),
    }


def a2a_trace_snapshot(recent_minutes: int = 30) -> dict:
    path, events = _read_recent_audit_events()
    summary = summarize_a2a_events(events, recent_minutes=recent_minutes)
    summary["path"] = str(path)
    summary["exists"] = path.exists()
    return summary


def pipeline_trace_events(started_at: str = "") -> dict:
    """실행 시작 이후 생성된 최신 Pipeline Trace와 안전한 감사 이벤트를 반환합니다."""
    path, events = _read_recent_audit_events()
    if started_at:
        events = [event for event in events if event.get("timestamp", "") >= started_at]
    trace_starts = [
        event for event in events
        if event.get("operation") == "ParseQuestion" and event.get("status") == "started"
    ]
    trace_id = trace_starts[-1].get("trace_id") if trace_starts else ""
    trace_events = [event for event in events if event.get("trace_id") == trace_id] if trace_id else []
    return {"trace_id": trace_id, "events": trace_events, "path": str(path)}


def run_diagnostics(mode: str) -> dict:
    if mode not in DIAGNOSTIC_MODES:
        raise ValueError(f"허용되지 않은 진단 모드: {mode}")
    return _run_cmd(VOC_RUNTIME_DIR / "scripts" / "quality-diagnosis.cmd", mode, timeout=300)


def judge_provider_options() -> list[dict]:
    return voc_judge_service.judge_provider_options()


def judge_independence_preview(provider: str, model: str) -> dict:
    generator_snapshot = {
        "policy": {
            "provider": "anthropic",
            "model": os.environ.get("A2A_MODEL_POLICY", "claude-sonnet-4-6"),
        }
    }
    return voc_judge_service.independence_grade(provider, model, generator_snapshot)


def _normalize_judge_config(config: dict | None) -> dict:
    config = dict(config or {})
    enabled = bool(config.get("enabled"))
    options = {item["provider"]: item for item in judge_provider_options()}
    provider = str(config.get("provider") or "anthropic").lower()
    if provider not in options:
        raise ValueError(f"지원하지 않는 Judge Provider입니다: {provider}")
    model = str(config.get("model") or options[provider]["default_model"]).strip()
    if enabled and not options[provider]["credential_configured"]:
        raise ValueError(f"{options[provider]['label']} Judge API 자격 증명이 설정되지 않았습니다.")
    return {
        "enabled": enabled,
        "provider": provider,
        "model": model,
        "timeout_seconds": int(config.get("timeout_seconds") or 90),
        "max_retries": int(config.get("max_retries") if config.get("max_retries") is not None else 2),
    }


def _not_run_judge_result(config: dict, message: str) -> dict:
    return {
        "status": "NOT_RUN",
        "decision": "NOT_RUN",
        "provider": config.get("provider", ""),
        "model": config.get("model", ""),
        "total_score": None,
        "dimension_scores": {},
        "message": message,
        "attempts": [],
        "evaluated_at": datetime.now().astimezone().isoformat(),
    }


def _evaluate_case_judge(
    *,
    case: dict,
    execution: dict,
    trace: dict,
    mode: str,
    execution_ok: bool,
    judge_config: dict,
    model_snapshot: dict,
) -> dict:
    if not judge_config["enabled"]:
        return _not_run_judge_result(judge_config, "Judge를 선택하지 않았습니다.")
    if mode != "voc":
        return _not_run_judge_result(judge_config, "격리 장애 Case는 개선안 Judge 평가 대상이 아닙니다.")
    if not execution_ok:
        return _not_run_judge_result(judge_config, "Pipeline 실행 실패로 Judge를 수행하지 않았습니다.")
    return _sanitize_evidence_value(
        voc_judge_service.evaluate_independent_judge(
            case=_sanitize_evidence_value(case),
            execution=_sanitize_evidence_value(execution),
            trace=_sanitize_evidence_value(trace),
            rubric=load_independent_judge_rubric(),
            provider=judge_config["provider"],
            model=judge_config["model"],
            generator_snapshot=model_snapshot,
            timeout_seconds=judge_config["timeout_seconds"],
            max_retries=judge_config["max_retries"],
        )
    )


def _case_status_with_judge(execution_ok: bool, judge_result: dict) -> str:
    if not execution_ok:
        return "ERROR"
    decision = judge_result.get("decision")
    if decision in {"PASS", "FAIL", "REVIEW_REQUIRED"}:
        return decision
    return "REVIEW_REQUIRED"


def run_test_case(
    case_id: str,
    timeout_seconds: int = 180,
    judge_config: dict | None = None,
) -> dict:
    """선택한 정의를 실제 VOC 실행 또는 안전한 격리 장애 시험으로 수행합니다."""
    cases = load_test_cases().get("cases", [])
    case = next((item for item in cases if item.get("case_id") == case_id), None)
    if not case:
        raise ValueError(f"알 수 없는 테스트케이스: {case_id}")

    judge_config = _normalize_judge_config(judge_config)
    run = _start_manual_voc_run(case, judge_config=judge_config)
    run_id = run["run_id"]
    started_at = run["manifest"]["started_at"]
    fault_id = FAULT_TEST_CASES.get(case_id)
    mode = "fault" if fault_id else "voc"
    try:
        if fault_id:
            execution = _run_cmd(
                VOC_RUNTIME_DIR / "scripts" / "fault-tests.cmd",
                ["--case", fault_id],
                timeout=180,
            )
        else:
            execution = run_voc_analysis(
                case.get("question", ""),
                save_report=True,
                timeout_seconds=timeout_seconds,
                task_override=case.get("expected_task"),
            )

        finished_at = datetime.now().astimezone().isoformat()
        execution_ok = bool(execution.get("ok"))
        if mode == "voc":
            execution_ok = execution_ok and bool(execution.get("result", {}).get("ok"))
        trace = (
            pipeline_trace_events(started_at)
            if mode == "voc"
            else {
                "trace_id": "",
                "events": [],
                "source": "isolated_fault_runner",
                "fault_id": fault_id,
            }
        )
        judge_result = _evaluate_case_judge(
            case=case,
            execution=execution,
            trace=trace,
            mode=mode,
            execution_ok=execution_ok,
            judge_config=judge_config,
            model_snapshot=run["manifest"].get("model_snapshot", {}),
        )
        case_status = _case_status_with_judge(execution_ok, judge_result)
        rule_status = "REVIEW_REQUIRED" if execution_ok else "NOT_RUN"
        message = _execution_message(execution, execution_ok)
        voc_run_store.save_case_artifacts(
            run_id,
            case_id,
            pipeline_result={
                "run_id": run_id,
                "case_id": case_id,
                "mode": mode,
                "fault_id": fault_id or "",
                "recorded_at": finished_at,
                "execution": _sanitize_evidence_value(execution),
            },
            trace=_sanitize_evidence_value(trace),
            rule_result={
                "run_id": run_id,
                "case_id": case_id,
                "status": rule_status,
                "rubric_id": "VOC-INTERNAL-PIPELINE-100",
                "rubric_version": load_system_rubric().get("version"),
                "message": (
                    "자동 100점 채점은 후속 Step에서 구현합니다. 현재 결과는 사람 검토가 필요합니다."
                    if execution_ok
                    else "Pipeline 실행 오류로 품질 채점을 수행하지 않았습니다."
                ),
            },
            judge_result=judge_result,
        )
        completed = voc_run_store.complete_voc_run(
            run_id,
            [
                {
                    "case_id": case_id,
                    "status": case_status,
                    "mode": mode,
                    "trace_id": trace.get("trace_id", ""),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "message": message,
                    "judge_status": judge_result.get("decision", "NOT_RUN"),
                    "judge_score": judge_result.get("total_score"),
                    "judge_independence_grade": judge_result.get("independence_grade", ""),
                }
            ],
        )
        result = {
            "mode": mode,
            "case": case,
            "execution": execution,
            "trace": _sanitize_evidence_value(trace),
            "run_id": run_id,
            "run_dir": completed["run_dir"],
            "evidence_status": case_status,
            "judge_result": judge_result,
        }
        if fault_id:
            result["fault_id"] = fault_id
        return result
    except Exception as exc:
        try:
            finished_at = datetime.now().astimezone().isoformat()
            voc_run_store.save_case_artifacts(
                run_id,
                case_id,
                pipeline_result={
                    "run_id": run_id,
                    "case_id": case_id,
                    "mode": mode,
                    "recorded_at": finished_at,
                    "execution": {"ok": False, "error": f"{type(exc).__name__}: {_safe_text(str(exc))}"},
                },
                trace={"trace_id": "", "events": []},
                rule_result={
                    "run_id": run_id,
                    "case_id": case_id,
                    "status": "NOT_RUN",
                    "message": "실행 저장 중 오류로 품질 채점을 수행하지 않았습니다.",
                },
                judge_result=_not_run_judge_result(judge_config, "Pipeline 또는 저장 오류로 Judge를 수행하지 않았습니다."),
            )
            voc_run_store.complete_voc_run(
                run_id,
                [
                    {
                        "case_id": case_id,
                        "status": "ERROR",
                        "mode": mode,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "message": f"{type(exc).__name__}: {_safe_text(str(exc))}",
                        "judge_status": "NOT_RUN",
                    }
                ],
                lifecycle_status="ERROR",
            )
        except Exception:
            pass
        raise


def batch_preflight(case_ids: list[str] | None = None) -> dict:
    """일괄 실행 전에 런타임·Agent·구현 상태를 읽기 전용으로 점검합니다."""
    catalog = load_quality_test_catalog()
    catalog_cases = {item["case_id"]: item for item in catalog.get("cases", [])}
    selected = list(case_ids or catalog_cases)
    unknown = [case_id for case_id in selected if case_id not in catalog_cases]
    implemented = [
        case_id for case_id in selected
        if case_id in catalog_cases
        and catalog_cases[case_id].get("implementation_status") == "IMPLEMENTED"
    ]
    pending = [
        case_id for case_id in selected
        if case_id in catalog_cases
        and catalog_cases[case_id].get("implementation_status") != "IMPLEMENTED"
    ]
    health = runtime_health()
    agents = agent_status_snapshot()
    needs_agents = any(case_id.startswith("TC-") and case_id not in FAULT_TEST_CASES for case_id in implemented)
    blockers = []
    warnings = []
    if unknown:
        blockers.append(f"카탈로그에 없는 Case: {', '.join(unknown)}")
    if not health.get("ok"):
        blockers.append(f"런타임 필수 파일 누락: {', '.join(health.get('missing', []))}")
    if needs_agents and not agents.get("all_running"):
        blockers.append("일반 VOC Case 실행에 필요한 6개 Agent가 모두 RUNNING 상태가 아닙니다.")
    if pending:
        warnings.append(
            f"후속 단계에서 구현할 {len(pending)}건은 NOT_RUN으로 기록됩니다: {', '.join(pending)}"
        )
    return {
        "ok": not blockers,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "selected_count": len(selected),
        "implemented_count": len(implemented),
        "pending_count": len(pending),
        "implemented_case_ids": implemented,
        "pending_case_ids": pending,
        "runtime": health,
        "agents": agents,
        "blockers": blockers,
        "warnings": warnings,
    }


def start_batch_run(
    case_ids: list[str],
    *,
    timeout_seconds: int = 180,
    max_retries: int = 2,
    parent_run_id: str = "",
    judge_config: dict | None = None,
) -> dict:
    """중복 실행을 차단하고 BATCH/RETEST Run을 생성합니다."""
    catalog = load_quality_test_catalog()
    catalog_cases = {item["case_id"]: item for item in catalog.get("cases", [])}
    selected = [str(case_id) for case_id in case_ids]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("일괄 실행 대상은 1건 이상이며 중복되지 않아야 합니다.")
    unknown = [case_id for case_id in selected if case_id not in catalog_cases]
    if unknown:
        raise ValueError(f"카탈로그에 없는 Case: {', '.join(unknown)}")
    if timeout_seconds < 1 or max_retries < 0 or max_retries > 5:
        raise ValueError("timeout은 1초 이상, 재시도는 0~5회로 설정해야 합니다.")

    judge_config = _normalize_judge_config(judge_config)
    implemented_count = sum(
        catalog_cases[case_id].get("implementation_status") == "IMPLEMENTED"
        for case_id in selected
    )
    pending_count = len(selected) - implemented_count
    seconds_per_case = 75 if judge_config.get("enabled") else 45
    estimated_total_seconds = max(
        15 + implemented_count * seconds_per_case + pending_count,
        5,
    )
    signature = tuple(sorted(selected))
    with _BATCH_LOCK:
        active_run_id = _ACTIVE_BATCH_SIGNATURES.get(signature)
        if active_run_id:
            raise RuntimeError(f"동일한 Case 조합이 이미 실행 중입니다: {active_run_id}")
        run_type = "RETEST" if parent_run_id else "BATCH"
        run = _start_voc_run(
            [catalog_cases[case_id] for case_id in selected],
            run_type=run_type,
            run_metadata={
                "parent_run_id": parent_run_id,
                "execution_policy": "SEQUENTIAL",
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries,
                "transient_backoff": "exponential",
                "judge_config": judge_config,
                "estimated_total_seconds": estimated_total_seconds,
            },
            judge_config=judge_config,
        )
        run_id = run["run_id"]
        _ACTIVE_BATCH_SIGNATURES[signature] = run_id
        _BATCH_STOP_EVENTS[run_id] = threading.Event()
        voc_run_store.update_voc_run_progress(
            run_id,
            [],
            runtime_progress={
                "phase": "PREFLIGHT",
                "phase_label": "사전 점검 완료",
                "message": "실행 환경과 선택 Case 검증을 완료했습니다.",
                "current_case_id": "",
                "current_position": 0,
                "phase_started_at": datetime.now().astimezone().isoformat(),
            },
        )
        return {
            **run,
            "case_ids": selected,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "parent_run_id": parent_run_id,
            "judge_config": judge_config,
            "estimated_total_seconds": estimated_total_seconds,
        }


def request_batch_stop(run_id: str) -> bool:
    with _BATCH_LOCK:
        event = _BATCH_STOP_EVENTS.get(run_id)
        if not event:
            return False
        event.set()
        return True


def get_batch_run_progress(run_id: str) -> dict:
    stored = voc_run_store.load_voc_run(run_id)
    manifest = stored.get("manifest", {})
    summary = stored.get("summary", {})
    with _BATCH_LOCK:
        stop_requested = bool(
            _BATCH_STOP_EVENTS.get(run_id) and _BATCH_STOP_EVENTS[run_id].is_set()
        )
    return {
        "run_id": run_id,
        "run_dir": stored.get("run_dir", ""),
        "status": manifest.get("status", summary.get("status", "ERROR")),
        "started_at": manifest.get("started_at", ""),
        "finished_at": manifest.get("finished_at", ""),
        "total": summary.get("total", len(manifest.get("selected_case_ids", []))),
        "completed": summary.get("completed", len(summary.get("case_results", []))),
        "counts": summary.get("counts", {}),
        "judge_counts": summary.get("judge_counts", {}),
        "case_results": summary.get("case_results", []),
        "stop_requested": stop_requested,
        "judge_config": manifest.get("run_metadata", {}).get("judge_config", {}),
        "errors": stored.get("errors", []),
        "runtime_progress": summary.get("runtime_progress", {}),
        "estimated_total_seconds": manifest.get("run_metadata", {}).get(
            "estimated_total_seconds",
            0,
        ),
    }


def execute_batch_run(
    run_id: str,
    case_ids: list[str],
    *,
    timeout_seconds: int = 180,
    max_retries: int = 2,
    backoff_base_seconds: float = 1.0,
    judge_config: dict | None = None,
) -> dict:
    """Case를 순차 실행하며 매 Case 결과와 재시도 증적을 즉시 저장합니다."""
    signature = tuple(sorted(case_ids))
    results = []

    try:
        run_manifest = voc_run_store.load_voc_run(run_id).get("manifest", {})
        if judge_config is None:
            judge_config = run_manifest.get("run_metadata", {}).get("judge_config")
        judge_config = _normalize_judge_config(judge_config)
        catalog = load_quality_test_catalog()
        catalog_cases = {item["case_id"]: item for item in catalog.get("cases", [])}
        test_cases = {item["case_id"]: item for item in load_test_cases().get("cases", [])}
        event = _BATCH_STOP_EVENTS.get(run_id) or threading.Event()
        voc_run_store.update_voc_run_progress(
            run_id,
            results,
            runtime_progress={
                "phase": "PREPARING",
                "phase_label": "처리 준비 중",
                "message": "카탈로그, 테스트 정의와 실행 환경을 준비하고 있습니다.",
                "current_case_id": "",
                "current_position": 0,
                "phase_started_at": datetime.now().astimezone().isoformat(),
            },
        )
        for position, case_id in enumerate(case_ids):
            catalog_case = catalog_cases[case_id]
            if event.is_set():
                for remaining_id in case_ids[position:]:
                    results.append(_record_not_run_case(run_id, remaining_id, "사용자 중지 요청으로 실행하지 않았습니다."))
                break

            case_started_at = datetime.now().astimezone().isoformat()
            voc_run_store.update_voc_run_progress(
                run_id,
                results,
                runtime_progress={
                    "phase": "RUNNING",
                    "phase_label": "TC 수행 중",
                    "message": f"{case_id} Pipeline과 품질 평가를 수행하고 있습니다.",
                    "current_case_id": case_id,
                    "current_position": position + 1,
                    "phase_started_at": case_started_at,
                    "current_case_started_at": case_started_at,
                },
            )

            if catalog_case.get("implementation_status") != "IMPLEMENTED":
                results.append(
                    _record_not_run_case(
                        run_id,
                        case_id,
                        "후속 품질평가 단계에서 구현 예정인 Case입니다.",
                    )
                )
                voc_run_store.update_voc_run_progress(run_id, results)
                continue

            case_result = _execute_batch_case(
                run_id,
                case_id,
                test_cases.get(case_id, catalog_case),
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                backoff_base_seconds=backoff_base_seconds,
                judge_config=judge_config,
                model_snapshot=run_manifest.get("model_snapshot", {}),
            )
            results.append(case_result)
            voc_run_store.update_voc_run_progress(
                run_id,
                results,
                runtime_progress={
                    "phase": "RUNNING",
                    "phase_label": "TC 결과 저장",
                    "message": f"{case_id} 결과와 증적 저장을 완료했습니다.",
                    "current_case_id": case_id,
                    "current_position": position + 1,
                },
            )

        lifecycle_status = "INTERRUPTED" if event.is_set() else "COMPLETED"
        voc_run_store.update_voc_run_progress(
            run_id,
            results,
            runtime_progress={
                "phase": "FINALIZING",
                "phase_label": "결과 정리 중",
                "message": "전체 결과 집계와 Run 이력을 정리하고 있습니다.",
                "current_case_id": "",
                "current_position": len(results),
                "phase_started_at": datetime.now().astimezone().isoformat(),
            },
        )
        completed = voc_run_store.complete_voc_run(
            run_id,
            results,
            lifecycle_status=lifecycle_status,
        )
        return {
            "run_id": run_id,
            "run_dir": completed["run_dir"],
            "manifest": completed["manifest"],
            "summary": completed["summary"],
        }
    except Exception:
        try:
            voc_run_store.complete_voc_run(run_id, results, lifecycle_status="ERROR")
        except Exception:
            pass
        raise
    finally:
        with _BATCH_LOCK:
            if _ACTIVE_BATCH_SIGNATURES.get(signature) == run_id:
                _ACTIVE_BATCH_SIGNATURES.pop(signature, None)
            _BATCH_STOP_EVENTS.pop(run_id, None)


def _record_not_run_case(run_id: str, case_id: str, message: str) -> dict:
    now = datetime.now().astimezone().isoformat()
    result = {
        "case_id": case_id,
        "status": "NOT_RUN",
        "mode": "pending",
        "trace_id": "",
        "started_at": "",
        "finished_at": now,
        "message": message,
        "attempt_count": 0,
        "judge_status": "NOT_RUN",
    }
    voc_run_store.save_case_artifacts(
        run_id,
        case_id,
        pipeline_result={"run_id": run_id, "case_id": case_id, "attempts": [], "message": message},
        trace={"trace_id": "", "events": []},
        rule_result={"run_id": run_id, "case_id": case_id, "status": "NOT_RUN", "message": message},
        judge_result={"run_id": run_id, "case_id": case_id, "status": "NOT_RUN", "decision": "NOT_RUN", "message": message},
    )
    return result


def _execute_batch_case(
    run_id: str,
    case_id: str,
    case: dict,
    *,
    timeout_seconds: int,
    max_retries: int,
    backoff_base_seconds: float,
    judge_config: dict,
    model_snapshot: dict,
) -> dict:
    started_at = datetime.now().astimezone().isoformat()
    fault_id = case_id if case_id in DIRECT_FAULT_CASE_IDS else FAULT_TEST_CASES.get(case_id)
    mode = "fault" if fault_id else "voc"
    attempts = []
    execution = {}
    execution_ok = False

    for attempt_number in range(1, max_retries + 2):
        attempt_started = datetime.now().astimezone().isoformat()
        try:
            if fault_id:
                execution = _run_cmd(
                    VOC_RUNTIME_DIR / "scripts" / "fault-tests.cmd",
                    ["--case", fault_id],
                    timeout=timeout_seconds,
                )
            else:
                execution = run_voc_analysis(
                    case.get("question", ""),
                    save_report=True,
                    timeout_seconds=timeout_seconds,
                    task_override=case.get("expected_task"),
                )
            execution_ok = bool(execution.get("ok"))
            if mode == "voc":
                execution_ok = execution_ok and bool(execution.get("result", {}).get("ok"))
        except Exception as exc:
            execution = {"ok": False, "error": f"{type(exc).__name__}: {_safe_text(str(exc))}"}
            execution_ok = False

        transient = not execution_ok and _is_transient_execution_error(execution)
        attempts.append(
            {
                "attempt": attempt_number,
                "started_at": attempt_started,
                "finished_at": datetime.now().astimezone().isoformat(),
                "ok": execution_ok,
                "transient": transient,
                "execution": _sanitize_evidence_value(execution),
            }
        )
        if execution_ok or not transient or attempt_number > max_retries:
            break
        time.sleep(max(0.0, backoff_base_seconds) * (2 ** (attempt_number - 1)))

    finished_at = datetime.now().astimezone().isoformat()
    trace = (
        pipeline_trace_events(started_at)
        if mode == "voc"
        else {"trace_id": "", "events": [], "source": "isolated_fault_runner", "fault_id": fault_id}
    )
    status = "REVIEW_REQUIRED" if execution_ok else "ERROR"
    message = _execution_message(execution, execution_ok)
    judge_result = _evaluate_case_judge(
        case=case,
        execution=execution,
        trace=trace,
        mode=mode,
        execution_ok=execution_ok,
        judge_config=judge_config,
        model_snapshot=model_snapshot,
    )
    status = _case_status_with_judge(execution_ok, judge_result)
    voc_run_store.save_case_artifacts(
        run_id,
        case_id,
        pipeline_result={
            "run_id": run_id,
            "case_id": case_id,
            "mode": mode,
            "fault_id": fault_id or "",
            "recorded_at": finished_at,
            "attempts": attempts,
            "execution": _sanitize_evidence_value(execution),
        },
        trace=_sanitize_evidence_value(trace),
        rule_result={
            "run_id": run_id,
            "case_id": case_id,
            "status": "REVIEW_REQUIRED" if execution_ok else "NOT_RUN",
            "rubric_id": "VOC-INTERNAL-PIPELINE-100",
            "rubric_version": load_system_rubric().get("version"),
            "message": "자동 품질 채점 전 사람 검토가 필요합니다." if execution_ok else "실행 오류로 채점하지 않았습니다.",
        },
        judge_result=judge_result,
    )
    return {
        "case_id": case_id,
        "status": status,
        "mode": mode,
        "trace_id": trace.get("trace_id", ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "message": message,
        "attempt_count": len(attempts),
        "judge_status": judge_result.get("decision", "NOT_RUN"),
        "judge_score": judge_result.get("total_score"),
        "judge_independence_grade": judge_result.get("independence_grade", ""),
    }


def _is_transient_execution_error(execution: dict) -> bool:
    text = json.dumps(execution, ensure_ascii=False, default=str).lower()
    return any(marker in text for marker in TRANSIENT_ERROR_MARKERS)


def list_voc_run_history() -> list[dict]:
    """실행 중 Run을 변경하지 않고 이력 화면용 요약을 반환합니다."""
    rows = []
    for item in voc_run_store.list_voc_runs(recover=False):
        counts = item.get("counts", {})
        selected_count = len(item.get("selected_case_ids", []))
        completed_count = sum(int(counts.get(status, 0)) for status in voc_run_store.CASE_STATUSES)
        decided = int(counts.get("PASS", 0)) + int(counts.get("FAIL", 0))
        success_rate = round(int(counts.get("PASS", 0)) / decided * 100, 1) if decided else None
        rows.append(
            {
                **item,
                "selected_count": selected_count,
                "completed_count": completed_count,
                "completion_rate": round(completed_count / selected_count * 100, 1) if selected_count else 0.0,
                "success_rate": success_rate,
                "judge_status": "사용" if item.get("judge_enabled") else "미사용",
                "deployment_decision": item.get("deployment_decision") or "미판정",
            }
        )
    return rows


def load_voc_run_history_detail(run_id: str) -> dict:
    stored = voc_run_store.load_voc_run(run_id)
    stored["integrity"] = voc_run_store.verify_run_integrity(run_id)
    return stored


def load_voc_case_history_detail(run_id: str, case_id: str) -> dict:
    return voc_run_store.load_case_artifacts(run_id, case_id)


def reevaluate_voc_run_case(
    run_id: str,
    case_id: str,
    judge_config: dict,
) -> dict:
    config = _normalize_judge_config({**judge_config, "enabled": True})
    stored = voc_run_store.load_voc_run(run_id)
    artifacts = voc_run_store.load_case_artifacts(run_id, case_id)
    pipeline = artifacts.get("pipeline_result", {})
    execution = pipeline.get("execution", {})
    mode = pipeline.get("mode", "")
    execution_ok = bool(execution.get("ok"))
    if mode == "voc":
        execution_ok = execution_ok and bool(execution.get("result", {}).get("ok"))
    if mode != "voc" or not execution_ok:
        raise ValueError("성공한 VOC Pipeline Case만 Judge 재평가할 수 있습니다.")

    run_dir = Path(stored["run_dir"])
    snapshot_path = run_dir / "snapshots" / "selected_test_cases.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    case = next((item for item in snapshot.get("cases", []) if item.get("case_id") == case_id), None)
    if not case:
        raise ValueError("Run 스냅샷에서 재평가 대상 Case를 찾을 수 없습니다.")
    judge_result = _evaluate_case_judge(
        case=case,
        execution=execution,
        trace=artifacts.get("trace", {}),
        mode=mode,
        execution_ok=True,
        judge_config=config,
        model_snapshot=stored.get("manifest", {}).get("model_snapshot", {}),
    )
    saved = voc_run_store.save_judge_reevaluation(run_id, case_id, judge_result)
    return {
        "run_id": run_id,
        "case_id": case_id,
        "judge_result": saved["judge_result"],
        "summary": saved["summary"],
    }


def validity_provider_options() -> list[dict]:
    return voc_validity_service.validity_provider_options()


def list_improvement_validity_candidates() -> list[dict]:
    """완료된 VOC Pipeline Case를 타당성 검증 대상 목록으로 반환합니다."""
    candidates = []
    for run in voc_run_store.list_voc_runs(recover=False):
        if run.get("status") == "RUNNING":
            continue
        stored = voc_run_store.load_voc_run(run["run_id"])
        for item in stored.get("summary", {}).get("case_results", []):
            case_id = item.get("case_id")
            if not case_id:
                continue
            artifacts = voc_run_store.load_case_artifacts(run["run_id"], case_id)
            pipeline = artifacts.get("pipeline_result", {})
            execution = pipeline.get("execution", {})
            result = execution.get("result", {}) if isinstance(execution, dict) else {}
            if pipeline.get("mode") != "voc" or not execution.get("ok") or not result.get("ok"):
                continue
            validity = artifacts.get("validity_result", {})
            candidates.append(
                {
                    "run_id": run["run_id"],
                    "case_id": case_id,
                    "started_at": run.get("started_at", ""),
                    "run_type": run.get("run_type", ""),
                    "parent_run_id": stored.get("manifest", {}).get("run_metadata", {}).get("parent_run_id", ""),
                    "question": execution.get("question", ""),
                    "judge_status": artifacts.get("judge_result", {}).get("decision", "NOT_RUN"),
                    "judge_score": artifacts.get("judge_result", {}).get("total_score"),
                    "validity_status": validity.get("decision", "NOT_RUN"),
                    "validity_score": validity.get("total_score"),
                    "workflow_state": validity.get("workflow_state", "DRAFT"),
                    "formal_approval": bool(validity.get("formal_approval")),
                }
            )
    candidates.sort(key=lambda item: item.get("started_at", ""), reverse=True)
    return candidates


def _load_run_case_snapshot(run_id: str, case_id: str) -> dict:
    stored = voc_run_store.load_voc_run(run_id)
    run_dir = Path(stored["run_dir"])
    snapshot_path = run_dir / "snapshots" / "selected_test_cases.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    case = next((item for item in snapshot.get("cases", []) if item.get("case_id") == case_id), None)
    if not case:
        raise ValueError("Run 스냅샷에서 대상 Case를 찾을 수 없습니다.")
    return {"stored": stored, "case": case, "run_dir": run_dir}


def evaluate_voc_improvement_validity(
    run_id: str,
    case_id: str,
    config: dict,
) -> dict:
    provider = str(config.get("provider") or "anthropic").lower()
    options = {item["provider"]: item for item in validity_provider_options()}
    if provider not in options:
        raise ValueError("지원하지 않는 타당성 평가 Provider입니다.")
    model = str(config.get("model") or options[provider]["default_model"]).strip()
    if not options[provider]["credential_configured"]:
        raise ValueError(f"{options[provider]['label']} API 자격 증명이 설정되지 않았습니다.")

    loaded = _load_run_case_snapshot(run_id, case_id)
    artifacts = voc_run_store.load_case_artifacts(run_id, case_id)
    pipeline = artifacts.get("pipeline_result", {})
    execution = pipeline.get("execution", {})
    result = execution.get("result", {}) if isinstance(execution, dict) else {}
    if pipeline.get("mode") != "voc" or not execution.get("ok") or not result.get("ok"):
        raise ValueError("성공한 VOC Pipeline Case만 타당성을 평가할 수 있습니다.")
    validity = voc_validity_service.evaluate_improvement_validity(
        case=loaded["case"],
        execution=execution,
        trace=artifacts.get("trace", {}),
        judge_result=artifacts.get("judge_result", {}),
        defects=loaded["stored"].get("defects", {}),
        rubric=load_improvement_validity_rubric(),
        provider=provider,
        model=model,
    )
    saved = voc_run_store.save_validity_evaluation(run_id, case_id, validity)
    return {
        "run_id": run_id,
        "case_id": case_id,
        "validity_result": saved["validity_result"],
        "summary": saved["summary"],
    }


def review_voc_improvement_validity(
    run_id: str,
    case_id: str,
    *,
    reviewer_role: str,
    reviewer_name_or_id: str,
    decision: str,
    comment: str,
) -> dict:
    return voc_run_store.apply_validity_human_review(
        run_id,
        case_id,
        reviewer_role=reviewer_role,
        reviewer_name_or_id=_safe_text(reviewer_name_or_id),
        decision=decision,
        comment=_safe_text(comment),
    )


def compare_voc_improvement_answers(
    baseline_run_id: str,
    candidate_run_id: str,
    case_id: str,
) -> dict:
    """연결된 RETEST의 동일 질문·TC·Rubric 결과만 실제 개선 A/B로 비교합니다."""
    if baseline_run_id == candidate_run_id:
        raise ValueError("서로 다른 Run을 선택하세요.")
    baseline = _load_run_case_snapshot(baseline_run_id, case_id)
    candidate = _load_run_case_snapshot(candidate_run_id, case_id)
    baseline_manifest = baseline["stored"].get("manifest", {})
    candidate_manifest = candidate["stored"].get("manifest", {})
    differences = []
    for field in ("suite_id", "catalog_version", "test_case_hash"):
        if baseline_manifest.get(field) != candidate_manifest.get(field):
            differences.append(field)
    baseline_rubric = baseline_manifest.get("rubric_versions", {}).get("improvement_validity")
    candidate_rubric = candidate_manifest.get("rubric_versions", {}).get("improvement_validity")
    if baseline_rubric != candidate_rubric:
        differences.append("improvement_validity_rubric")
    if baseline["case"].get("question") != candidate["case"].get("question"):
        differences.append("question")
    metadata = candidate_manifest.get("run_metadata", {})
    if candidate_manifest.get("run_type") != "RETEST" or metadata.get("parent_run_id") != baseline_run_id:
        differences.append("retest_parent_run")

    before = voc_run_store.load_case_artifacts(baseline_run_id, case_id)
    after = voc_run_store.load_case_artifacts(candidate_run_id, case_id)

    def values(artifacts: dict) -> dict:
        execution = artifacts.get("pipeline_result", {}).get("execution", {})
        result = execution.get("result", {}) if isinstance(execution, dict) else {}
        judge = artifacts.get("judge_result", {})
        validity = artifacts.get("validity_result", {})
        return {
            "summary": result.get("summary", ""),
            "policy": result.get("policy", ""),
            "judge_decision": judge.get("decision", "NOT_RUN"),
            "judge_score": judge.get("total_score"),
            "validity_decision": validity.get("decision", "NOT_RUN"),
            "validity_score": validity.get("total_score"),
            "workflow_state": validity.get("workflow_state", "DRAFT"),
        }

    baseline_values = values(before)
    candidate_values = values(after)
    score_deltas = {}
    for key in ("judge_score", "validity_score"):
        left, right = baseline_values.get(key), candidate_values.get(key)
        score_deltas[key] = round(float(right) - float(left), 2) if left is not None and right is not None else None
    return {
        "compatible": not differences,
        "compatibility_differences": differences,
        "comparison_type": "LINKED_RETEST_ANSWER_AB",
        "case_id": case_id,
        "question": baseline["case"].get("question", ""),
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "baseline": baseline_values,
        "candidate": candidate_values,
        "score_deltas": score_deltas,
    }


def download_voc_run_evidence(run_id: str) -> bytes:
    return voc_run_store.build_run_evidence_zip(run_id)


def delete_voc_run_history(run_ids: list[str]) -> dict:
    return voc_run_store.delete_voc_runs(run_ids)


def list_voc_defects() -> list[dict]:
    return voc_defect_service.list_defects()


def load_voc_defect(defect_id: str) -> dict:
    return voc_defect_service.load_defect(defect_id)


def create_voc_defect(**payload) -> dict:
    return voc_defect_service.create_defect(**payload)


def transition_voc_defect(defect_id: str, **payload) -> dict:
    return voc_defect_service.transition_defect(defect_id, **payload)


def build_voc_quality_report(run_id: str, baseline_run_id: str = "") -> dict:
    return voc_report_service.build_quality_report_model(run_id, baseline_run_id)


def generate_voc_quality_report(run_id: str, baseline_run_id: str = "") -> dict:
    return voc_report_service.generate_quality_report_evidence(run_id, baseline_run_id)


def latest_voc_full_run_id() -> str:
    return voc_acceptance_service.latest_full_run_id()


def build_voc_acceptance_snapshot(
    run_id: str, baseline_run_id: str = "", *, verification: dict | None = None
) -> dict:
    return voc_acceptance_service.build_acceptance_snapshot(
        run_id,
        baseline_run_id,
        runtime=runtime_health(),
        agents=agent_status_snapshot(),
        verification=verification if verification is not None else voc_acceptance_service.load_verification_snapshot(),
    )


def generate_voc_acceptance_evidence(snapshot: dict) -> dict:
    return voc_acceptance_service.generate_acceptance_evidence(snapshot)


def compare_voc_runs(baseline_run_id: str, candidate_run_id: str) -> dict:
    if baseline_run_id == candidate_run_id:
        raise ValueError("서로 다른 두 Run을 선택하세요.")
    baseline = voc_run_store.load_voc_run(baseline_run_id)
    candidate = voc_run_store.load_voc_run(candidate_run_id)
    baseline_manifest = baseline.get("manifest", {})
    candidate_manifest = candidate.get("manifest", {})
    baseline_summary = baseline.get("summary", {})
    candidate_summary = candidate.get("summary", {})
    compatibility_fields = ("suite_id", "catalog_version", "test_case_hash")
    differences = [
        field for field in compatibility_fields
        if baseline_manifest.get(field) != candidate_manifest.get(field)
    ]
    baseline_rubrics = baseline_manifest.get("rubric_versions", {})
    candidate_rubrics = candidate_manifest.get("rubric_versions", {})
    if baseline_rubrics != candidate_rubrics:
        differences.append("rubric_versions")

    baseline_selected = set(baseline_manifest.get("selected_case_ids", []))
    candidate_selected = set(candidate_manifest.get("selected_case_ids", []))
    if not candidate_selected or not candidate_selected.issubset(baseline_selected):
        differences.append("selected_case_scope")
    candidate_metadata = candidate_manifest.get("run_metadata", {})
    valid_retest_pair = (
        candidate_manifest.get("run_type") == "RETEST"
        and candidate_metadata.get("parent_run_id") == baseline_run_id
    )
    if not valid_retest_pair:
        differences.append("retest_parent_run")

    baseline_cases = {
        item.get("case_id"): item for item in baseline_summary.get("case_results", [])
    }
    candidate_cases = {
        item.get("case_id"): item for item in candidate_summary.get("case_results", [])
    }
    case_ids = sorted(set(baseline_cases) | set(candidate_cases))
    case_comparison = []
    for case_id in case_ids:
        before = baseline_cases.get(case_id, {})
        after = candidate_cases.get(case_id, {})
        case_comparison.append(
            {
                "case_id": case_id,
                "baseline_status": before.get("status", "미포함"),
                "candidate_status": after.get("status", "미포함"),
                "changed": before.get("status") != after.get("status"),
                "baseline_attempts": int(before.get("attempt_count") or 0),
                "candidate_attempts": int(after.get("attempt_count") or 0),
            }
        )
    statuses = sorted(voc_run_store.CASE_STATUSES)
    count_comparison = [
        {
            "status": status,
            "baseline": int(baseline_summary.get("counts", {}).get(status, 0)),
            "candidate": int(candidate_summary.get("counts", {}).get(status, 0)),
            "delta": int(candidate_summary.get("counts", {}).get(status, 0))
            - int(baseline_summary.get("counts", {}).get(status, 0)),
        }
        for status in statuses
    ]
    return {
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "compatible": not differences,
        "comparison_type": "RETEST_BEFORE_AFTER",
        "valid_retest_pair": valid_retest_pair,
        "compatibility_differences": differences,
        "count_comparison": count_comparison,
        "case_comparison": case_comparison,
        "baseline_status": baseline_manifest.get("status", ""),
        "candidate_status": candidate_manifest.get("status", ""),
    }


def _execution_message(execution: dict, execution_ok: bool) -> str:
    if execution_ok:
        return "Pipeline 실행 완료 — 자동 품질 채점 전 사람 검토 필요"
    result = execution.get("result", {}) if isinstance(execution, dict) else {}
    return _safe_text(
        str(
            result.get("message")
            or result.get("error")
            or execution.get("output")
            or "Pipeline 실행 오류"
        )
    )[:500]


def _sanitize_evidence_value(value):
    sensitive_keys = {"api_key", "token_value", "password", "secret", "authorization"}
    if isinstance(value, dict):
        return {
            key: "[REDACTED_CREDENTIAL]"
            if str(key).lower() in sensitive_keys
            else _sanitize_evidence_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_evidence_value(item) for item in value]
    if isinstance(value, str):
        text = _safe_text(value)
        for pattern, replacement in PERSONAL_DATA_PATTERNS:
            text = pattern.sub(replacement, text)
        return text
    return value


def _start_voc_run(
    cases: list[dict],
    *,
    run_type: str,
    run_metadata: dict | None = None,
    judge_config: dict | None = None,
) -> dict:
    judge_config = _normalize_judge_config(judge_config)
    catalog = load_quality_test_catalog()
    system_rubric = load_system_rubric()
    judge_rubric = load_independent_judge_rubric()
    validity_rubric = load_improvement_validity_rubric()
    evidence_contract = load_quality_evidence_contract()
    rubric_payloads = {
        "internal_pipeline": system_rubric,
        "independent_judge": judge_rubric,
        "improvement_validity": validity_rubric,
    }
    model_snapshot = {
        "summary": {
            "provider": "openai",
            "model": os.environ.get("A2A_MODEL_SUMMARY", "gpt-5.2"),
            "credential_configured": bool(os.environ.get("OPENAI_API_KEY")),
        },
        "policy": {
            "provider": "anthropic",
            "model": os.environ.get("A2A_MODEL_POLICY", "claude-sonnet-4-6"),
            "credential_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        "judge": {
            "enabled": judge_config["enabled"],
            "provider": judge_config["provider"],
            "model": judge_config["model"],
            "credential_configured": next(
                item["credential_configured"]
                for item in judge_provider_options()
                if item["provider"] == judge_config["provider"]
            ),
        },
    }
    environment = {
        "python_version": platform.python_version(),
        "operating_system": platform.system(),
        "platform_release": platform.release(),
        "runtime_root": VOC_RUNTIME_DIR.name,
    }
    environment["fingerprint_sha256"] = voc_run_store.canonical_sha256(environment)
    prompt_files = [
        VOC_RUNTIME_DIR / "agents" / f"{name}.py"
        for name, _, _ in AGENT_DEFINITIONS
    ] + [VOC_RUNTIME_DIR / "scripts" / "run-voc.py"]
    prompt_snapshot = {
        "strategy": "source_file_sha256",
        "files": {
            str(path.relative_to(VOC_RUNTIME_DIR)).replace("\\", "/"): voc_run_store.file_sha256(path)
            for path in prompt_files
            if path.exists()
        },
    }
    rubric_versions = {
        name: {
            "version": payload.get("version"),
            "sha256": voc_run_store.canonical_sha256(payload),
        }
        for name, payload in rubric_payloads.items()
    }
    snapshots = {
        "selected_test_cases.json": {"cases": _sanitize_evidence_value(cases)},
        "quality_test_catalog.json": catalog,
        "rubrics/system_quality_rubric.json": system_rubric,
        "rubrics/independent_judge_rubric.json": judge_rubric,
        "rubrics/improvement_validity_rubric.json": validity_rubric,
        "quality_evidence_contract.json": evidence_contract,
        "model_snapshot.json": model_snapshot,
        "prompt_snapshot.json": prompt_snapshot,
    }
    return voc_run_store.start_voc_run(
        run_type=run_type,
        selected_case_ids=[case["case_id"] for case in cases],
        suite_id=catalog.get("suite_id", "VOC-QA-35"),
        catalog_version=str(catalog.get("version", "")),
        test_case_hash=voc_run_store.canonical_sha256(catalog.get("cases", [])),
        rubric_versions=rubric_versions,
        model_snapshot=model_snapshot,
        judge_enabled=judge_config["enabled"],
        environment_fingerprint=environment,
        snapshots=snapshots,
        run_metadata=_sanitize_evidence_value(run_metadata or {}),
    )


def _start_manual_voc_run(case: dict, *, judge_config: dict | None = None) -> dict:
    return _start_voc_run([case], run_type="MANUAL", judge_config=judge_config)


def _sanitize_value(value):
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return _safe_text(value) if isinstance(value, str) else value


def run_voc_analysis(
    question: str,
    save_report: bool = False,
    timeout_seconds: int = 180,
    task_override: str | None = None,
) -> dict:
    question = (question or "").strip()
    if not question:
        return {"ok": False, "result": {"ok": False, "message": "질문을 입력하세요."}}
    if len(question) > 4000:
        return {"ok": False, "result": {"ok": False, "message": "질문은 4,000자 이하여야 합니다."}}

    timeout_seconds = max(5, min(int(timeout_seconds), 180))
    command = [
        sys.executable,
        str(VOC_RUNTIME_DIR / "scripts" / "run-voc.py"),
        "--question",
        question,
        "--csv-path",
        str(VOC_RUNTIME_DIR / "voc.csv"),
        "--timeout",
        str(timeout_seconds),
    ]
    if save_report:
        command.append("--save-report")
    if task_override in {"summary", "policy", "both"}:
        command.extend(["--task-override", task_override])
    try:
        completed = subprocess.run(
            command,
            cwd=VOC_RUNTIME_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds + 30,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "result": {"ok": False, "message": f"VOC 분석이 {timeout_seconds + 30}초를 초과했습니다."},
        }
    except Exception as exc:
        return {"ok": False, "result": {"ok": False, "message": _safe_text(f"{type(exc).__name__}: {exc}")}}

    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        return {
            "ok": False,
            "result": {
                "ok": False,
                "message": "VOC 분석 결과 JSON을 해석하지 못했습니다.",
                "error": _safe_text(completed.stderr or completed.stdout),
            },
        }
    payload = _sanitize_value(payload)
    payload["ok"] = completed.returncode in (0, 2) and isinstance(payload.get("result"), dict)
    return payload


def load_json(relative_path: str) -> dict:
    path = (VOC_RUNTIME_DIR / relative_path).resolve()
    if VOC_RUNTIME_DIR.resolve() not in path.parents:
        raise ValueError("런타임 외부 경로는 읽을 수 없습니다.")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_test_cases() -> dict:
    return load_json("quality_diagnosis/test_cases.json")


def load_system_rubric() -> dict:
    return load_json("quality_diagnosis/system_quality_rubric.json")


def load_quality_test_catalog() -> dict:
    return load_json("quality_diagnosis/quality_test_catalog.json")


def load_independent_judge_rubric() -> dict:
    return load_json("quality_diagnosis/independent_judge_rubric.json")


def load_improvement_validity_rubric() -> dict:
    return load_json("quality_diagnosis/improvement_validity_rubric.json")


def load_quality_evidence_contract() -> dict:
    return load_json("quality_diagnosis/quality_evidence_contract.json")


def load_quality_rubric(rubric_type: str) -> dict:
    spec = QUALITY_RUBRIC_SPECS.get(rubric_type)
    if not spec:
        raise ValueError("알 수 없는 품질 평가 기준 유형입니다.")
    return load_json(spec["relative_path"])


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_quality_rubric(rubric_type: str, payload: dict) -> list[str]:
    spec = QUALITY_RUBRIC_SPECS.get(rubric_type)
    if not spec:
        return ["알 수 없는 품질 평가 기준 유형입니다."]
    if not isinstance(payload, dict):
        return ["Rubric JSON의 최상위 값은 객체여야 합니다."]

    errors = []
    serialized_payload = json.dumps(payload, ensure_ascii=False, default=str)
    if any(pattern.search(serialized_payload) for pattern in SECRET_PATTERNS):
        errors.append("Rubric JSON에는 API 키나 인증정보를 포함할 수 없습니다.")
    if not str(payload.get("version") or "").strip():
        errors.append("version은 필수입니다.")
    if payload.get("total_points") != 100:
        errors.append("total_points는 100이어야 합니다.")
    expected_rubric_id = spec.get("rubric_id")
    if expected_rubric_id and payload.get("rubric_id") != expected_rubric_id:
        errors.append(f"rubric_id는 {expected_rubric_id}여야 합니다.")

    items = payload.get(spec["items_key"])
    if not isinstance(items, dict) or not items:
        errors.append(f"{spec['items_key']}는 비어 있지 않은 객체여야 합니다.")
        items = {}

    item_total = 0.0
    for item_id, item in items.items():
        if not str(item_id).strip() or not isinstance(item, dict):
            errors.append("평가 항목 ID와 정의가 올바르지 않습니다.")
            continue
        if not str(item.get("label") or "").strip():
            errors.append(f"{item_id}: 평가 항목명이 필요합니다.")
        max_points = item.get("max_points")
        if not _is_number(max_points) or max_points <= 0:
            errors.append(f"{item_id}: 배점은 0보다 큰 숫자여야 합니다.")
            continue
        item_total += float(max_points)
        criteria = item.get("criteria")
        if not isinstance(criteria, dict) or not criteria:
            errors.append(f"{item_id}: 세부 기준이 필요합니다.")
            continue
        if any(not str(key).strip() or not _is_number(score) or score < 0 for key, score in criteria.items()):
            errors.append(f"{item_id}: 세부 기준 ID와 점수는 유효한 0 이상의 값이어야 합니다.")
        else:
            criteria_total = sum(float(score) for score in criteria.values())
            if abs(criteria_total - float(max_points)) > 0.001:
                errors.append(
                    f"{item_id}: 세부 기준 합계 {criteria_total:g}와 배점 {float(max_points):g}이 다릅니다."
                )
        if "pass_floor" in item:
            pass_floor = item.get("pass_floor")
            if not _is_number(pass_floor) or not 0 < float(pass_floor) <= float(max_points):
                errors.append(f"{item_id}: PASS 하한은 0보다 크고 배점 이하여야 합니다.")

    if items and abs(item_total - 100.0) > 0.001:
        errors.append(f"평가 항목 배점 합계는 100이어야 합니다. 현재 합계: {item_total:g}")

    decisions = payload.get(spec["decisions_key"])
    valid_ranges = []
    if not isinstance(decisions, list) or not decisions:
        errors.append(f"{spec['decisions_key']}는 한 건 이상 필요합니다.")
    else:
        for index, decision in enumerate(decisions, start=1):
            if not isinstance(decision, dict) or not str(decision.get("decision") or "").strip():
                errors.append(f"판정 기준 {index}: decision이 필요합니다.")
                continue
            min_score = decision.get(spec["decision_min_key"])
            max_score = decision.get(spec["decision_max_key"])
            if not _is_number(min_score) or not _is_number(max_score):
                errors.append(f"판정 기준 {index}: 최소·최대 점수는 숫자여야 합니다.")
                continue
            if not 0 <= float(min_score) <= float(max_score) <= 100:
                errors.append(f"판정 기준 {index}: 점수 범위는 0~100 안이어야 합니다.")
                continue
            valid_ranges.append((float(min_score), float(max_score)))

    if valid_ranges:
        ordered = sorted(valid_ranges)
        if ordered[0][0] != 0 or ordered[-1][1] != 100:
            errors.append("판정 구간은 0점부터 100점까지 포함해야 합니다.")
        for previous, current in zip(ordered, ordered[1:]):
            if round(current[0] - previous[1], 2) != 0.01:
                errors.append("판정 구간 사이에 중복 또는 누락이 없어야 합니다.")
                break

    hold_rules = payload.get(spec["hold_rules_key"])
    if not isinstance(hold_rules, list) or not hold_rules or any(
        not str(rule).strip() for rule in hold_rules
    ):
        errors.append(f"{spec['hold_rules_key']}에는 한 건 이상의 규칙이 필요합니다.")

    if rubric_type == "independent_judge":
        if payload.get("judge_provider_policy") != "runtime_configurable":
            errors.append("독립 LLM Judge의 provider 정책은 runtime_configurable이어야 합니다.")
        if not str(payload.get("default_provider") or "").strip():
            errors.append("독립 LLM Judge의 default_provider가 필요합니다.")
        required_statuses = {"ERROR", "NOT_RUN"}
        if set(payload.get("non_quality_statuses", {})) != required_statuses:
            errors.append("독립 LLM Judge 실행 상태에는 ERROR와 NOT_RUN이 필요합니다.")
    if rubric_type == "improvement_validity":
        states = set(payload.get("workflow_states", []))
        if not {"QA_REVIEWED", "BUSINESS_APPROVED"}.issubset(states):
            errors.append("개선안 타당성 승인 흐름에는 QA_REVIEWED와 BUSINESS_APPROVED가 필요합니다.")

    return errors


def save_quality_rubric(rubric_type: str, payload: dict, *, source: str) -> dict:
    errors = validate_quality_rubric(rubric_type, payload)
    if errors:
        return {"ok": False, "errors": errors}

    spec = QUALITY_RUBRIC_SPECS[rubric_type]
    target = (VOC_RUNTIME_DIR / spec["relative_path"]).resolve()
    if VOC_RUNTIME_DIR.resolve() not in target.parents:
        return {"ok": False, "errors": ["런타임 외부 경로에는 저장할 수 없습니다."]}

    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    before_bytes = target.read_bytes() if target.exists() else b""
    after_bytes = serialized.encode("utf-8")
    before_hash = hashlib.sha256(before_bytes).hexdigest() if before_bytes else ""
    after_hash = hashlib.sha256(after_bytes).hexdigest()
    if before_hash == after_hash:
        return {
            "ok": True,
            "changed": False,
            "path": str(target),
            "sha256": after_hash,
            "message": "현재 기준과 동일하여 파일을 변경하지 않았습니다.",
        }
    if before_bytes:
        try:
            before_version = json.loads(before_bytes.decode("utf-8-sig")).get("version")
        except (UnicodeDecodeError, json.JSONDecodeError):
            before_version = None
        if before_version == payload.get("version"):
            return {
                "ok": False,
                "errors": [
                    "평가 기준 내용을 변경할 때는 실행 증적을 구분할 수 있도록 Rubric 버전도 변경해야 합니다."
                ],
            }

    history_dir = target.parent / "RubricHistory"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone()
    stamp = timestamp.strftime("%Y%m%d_%H%M%S_%f")
    backup_path = history_dir / f"{target.stem}_{stamp}.json"
    if before_bytes:
        backup_path.write_bytes(before_bytes)

    temp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        temp_path.write_bytes(after_bytes)
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    audit = {
        "changed_at": timestamp.isoformat(),
        "rubric_type": rubric_type,
        "rubric_version": payload.get("version"),
        "source": source,
        "target_file": target.name,
        "backup_file": backup_path.name if before_bytes else "",
        "before_sha256": before_hash,
        "after_sha256": after_hash,
    }
    with (history_dir / "rubric_changes.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "changed": True,
        "path": str(target),
        "backup_path": str(backup_path) if before_bytes else "",
        "sha256": after_hash,
        "message": "품질 평가 기준을 저장했습니다.",
    }


def test_case_summary() -> dict:
    cases = load_test_cases().get("cases", [])
    return {"total": len(cases), "categories": dict(Counter(case.get("category", "unknown") for case in cases))}


def audit_summary() -> dict:
    path = VOC_RUNTIME_DIR / ".runtime" / "audit" / "a2a_events.jsonl"
    if not path.exists():
        return {"exists": False, "events": 0, "traces": 0, "success": 0, "failure": 0, "path": str(path)}
    events = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {
        "exists": True,
        "events": len(events),
        "traces": len({event.get("trace_id") for event in events if event.get("trace_id")}),
        "success": sum(event.get("status") == "success" for event in events),
        "failure": sum(event.get("status") == "failure" for event in events),
        "path": str(path),
    }


def list_reports(category_label: str) -> list[dict]:
    folder_name = REPORT_CATEGORIES.get(category_label)
    if not folder_name:
        raise ValueError("알 수 없는 Report 분류입니다.")
    folder = VOC_REPORTS_DIR / folder_name
    if not folder.exists():
        return []
    rows = []
    for path in sorted(folder.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json"}:
            continue
        rows.append({
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "modified": path.stat().st_mtime,
        })
    return rows


def read_report(path_value: str, max_chars: int = 200_000) -> str:
    path = Path(path_value).resolve()
    report_root = VOC_REPORTS_DIR.resolve()
    if report_root not in path.parents or not path.is_file():
        raise ValueError("Report 루트 외부 파일은 읽을 수 없습니다.")
    return _safe_text(path.read_text(encoding="utf-8-sig", errors="replace")[:max_chars])


def load_guide(name: str) -> str:
    allowed = {
        "사용자 가이드": VOC_RUNTIME_DIR.parent / "README.md",
        "적용 가이드": VOC_REUSE_DOCS_DIR / "ADOPTION_GUIDE.md",
        "이식 가이드": VOC_REUSE_DOCS_DIR / "ADOPTION_GUIDE.md",
        "이식 체크리스트": VOC_REUSE_DOCS_DIR / "PORTABILITY_CHECKLIST.md",
        "실행 가이드": VOC_RUNTIME_DIR / "quality_diagnosis" / "RUN_QUALITY_DIAGNOSIS.md",
        "품질진단 실행": VOC_RUNTIME_DIR / "quality_diagnosis" / "RUN_QUALITY_DIAGNOSIS.md",
    }
    path = allowed.get(name)
    if not path or not path.exists():
        return "문서를 찾을 수 없습니다."
    return _safe_text(path.read_text(encoding="utf-8-sig", errors="replace"))
