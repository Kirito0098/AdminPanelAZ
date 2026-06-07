"""In-memory background task queue for long CIDR pipeline operations."""

import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

CIDR_TASKS: dict[str, dict[str, Any]] = {}
CIDR_TASKS_LOCK = threading.Lock()
CIDR_TASK_RETENTION = timedelta(hours=2)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cleanup_cidr_tasks() -> None:
    cutoff = _now_utc() - CIDR_TASK_RETENTION
    with CIDR_TASKS_LOCK:
        stale = [
            task_id
            for task_id, task in CIDR_TASKS.items()
            if task.get("finished_at") and task["finished_at"] < cutoff
        ]
        for task_id in stale:
            CIDR_TASKS.pop(task_id, None)


def create_cidr_task(task_type: str, message: str) -> str:
    _cleanup_cidr_tasks()
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
    with CIDR_TASKS_LOCK:
        CIDR_TASKS[task_id] = task
    return task_id


def update_cidr_task(task_id: str, **fields: Any) -> None:
    with CIDR_TASKS_LOCK:
        task = CIDR_TASKS.get(task_id)
        if not task:
            return
        task.update(fields)
        task["updated_at"] = _now_utc()


def get_cidr_task(task_id: str) -> dict[str, Any] | None:
    with CIDR_TASKS_LOCK:
        task = CIDR_TASKS.get(task_id)
        return dict(task) if task else None


def find_active_cidr_task(task_type: str) -> dict[str, Any] | None:
    with CIDR_TASKS_LOCK:
        for task in CIDR_TASKS.values():
            if str(task.get("task_type") or "") != str(task_type or ""):
                continue
            if str(task.get("status") or "") in {"queued", "running"}:
                return dict(task)
    return None


def serialize_cidr_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = dict(task)
    for key in ("created_at", "started_at", "finished_at", "updated_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if isinstance(value, datetime) else None
    return payload


def start_cidr_task(task_id: str, runner: Callable) -> None:
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

    threading.Thread(target=_worker, daemon=True).start()
