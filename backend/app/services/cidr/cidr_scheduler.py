"""Scheduled nightly CIDR DB refresh worker."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.cidr.pipeline.deploy import compute_artifact_stamp
from app.services.cidr.pipeline.orchestrator import run_compile, run_ingest, run_multi_deploy

logger = logging.getLogger(__name__)


def _seconds_until_next_run(hour: int, minute: int) -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _resolve_cron_deploy_kwargs(settings: Settings) -> dict[str, Any]:
    target = settings.cidr_db_deploy_target
    if target == "all_online":
        return {"all_online": True}
    if target == "node_ids":
        node_ids = settings.cidr_db_deploy_target_node_id_list
        if not node_ids:
            return {}
        return {"target_node_ids": node_ids}
    return {}


def _summarize_compile_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "message": result.get("message"),
        "updated": result.get("updated") or [],
        "failed": result.get("failed") or [],
        "skipped": result.get("skipped") or [],
    }


def _summarize_deploy_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "message": result.get("message"),
        "artifact_stamp": result.get("artifact_stamp"),
        "nodes_deployed": result.get("nodes_deployed", 0),
        "nodes_failed": result.get("nodes_failed", 0),
        "nodes_skipped": result.get("nodes_skipped", 0),
        "per_node": result.get("per_node") or [],
    }


def run_nightly_cidr_pipeline(db: Session, settings: Settings) -> dict[str, Any]:
    """Run ingest and optionally compile + deploy for the nightly cron."""
    svc = CidrDbUpdaterService(db=db)
    summary: dict[str, Any] = {"refresh": None, "compile": None, "deploy": None}

    logger.info("CIDR DB scheduler: starting nightly refresh")
    refresh_result = run_ingest(db, triggered_by="cron")
    summary["refresh"] = refresh_result
    log_id = refresh_result.get("log_id")

    logger.info(
        "CIDR DB scheduler: refresh done status=%s updated=%d failed=%d",
        refresh_result.get("status"),
        refresh_result.get("providers_updated", 0),
        refresh_result.get("providers_failed", 0),
    )

    if not settings.cidr_db_compile_after_refresh:
        return summary

    refresh_status = str(refresh_result.get("status") or "")
    if refresh_status not in ("ok", "partial"):
        logger.info(
            "CIDR DB scheduler: skipping compile after refresh (status=%s)",
            refresh_status,
        )
        if log_id:
            svc.append_refresh_log_pipeline_details(
                log_id,
                {
                    "compile_after_refresh": True,
                    "compile_skipped_reason": f"refresh_status={refresh_status}",
                },
            )
        return summary

    logger.info("CIDR DB scheduler: starting compile after refresh")
    compile_result = run_compile()
    summary["compile"] = compile_result
    artifact_stamp = compute_artifact_stamp()
    compiled_at = datetime.now(timezone.utc).isoformat()

    if log_id:
        svc.append_refresh_log_pipeline_details(
            log_id,
            {
                "compile_after_refresh": True,
                "compiled_at": compiled_at,
                "artifact_stamp": artifact_stamp,
                "compile": _summarize_compile_result(compile_result),
            },
        )

    logger.info(
        "CIDR DB scheduler: compile done success=%s updated=%d",
        compile_result.get("success"),
        len(compile_result.get("updated") or []),
    )

    if not settings.cidr_db_deploy_after_compile:
        return summary

    compile_ok = bool(compile_result.get("success") or compile_result.get("updated"))
    if not compile_ok:
        logger.info("CIDR DB scheduler: skipping deploy after compile (compile failed)")
        if log_id:
            svc.append_refresh_log_pipeline_details(
                log_id,
                {
                    "deploy_after_compile": True,
                    "deploy_skipped_reason": "compile_failed",
                },
            )
        return summary

    deploy_kwargs = _resolve_cron_deploy_kwargs(settings)
    if settings.cidr_db_deploy_target == "node_ids" and not deploy_kwargs:
        logger.warning(
            "CIDR DB scheduler: CIDR_DB_DEPLOY_TARGET=node_ids but no node IDs configured — deploy skipped",
        )
        if log_id:
            svc.append_refresh_log_pipeline_details(
                log_id,
                {
                    "deploy_after_compile": True,
                    "deploy_target": settings.cidr_db_deploy_target,
                    "deploy_skipped_reason": "empty_node_ids",
                },
            )
        return summary

    logger.info(
        "CIDR DB scheduler: starting deploy after compile (target=%s)",
        settings.cidr_db_deploy_target,
    )
    deploy_result = run_multi_deploy(
        db,
        files=compile_result.get("updated"),
        sync_after=True,
        apply_after=False,
        **deploy_kwargs,
    )
    summary["deploy"] = deploy_result

    if log_id:
        svc.append_refresh_log_pipeline_details(
            log_id,
            {
                "deploy_after_compile": True,
                "deploy_target": settings.cidr_db_deploy_target,
                "deployed_at": datetime.now(timezone.utc).isoformat(),
                "deployed_artifact_stamp": deploy_result.get("artifact_stamp") or artifact_stamp,
                "deploy": _summarize_deploy_result(deploy_result),
            },
        )

    logger.info(
        "CIDR DB scheduler: deploy done success=%s nodes=%d failed=%d skipped=%d",
        deploy_result.get("success"),
        deploy_result.get("nodes_deployed", 0),
        deploy_result.get("nodes_failed", 0),
        deploy_result.get("nodes_skipped", 0),
    )
    return summary


async def run_cidr_db_scheduler_loop() -> None:
    settings = get_settings()
    while True:
        try:
            if not settings.cidr_db_refresh_enabled:
                await asyncio.sleep(3600)
                continue
            delay = _seconds_until_next_run(settings.cidr_db_refresh_hour, settings.cidr_db_refresh_minute)
            logger.info("CIDR DB scheduler: next refresh in %.0f seconds", delay)
            await asyncio.sleep(delay)
            db = SessionLocal()
            try:
                run_nightly_cidr_pipeline(db, settings)
            finally:
                db.close()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("CIDR DB scheduler error: %s", exc)
            await asyncio.sleep(300)
