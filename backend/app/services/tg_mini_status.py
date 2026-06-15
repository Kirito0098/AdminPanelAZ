"""Read-only warper/CIDR status payloads for TG Mini App and bot."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.cidr.cidr_tasks import find_any_active_pipeline_task
from app.services.cidr.pipeline.deploy import list_compile_artifacts
from app.services.node_manager import get_active_adapter, get_active_node


def build_warper_status_payload(db: Session) -> dict:
    node = get_active_node(db)
    adapter = get_active_adapter(db)
    raw_status = adapter.get_warper_status()
    if isinstance(raw_status, dict):
        status_text = raw_status.get("status") or raw_status.get("mode") or str(raw_status)
        status_data = raw_status
    else:
        status_text = str(raw_status)
        status_data = {"status": status_text}
    return {
        "node_id": node.id,
        "node_name": node.name,
        "node_host": node.host,
        "status": status_text,
        "raw": status_data,
    }


def _summarize_last_compile() -> dict | None:
    from app.routers.cidr_db import _summarize_last_compile

    return _summarize_last_compile()


def _summarize_last_deploy() -> dict | None:
    from app.routers.cidr_db import _summarize_last_deploy

    return _summarize_last_deploy()


def build_cidr_status_payload(db: Session) -> dict:
    from app.cidr_database import CidrSessionLocal
    from app.models import ProviderMeta
    from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

    total_cidrs = int(db.query(func.coalesce(func.sum(ProviderMeta.cidr_count), 0)).scalar() or 0)
    active = find_any_active_pipeline_task()
    active_label = active.get("type") if active else None

    cidr_session = CidrSessionLocal()
    try:
        svc = CidrDbUpdaterService(db=db, cidr_db=cidr_session)
        status_data = svc.get_db_status()
    finally:
        cidr_session.close()

    compile_row = _summarize_last_compile() if list_compile_artifacts() else None
    deploy_row = _summarize_last_deploy()

    return {
        "total_cidrs": total_cidrs,
        "last_refresh_status": status_data.get("last_refresh_status"),
        "last_refresh_finished": status_data.get("last_refresh_finished"),
        "active_task": active_label,
        "last_compile": compile_row,
        "last_deploy": deploy_row,
    }
