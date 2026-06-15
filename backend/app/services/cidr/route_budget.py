"""Extract OpenVPN route budget metadata from the last CIDR estimate task."""

from __future__ import annotations

from typing import Any

from app.services.cidr.cidr_tasks import find_last_completed_cidr_task


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def build_route_budget_payload() -> dict[str, Any]:
    task = find_last_completed_cidr_task("cidr_estimate_from_db")
    if not task:
        return {
            "available": False,
            "message": "Оценка CIDR ещё не выполнялась",
        }

    result = task.get("result") or {}
    optimization = result.get("global_route_optimization") or {}
    limit = _coerce_int(optimization.get("limit"))
    used = _coerce_int(optimization.get("compressed_total_cidr_count"))
    original = _coerce_int(optimization.get("original_total_cidr_count"))
    if limit is None or used is None:
        return {
            "available": False,
            "message": "В последней оценке нет данных о лимите маршрутов",
            "task_id": task.get("task_id") or task.get("id"),
            "finished_at": task.get("finished_at"),
        }

    remaining = max(limit - used, 0)
    return {
        "available": True,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "original_total": original,
        "warning": optimization.get("warning"),
        "strategy": optimization.get("strategy"),
        "task_id": task.get("task_id") or task.get("id"),
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
    }
