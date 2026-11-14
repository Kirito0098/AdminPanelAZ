"""Thin wrapper over BackgroundTaskService for CIDR pipeline tasks."""

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException

from app.services.background_tasks import background_task_service

CIDR_TASK_RETENTION = timedelta(hours=2)

ACTIVE_PIPELINE_TASK_TYPES = (
    "cidr_db_refresh",
    "cidr_db_refresh_dry_run",
    "antifilter_refresh",
    "cidr_generate_from_db",
    "cidr_estimate_from_db",
    "cidr_deploy",
    "cidr_rollback",
)

CIDR_TASK_CANCELLED_MESSAGE = "Операция отменена: превышено время выполнения"

# Serializes "pipeline is idle" check with task creation: two tabs can otherwise
# both pass the check and start two pipelines. One uvicorn process == one lock.
_PIPELINE_LOCK = threading.Lock()

# Cooperative cancel flags: a stale task keeps writing until the runner notices.
_CANCEL_LOCK = threading.Lock()
_CANCEL_REQUESTED: set[str] = set()


class CidrTaskCancelled(BaseException):
    """Cooperative cancel signal.

    Derives from BaseException on purpose: the pipeline wraps progress callbacks
    in ``except Exception`` guards, which must not swallow a cancel request.
    """


CIDR_TASK_STALE_SECONDS: dict[str, int] = {
    "antifilter_refresh": 720,
    "cidr_db_refresh": 3600,
    "cidr_db_refresh_dry_run": 3600,
    "cidr_generate_from_db": 1800,
    "cidr_estimate_from_db": 900,
    "cidr_deploy": 1800,
    "cidr_rollback": 1800,
}

# In-memory fallback for unit tests without DB wiring
_CIDR_TASKS: dict[str, dict[str, Any]] = {}
_USE_MEMORY = False


def _use_memory_backend() -> bool:
    return _USE_MEMORY


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cleanup_memory_tasks() -> None:
    cutoff = _now_utc() - CIDR_TASK_RETENTION
    stale = [
        task_id
        for task_id, task in _CIDR_TASKS.items()
        if task.get("finished_at") and task["finished_at"] < cutoff
    ]
    for task_id in stale:
        _CIDR_TASKS.pop(task_id, None)


def create_cidr_task(task_type: str, message: str) -> str:
    if _use_memory_backend():
        _cleanup_memory_tasks()
        import secrets

        task_id = secrets.token_hex(16)
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "queued",
            "message": str(message or "Задача поставлена в очередь"),
            "progress_percent": 0,
            "progress_stage": "Ожидание запуска...",
            "error": None,
            "result": None,
            "created_at": _now_utc(),
            "started_at": None,
            "finished_at": None,
            "updated_at": _now_utc(),
        }
        _CIDR_TASKS[task_id] = task
        return task_id
    return background_task_service.create_queued_task(task_type, message)


def update_cidr_task(task_id: str, **fields: Any) -> None:
    if _use_memory_backend():
        task = _CIDR_TASKS.get(task_id)
        if not task:
            return
        task.update(fields)
        task["updated_at"] = _now_utc()
        return
    background_task_service.update_background_task(task_id, **fields)


def get_cidr_task(task_id: str) -> dict[str, Any] | None:
    if _use_memory_backend():
        task = _CIDR_TASKS.get(task_id)
        return dict(task) if task else None
    task = background_task_service.get_task(task_id)
    return background_task_service.serialize_background_task(task) if task else None


def find_any_active_pipeline_task() -> dict[str, Any] | None:
    return find_active_pipeline_task()


def find_active_pipeline_task(*, exclude_task_type: str | None = None) -> dict[str, Any] | None:
    """Return any unfinished CIDR pipeline task, optionally skipping one type."""
    for task_type in ACTIVE_PIPELINE_TASK_TYPES:
        if exclude_task_type and task_type == exclude_task_type:
            continue
        task = find_active_cidr_task(task_type)
        if task:
            return task
    return None


def _pipeline_busy_error(active: dict[str, Any]) -> HTTPException:
    task_type = str(active.get("task_type") or "unknown")
    return HTTPException(
        status_code=409,
        detail=f"Другая операция с CIDR уже выполняется: {task_type}",
    )


def assert_pipeline_idle() -> None:
    """Reject the call with 409 when any CIDR pipeline task is still running."""
    active = find_active_pipeline_task()
    if active:
        raise _pipeline_busy_error(active)


def start_pipeline_task(
    task_type: str,
    message: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Atomically check the pipeline and create the task.

    Returns ``(task_id, active_task)``. ``active_task`` is the running task of
    the same type (callers keep answering ``queued: true`` with its id); a task
    of another type raises 409. Holding ``_PIPELINE_LOCK`` makes the
    check-then-create pair race-free inside one uvicorn process.
    """
    with _PIPELINE_LOCK:
        active = find_active_pipeline_task(exclude_task_type=task_type)
        if active:
            raise _pipeline_busy_error(active)
        same_type = find_active_cidr_task(task_type)
        if same_type:
            return None, same_type
        return create_cidr_task(task_type, message), None


def request_cancel(task_id: str) -> None:
    """Ask the runner of ``task_id`` to stop at its next checkpoint."""
    with _CANCEL_LOCK:
        _CANCEL_REQUESTED.add(str(task_id))


def is_cancel_requested(task_id: str) -> bool:
    with _CANCEL_LOCK:
        return str(task_id) in _CANCEL_REQUESTED


def clear_cancel(task_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCEL_REQUESTED.discard(str(task_id))


def _parse_task_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _task_age_seconds(task: dict[str, Any]) -> float | None:
    started = _parse_task_datetime(task.get("started_at")) or _parse_task_datetime(task.get("created_at"))
    if not started:
        return None
    return max(0.0, (_now_utc() - started).total_seconds())


def fail_stale_cidr_task(task: dict[str, Any], *, max_age_seconds: int) -> bool:
    """Mark an active task as failed if it exceeded max_age_seconds."""
    status = str(task.get("status") or "")
    if status not in {"queued", "running"}:
        return False
    age = _task_age_seconds(task)
    if age is None or age <= max_age_seconds:
        return False
    task_id = str(task.get("task_id") or task.get("id") or "")
    if not task_id:
        return False
    request_cancel(task_id)
    update_cidr_task(
        task_id,
        status="failed",
        progress_percent=100,
        progress_stage="Задача прервана по таймауту",
        message="Задача прервана по таймауту",
        error="Превышено время выполнения",
        finished_at=_now_utc(),
    )
    return True


def find_active_cidr_task(task_type: str) -> dict[str, Any] | None:
    if _use_memory_backend():
        for task in _CIDR_TASKS.values():
            if str(task.get("task_type") or "") != str(task_type or ""):
                continue
            if str(task.get("status") or "") in {"queued", "running"}:
                active = dict(task)
                if fail_stale_cidr_task(
                    active,
                    max_age_seconds=CIDR_TASK_STALE_SECONDS.get(task_type, 3600),
                ):
                    return None
                return active
        return None
    task = background_task_service.find_active_task(task_type)
    if not task:
        return None
    serialized = background_task_service.serialize_background_task(task)
    if fail_stale_cidr_task(
        serialized,
        max_age_seconds=CIDR_TASK_STALE_SECONDS.get(task_type, 3600),
    ):
        return None
    return serialized


def find_last_completed_cidr_task(task_type: str) -> dict[str, Any] | None:
    if _use_memory_backend():
        candidates = [
            dict(task)
            for task in _CIDR_TASKS.values()
            if str(task.get("task_type") or "") == str(task_type or "")
            and str(task.get("status") or "") in {"completed", "failed"}
        ]
        if not candidates:
            return None

        def _sort_key(item: dict[str, Any]) -> float:
            value = item.get("finished_at") or item.get("created_at")
            if isinstance(value, datetime):
                return value.timestamp()
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    return 0.0
            return 0.0

        return max(candidates, key=_sort_key)
    task = background_task_service.find_last_completed_task(task_type)
    return background_task_service.serialize_background_task(task) if task else None


def serialize_cidr_task(task: dict[str, Any]) -> dict[str, Any]:
    return background_task_service.serialize_background_task(task)


def _cancellable_progress(task_id: str, progress_callback: Callable) -> Callable:
    """Abort the runner with ``CidrTaskCancelled`` once cancel is requested.

    Only the runner thread raises: heartbeat threads inside the ingest loop may
    call the same callback and must not die with an unhandled exception.
    """
    owner = threading.get_ident()

    def _callback(percent: int, stage: str) -> None:
        if is_cancel_requested(task_id) and threading.get_ident() == owner:
            raise CidrTaskCancelled(task_id)
        progress_callback(percent, stage)

    return _callback


def _guarded_runner(task_id: str, runner: Callable) -> Callable:
    """Make ``runner`` stop at the next progress checkpoint after a cancel."""

    def _run(progress_callback: Callable) -> dict[str, Any]:
        try:
            return runner(_cancellable_progress(task_id, progress_callback)) or {}
        except CidrTaskCancelled:
            update_cidr_task(
                task_id,
                status="failed",
                progress_percent=100,
                progress_stage="Операция отменена",
                message=CIDR_TASK_CANCELLED_MESSAGE,
                error=CIDR_TASK_CANCELLED_MESSAGE,
                finished_at=_now_utc(),
            )
            return {
                "success": False,
                "cancelled": True,
                "message": CIDR_TASK_CANCELLED_MESSAGE,
            }
        finally:
            clear_cancel(task_id)

    return _run


def start_cidr_task(task_id: str, runner: Callable) -> None:
    runner = _guarded_runner(task_id, runner)
    if _use_memory_backend():
        def _progress_callback(percent: int, stage: str) -> None:
            update_cidr_task(
                task_id,
                status="running",
                progress_percent=max(0, min(99, int(percent))),
                progress_stage=str(stage or "Выполняется операция"),
                message=str(stage or "Выполняется операция"),
            )

        def _worker() -> None:
            update_cidr_task(
                task_id,
                status="running",
                progress_percent=1,
                progress_stage="Подготовка...",
                started_at=_now_utc(),
            )
            try:
                result = runner(_progress_callback) or {}
                if result.get("cancelled"):
                    update_cidr_task(
                        task_id,
                        status="failed",
                        progress_percent=100,
                        progress_stage="Операция отменена",
                        message=CIDR_TASK_CANCELLED_MESSAGE,
                        error=CIDR_TASK_CANCELLED_MESSAGE,
                        result=result,
                        finished_at=_now_utc(),
                    )
                    return
                if not bool(result.get("success")):
                    update_cidr_task(
                        task_id,
                        status="failed",
                        progress_percent=100,
                        progress_stage="Операция завершилась с ошибкой",
                        message=str(result.get("message") or "Операция завершилась с ошибкой"),
                        error=str(result.get("message") or "Операция завершилась с ошибкой"),
                        result=result,
                        finished_at=_now_utc(),
                    )
                    return
                update_cidr_task(
                    task_id,
                    status="completed",
                    progress_percent=100,
                    progress_stage="Операция завершена",
                    message=str(result.get("message") or "Операция завершена"),
                    result=result,
                    error=None,
                    finished_at=_now_utc(),
                )
            except Exception as exc:
                update_cidr_task(
                    task_id,
                    status="failed",
                    progress_percent=100,
                    progress_stage="Операция завершилась с ошибкой",
                    message="Операция завершилась с ошибкой",
                    error=str(exc),
                    finished_at=_now_utc(),
                )

        threading.Thread(target=_worker, daemon=True).start()
        return

    background_task_service.start_cidr_runner(task_id, runner)
