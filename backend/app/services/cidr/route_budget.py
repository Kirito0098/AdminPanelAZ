"""OpenVPN route budget: node route-ips.txt, else last CIDR estimate, else compiled artifacts."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _artifact_stats() -> dict[str, Any]:
    """Controller artifacts: total CIDR count, file count, newest mtime as ISO timestamp."""
    artifacts = list_compile_artifacts()
    mtime = _newest_artifact_mtime(_list_artifact_filenames())
    return {
        "used": sum(int(item.get("cidr_count") or 0) for item in artifacts.values()),
        "count": len(artifacts),
        "finished_at": (
            datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            if mtime is not None
            else None
        ),
    }


def _estimate_payload(panel_used: int) -> dict[str, Any] | None:
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
        "panel_used": panel_used,
        "remaining": max(limit - used, 0),
        "original_total": _coerce_int(optimization.get("original_total_cidr_count")),
        "warning": optimization.get("warning"),
        "strategy": optimization.get("strategy"),
        "task_id": task.get("task_id") or task.get("id"),
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
    }


def _artifacts_payload(stats: dict[str, Any]) -> dict[str, Any]:
    """Budget from files already compiled into LIST_DIR."""
    if not stats["count"]:
        return {
            "available": False,
            "message": "Нет данных о бюджете маршрутов: оценка CIDR не выполнялась, артефакты не собраны",
        }

    used = stats["used"]
    limit = _get_openvpn_route_total_cidr_limit()

    return {
        "available": True,
        "source": "artifacts",
        "limit": limit,
        "used": used,
        "panel_used": used,
        "remaining": max(limit - used, 0),
        "original_total": None,
        "warning": "Собранные артефакты превышают лимит маршрутов" if used > limit else None,
        "strategy": "none",
        "finished_at": stats["finished_at"],
        "status": "artifacts",
    }


def _node_route_used(adapter: Any) -> int | None:
    """Actual route count from the node's result/route-ips.txt, None when unavailable."""
    try:
        files = (adapter.get_route_result_files() or {}).get("files") or []
    except Exception as exc:  # node offline or agent error - the budget must not fail
        logger.warning("route budget: node result files unavailable: %s", exc)
        return None

    for item in files:
        if not isinstance(item, dict) or item.get("key") != "route_ips":
            continue
        if not item.get("exists"):
            return None
        return _coerce_int(item.get("line_count"))
    return None


def _node_payload(node_used: int, stats: dict[str, Any], estimate: dict[str, Any] | None) -> dict[str, Any]:
    """Budget from the routes actually loaded by the node."""
    limit = _get_openvpn_route_total_cidr_limit()

    return {
        "available": True,
        "source": "node",
        "limit": limit,
        "used": node_used,
        "node_used": node_used,
        "panel_used": stats["used"],
        "remaining": max(limit - node_used, 0),
        "original_total": None,
        "warning": "Фактические маршруты узла превышают лимит маршрутов" if node_used > limit else None,
        "strategy": "none",
        "task_id": (estimate or {}).get("task_id"),
        "finished_at": (estimate or {}).get("finished_at") or stats["finished_at"],
        "status": "node",
    }


def build_route_budget_payload(adapter: Any = None) -> dict[str, Any]:
    """Node routes first, then the last estimate, then controller artifacts."""
    stats = _artifact_stats()
    if adapter is not None:
        node_used = _node_route_used(adapter)
        if node_used is not None:
            return _node_payload(node_used, stats, _estimate_payload(stats["used"]))
    return _estimate_payload(stats["used"]) or _artifacts_payload(stats)
