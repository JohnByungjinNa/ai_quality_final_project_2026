from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Any, Callable
from uuid import uuid4


_LOCK = RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voc-background")
_JOBS: dict[str, dict[str, Any]] = {}
_MAX_RETAINED_JOBS = 100


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _trim_completed_jobs() -> None:
    completed = sorted(
        (
            job
            for job in _JOBS.values()
            if job.get("status") in {"COMPLETED", "ERROR"}
        ),
        key=lambda job: job.get("finished_at", ""),
    )
    for job in completed[: max(0, len(_JOBS) - _MAX_RETAINED_JOBS)]:
        _JOBS.pop(job["job_id"], None)


def update_background_job(job_id: str, **changes: Any) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        progress = changes.pop("progress", None)
        if isinstance(progress, dict):
            job["progress"] = {**job.get("progress", {}), **deepcopy(progress)}
        job.update(deepcopy(changes))
        job["updated_at"] = _now_iso()


def _run_job(
    job_id: str,
    worker: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    try:
        result = worker(job_id, *args, **kwargs)
    except Exception as exc:
        update_background_job(
            job_id,
            status="ERROR",
            error=f"{type(exc).__name__}: {exc}",
            finished_at=_now_iso(),
        )
        raise
    update_background_job(
        job_id,
        status="COMPLETED",
        result=result,
        finished_at=_now_iso(),
    )
    return result


def start_background_job(
    kind: str,
    target_id: str,
    worker: Callable[..., Any],
    *args: Any,
    progress: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str:
    job_id = f"{kind}-{uuid4().hex}"
    now = _now_iso()
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "target_id": target_id,
            "status": "RUNNING",
            "progress": deepcopy(progress or {}),
            "result": None,
            "error": "",
            "started_at": now,
            "updated_at": now,
            "finished_at": "",
            "future": None,
        }
        future = _EXECUTOR.submit(_run_job, job_id, worker, args, kwargs)
        _JOBS[job_id]["future"] = future
        _trim_completed_jobs()
    return job_id


def background_job_snapshot(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(str(job_id or ""))
        if not job:
            return None
        snapshot = {
            key: deepcopy(value)
            for key, value in job.items()
            if key != "future"
        }
        future: Future | None = job.get("future")
        snapshot["done"] = bool(future and future.done())
        return snapshot


def discard_background_job(job_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(str(job_id or ""))
        if not job:
            return
        future: Future | None = job.get("future")
        if future and not future.done():
            return
        _JOBS.pop(job_id, None)
