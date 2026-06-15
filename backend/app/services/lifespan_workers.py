"""Background worker startup plan and task spawning for app lifespan."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from app.config import get_settings
from app.services.backup_scheduler import run_backup_scheduler_loop, run_runtime_backup_cleanup_loop
from app.services.cert_sync_worker import run_cert_sync_loop
from app.services.cidr.cidr_scheduler import run_cidr_db_scheduler_loop
from app.services.nightly_idle_restart_worker import run_nightly_idle_restart_loop
from app.services.node_health_worker import run_node_health_loop
from app.services.node_key_rotation import run_node_key_rotation_loop
from app.services.panel_resource_metrics_worker import run_panel_resource_metrics_loop
from app.services.resource_metrics_worker import run_resource_metrics_loop
from app.services.retention_worker import run_retention_loop
from app.services.traffic.worker import run_traffic_collector_loop
from app.services.wg_policy_sync_worker import run_wg_policy_sync_loop
from app.services.user_reminder_worker import run_user_reminder_loop
from app.services.noc_report_scheduler import run_noc_report_scheduler_loop
from app.services.webhook_delivery_worker import run_webhook_delivery_loop
from app.services.worker_lifecycle import (
    should_start_backup_scheduler,
    should_start_cert_sync,
    should_start_cidr_scheduler,
    should_start_key_rotation,
    should_start_nightly_idle_restart,
    should_start_node_health,
    should_start_panel_resource_metrics,
    should_start_resource_metrics,
    should_start_resource_monitor,
    should_start_retention,
    should_start_runtime_backup_cleanup,
    should_start_traffic_collector,
    should_start_wg_policy_sync,
    should_start_node_sync_reconcile,
    should_start_user_reminders,
    should_start_noc_report_scheduler,
)

TaskFactory = Callable[[], asyncio.Task]


def get_worker_startup_plan() -> dict[str, bool]:
    """Return which background workers should start (read at process startup)."""
    return {
        "traffic_collector": should_start_traffic_collector(),
        "cert_sync": should_start_cert_sync(),
        "node_health": should_start_node_health(),
        "resource_metrics": should_start_resource_metrics(),
        "panel_resource_metrics": should_start_panel_resource_metrics(),
        "backup_scheduler": should_start_backup_scheduler(),
        "runtime_backup_cleanup": should_start_runtime_backup_cleanup(),
        "cidr_scheduler": should_start_cidr_scheduler(),
        "wg_policy_sync": should_start_wg_policy_sync(),
        "node_sync_reconcile": should_start_node_sync_reconcile(),
        "nightly_idle_restart": should_start_nightly_idle_restart(),
        "key_rotation": should_start_key_rotation(),
        "retention": should_start_retention(),
        "resource_monitor": should_start_resource_monitor(),
        "user_reminders": should_start_user_reminders(),
        "noc_report_scheduler": should_start_noc_report_scheduler(),
    }


def spawn_background_tasks(
    *,
    app_root: Path,
    db_path: Path,
    env_path: Path,
    create_task: Callable = asyncio.create_task,
) -> dict[str, asyncio.Task | None]:
    """Create asyncio tasks for enabled workers. Used by main.py lifespan."""
    settings = get_settings()
    plan = get_worker_startup_plan()
    tasks: dict[str, asyncio.Task | None] = {}

    if plan["traffic_collector"]:
        tasks["traffic_collector"] = create_task(run_traffic_collector_loop())
    if plan["cert_sync"]:
        tasks["cert_sync"] = create_task(run_cert_sync_loop())
    if plan["node_health"]:
        tasks["node_health"] = create_task(run_node_health_loop())
    if plan["resource_metrics"]:
        tasks["resource_metrics"] = create_task(run_resource_metrics_loop())
    if plan["panel_resource_metrics"]:
        tasks["panel_resource_metrics"] = create_task(run_panel_resource_metrics_loop())
    if plan["backup_scheduler"]:
        tasks["backup_scheduler"] = create_task(
            run_backup_scheduler_loop(
                app_root=app_root,
                backup_root=Path(settings.backup_root),
                db_path=db_path,
                env_path=env_path,
            )
        )
    if plan["runtime_backup_cleanup"]:
        tasks["runtime_backup_cleanup"] = create_task(run_runtime_backup_cleanup_loop(env_path=env_path))
    if plan["cidr_scheduler"]:
        tasks["cidr_scheduler"] = create_task(run_cidr_db_scheduler_loop())
    if plan["wg_policy_sync"]:
        tasks["wg_policy_sync"] = create_task(run_wg_policy_sync_loop())
    if plan["node_sync_reconcile"]:
        tasks["node_sync_reconcile"] = create_task(run_node_sync_reconcile_loop())
    if plan["nightly_idle_restart"]:
        tasks["nightly_idle_restart"] = create_task(run_nightly_idle_restart_loop())
    if plan["key_rotation"]:
        tasks["key_rotation"] = create_task(run_node_key_rotation_loop())
    if plan["retention"]:
        tasks["retention"] = create_task(run_retention_loop())
    if plan["user_reminders"]:
        tasks["user_reminders"] = create_task(run_user_reminder_loop())
    if plan["noc_report_scheduler"]:
        tasks["noc_report_scheduler"] = create_task(run_noc_report_scheduler_loop())

    tasks["webhook_delivery"] = create_task(run_webhook_delivery_loop())

    return tasks


async def cancel_background_tasks(tasks: dict[str, asyncio.Task | None]) -> None:
    for task in tasks.values():
        if task is None:
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
