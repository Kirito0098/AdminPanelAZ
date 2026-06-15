"""Light and deep health checks for production monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, NodeStatus, UserTrafficSample

settings = get_settings()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def build_light_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "resource_profile": settings.resource_profile,
    }


def _sqlite_ok(engine, label: str) -> dict[str, Any]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "label": label}
    except Exception as exc:
        return {"status": "error", "label": label, "error": str(exc)}


def _db_path_from_url(db_url: str, app_root: Path) -> Path:
    db_path = Path(db_url.replace("sqlite:///", ""))
    if not db_path.is_absolute():
        db_path = app_root / db_path
    return db_path


def build_deep_health(db: Session, *, app_root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **build_light_health(),
        "checks": {},
        "timestamp": _utcnow_iso(),
    }
    checks = payload["checks"]

    main_db = _sqlite_ok(db.get_bind(), "main_db")
    checks["main_db"] = main_db

    cidr_path = _db_path_from_url(settings.cidr_database_url, app_root)
    cidr_check: dict[str, Any] = {"status": "ok", "label": "cidr_db", "path": str(cidr_path)}
    if not cidr_path.is_file():
        cidr_check["status"] = "error"
        cidr_check["error"] = "cidr database file missing"
    checks["cidr_db"] = cidr_check

    try:
        last_sync = db.query(func.max(UserTrafficSample.created_at)).scalar()
        lag_seconds = None
        if last_sync is not None:
            lag_seconds = max(
                0,
                int((datetime.utcnow() - last_sync).total_seconds()),
            )
        checks["traffic_sync"] = {
            "status": "ok" if last_sync else "warning",
            "last_sample_at": last_sync.isoformat() if last_sync else None,
            "lag_seconds": lag_seconds,
            "stale_threshold_seconds": settings.traffic_db_stale_seconds,
            "stale": bool(lag_seconds is not None and lag_seconds > settings.traffic_db_stale_seconds),
        }
    except Exception as exc:
        checks["traffic_sync"] = {"status": "error", "error": str(exc)}

    node_check: dict[str, Any] = {"status": "skipped", "nodes": []}
    if settings.health_deep_node_ping:
        nodes = db.query(Node).all()
        online = 0
        entries = []
        for node in nodes:
            entry = {"id": node.id, "name": node.name, "status": node.status.value if node.status else None}
            if node.status == NodeStatus.online:
                online += 1
                try:
                    from app.services.node_manager import check_node_health

                    health = check_node_health(node)
                    entry["reachable"] = bool(health.get("online"))
                    if not entry["reachable"]:
                        entry["error"] = health.get("error") or "unreachable"
                except Exception as exc:
                    entry["reachable"] = False
                    entry["error"] = str(exc)
            entries.append(entry)
        node_check = {
            "status": "ok" if online > 0 or not nodes else "warning",
            "online_count": online,
            "total_count": len(nodes),
            "nodes": entries,
        }
    checks["active_nodes"] = node_check

    failed = [
        name
        for name, item in checks.items()
        if isinstance(item, dict) and item.get("status") == "error"
    ]
    payload["status"] = "degraded" if failed else "ok"
    if failed:
        payload["failed_checks"] = failed
    return payload
