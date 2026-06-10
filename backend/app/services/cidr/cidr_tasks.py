"""Thin wrapper over BackgroundTaskService for CIDR pipeline and pytest tasks."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.services.background_tasks import background_task_service

CIDR_TASK_RETENTION = timedelta(hours=2)

# In-memory fallback for unit tests without DB wiring
_CIDR_TASKS: dict[str, dict[str, Any]] = {}
_USE_MEMORY = False


def _use_memory_backend() -> bool:
    return _USE_MEMORY


def enable_memory_backend_for_tests(enabled: bool = True) -> None:
    global _USE_MEMORY
    _USE_MEMORY = enabled


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


def find_active_cidr_task(task_type: str) -> dict[str, Any] | None:
    if _use_memory_backend():
        for task in _CIDR_TASKS.values():
            if str(task.get("task_type") or "") != str(task_type or ""):
                continue
            if str(task.get("status") or "") in {"queued", "running"}:
                return dict(task)
        return None
    task = background_task_service.find_active_task(task_type)
    return background_task_service.serialize_background_task(task) if task else None


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


def start_cidr_task(task_id: str, runner: Callable) -> None:
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

        import threading

        threading.Thread(target=_worker, daemon=True).start()
        return

    background_task_service.start_cidr_runner(task_id, runner)
