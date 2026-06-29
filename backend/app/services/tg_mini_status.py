"""Read-only warper/CIDR status payloads for TG Mini App and bot."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.cidr.cidr_tasks import find_any_active_pipeline_task
from app.services.cidr.pipeline.deploy import list_compile_artifacts
from app.services.node_manager import get_active_adapter, get_active_node


def _warper_fake_subnet(status_data: dict[str, Any]) -> str | None:
    subnet = status_data.get("subnet")
    if isinstance(subnet, dict):
        fake = subnet.get("fake")
        if isinstance(fake, str) and fake.strip():
            return fake.strip()
    fake_subnet = status_data.get("fake_subnet")
    if isinstance(fake_subnet, str) and fake_subnet.strip():
        return fake_subnet.strip()
    return None


def _warper_outbound_mode(status_data: dict[str, Any]) -> str | None:
    outbound = status_data.get("outbound_mode") or status_data.get("mode")
    if isinstance(outbound, str) and outbound.strip():
        return outbound.strip()
    return None


def _traffic_number(payload: dict[str, Any] | None, *keys: str) -> int | None:
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _warper_status_text(raw_status: dict[str, Any]) -> str:
    for key in ("status", "mode", "state"):
        value = raw_status.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "—"


def build_warper_status_payload(db: Session) -> dict:
    node = get_active_node(db)
    adapter = get_active_adapter(db)

    health: dict[str, Any] = {
        "installed": False,
        "active": False,
        "version": None,
        "conflict_antizapret_warp": False,
        "health_error": None,
    }
    try:
        health = adapter.get_warper_health()
    except Exception as exc:
        health["health_error"] = str(exc)

    raw_status: dict[str, Any] = {}
    status_text = "—"
    outbound_mode: str | None = None
    fake_subnet: str | None = None
    singbox_running: bool | None = None
    kresd_patched: bool | None = None

    if health.get("installed") and not health.get("health_error"):
        try:
            fetched = adapter.get_warper_status()
            if isinstance(fetched, dict):
                raw_status = fetched
                status_text = _warper_status_text(raw_status)
                outbound_mode = _warper_outbound_mode(raw_status)
                fake_subnet = _warper_fake_subnet(raw_status)
                singbox = raw_status.get("singbox")
                if isinstance(singbox, dict) and isinstance(singbox.get("running"), bool):
                    singbox_running = singbox["running"]
                kresd = raw_status.get("kresd")
                if isinstance(kresd, dict) and isinstance(kresd.get("patched"), bool):
                    kresd_patched = kresd["patched"]
        except Exception as exc:
            raw_status = {"error": str(exc)}
            status_text = "ошибка"

    domain_count: int | None = None
    traffic_tx: int | None = None
    traffic_rx: int | None = None
    if health.get("installed") and not health.get("conflict_antizapret_warp"):
        try:
            domains = adapter.get_warper_domains()
            if isinstance(domains, list):
                domain_count = len(domains)
        except Exception:
            pass
        try:
            traffic = adapter.get_warper_traffic("today")
            if isinstance(traffic, dict):
                traffic_tx = _traffic_number(traffic, "period_tx", "tx", "upload")
                traffic_rx = _traffic_number(traffic, "period_rx", "rx", "download")
        except Exception:
            pass

    return {
        "node_id": node.id,
        "node_name": node.name,
        "node_host": node.host,
        "status": status_text,
        "raw": raw_status,
        "installed": bool(health.get("installed")),
        "active": bool(health.get("active")),
        "version": health.get("version"),
        "conflict_antizapret_warp": bool(health.get("conflict_antizapret_warp")),
        "health_error": health.get("health_error"),
        "outbound_mode": outbound_mode,
        "fake_subnet": fake_subnet,
        "domain_count": domain_count,
        "traffic_tx": traffic_tx,
        "traffic_rx": traffic_rx,
        "singbox_running": singbox_running,
        "kresd_patched": kresd_patched,
    }


def _summarize_last_compile() -> dict | None:
    from app.routers.cidr_db import _summarize_last_compile

    return _summarize_last_compile()


def _summarize_last_deploy() -> dict | None:
    from app.routers.cidr_db import _summarize_last_deploy

    return _summarize_last_deploy()


def _cidr_task_type_label(task_type: str) -> str:
    labels = {
        "cidr_db_refresh": "Загрузка провайдеров",
        "cidr_db_refresh_dry_run": "Пробная загрузка",
        "antifilter_refresh": "Обновление AntiFilter",
        "cidr_generate_from_db": "Сборка из SQLite",
        "cidr_estimate_from_db": "Оценка сборки",
        "cidr_rollback": "Откат",
        "cidr_deploy": "Развёртывание",
    }
    return labels.get(task_type, task_type or "—")


def _summarize_pipeline_task(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    task_type = str(task.get("task_type") or "")
    return {
        "task_id": task.get("task_id") or task.get("id"),
        "task_type": task_type,
        "task_label": _cidr_task_type_label(task_type),
        "status": task.get("status"),
        "progress_percent": int(task.get("progress_percent") or 0),
        "progress_stage": task.get("progress_stage"),
        "message": task.get("message"),
    }


def build_cidr_status_payload(db: Session) -> dict:
    from app.cidr_database import CidrSessionLocal
    from app.models import ProviderMeta
    from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

    total_cidrs = int(db.query(func.coalesce(func.sum(ProviderMeta.cidr_count), 0)).scalar() or 0)
    active = find_any_active_pipeline_task()
    active_summary = _summarize_pipeline_task(active)
    active_label = active_summary["task_label"] if active_summary else None

    cidr_session = CidrSessionLocal()
    try:
        svc = CidrDbUpdaterService(db=db, cidr_db=cidr_session)
        status_data = svc.get_db_status()
    finally:
        cidr_session.close()

    providers = status_data.get("providers") if isinstance(status_data.get("providers"), dict) else {}
    providers_loaded = sum(
        1
        for meta in providers.values()
        if isinstance(meta, dict) and int(meta.get("cidr_count") or 0) > 0
    )
    alerts = status_data.get("alerts") if isinstance(status_data.get("alerts"), list) else []

    compile_row = _summarize_last_compile() if list_compile_artifacts() else None
    deploy_row = _summarize_last_deploy()

    return {
        "total_cidrs": total_cidrs,
        "last_refresh_status": status_data.get("last_refresh_status"),
        "last_refresh_finished": status_data.get("last_refresh_finished"),
        "last_refresh_started": status_data.get("last_refresh_started"),
        "active_task": active_label,
        "pipeline_task": active_summary,
        "providers_loaded": providers_loaded,
        "providers_total": len(providers),
        "alerts_count": len(alerts),
        "has_compile_artifacts": bool(list_compile_artifacts()),
        "last_compile": compile_row,
        "last_deploy": deploy_row,
    }
