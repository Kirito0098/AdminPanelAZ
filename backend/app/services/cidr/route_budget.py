"""OpenVPN route budget: last CIDR estimate, else compiled LIST_DIR artifacts."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.services.cidr.cidr_tasks import find_last_completed_cidr_task
from app.services.cidr.pipeline.constants import _get_openvpn_route_total_cidr_limit
from app.services.cidr.pipeline.deploy import (
    _artifact_path,
    _list_artifact_filenames,
    list_compile_artifacts,
)


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _estimate_payload() -> dict[str, Any] | None:
    """Budget from the last estimate task, None when it has no optimization meta."""
    task = find_last_completed_cidr_task("cidr_estimate_from_db")
    if not task:
        return None

    result = task.get("result") or {}
    optimization = result.get("global_route_optimization") or {}
    limit = _coerce_int(optimization.get("limit"))
    used = _coerce_int(optimization.get("compressed_total_cidr_count"))
    if limit is None or used is None:
        return None

    return {
        "available": True,
        "source": "estimate",
        "limit": limit,
        "used": used,
        "remaining": max(limit - used, 0),
        "original_total": _coerce_int(optimization.get("original_total_cidr_count")),
        "warning": optimization.get("warning"),
        "strategy": optimization.get("strategy"),
        "task_id": task.get("task_id") or task.get("id"),
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
    }


def _newest_artifact_mtime(filenames: list[str]) -> float | None:
    newest: float | None = None
    for filename in filenames:
        path = _artifact_path(filename)
        if path is None:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def _artifacts_payload() -> dict[str, Any]:
    """Budget from files already compiled into LIST_DIR."""
    artifacts = list_compile_artifacts()
    if not artifacts:
        return {
            "available": False,
            "message": "Нет данных о бюджете маршрутов: оценка CIDR не выполнялась, артефакты не собраны",
        }

    used = sum(int(item.get("cidr_count") or 0) for item in artifacts.values())
    limit = _get_openvpn_route_total_cidr_limit()
    mtime = _newest_artifact_mtime(_list_artifact_filenames())
    finished_at = (
        datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat() if mtime is not None else None
    )

    return {
        "available": True,
        "source": "artifacts",
        "limit": limit,
        "used": used,
        "remaining": max(limit - used, 0),
        "original_total": None,
        "warning": "Собранные артефакты превышают лимит маршрутов" if used > limit else None,
        "strategy": "none",
        "finished_at": finished_at,
        "status": "artifacts",
    }


def build_route_budget_payload() -> dict[str, Any]:
    return _estimate_payload() or _artifacts_payload()
