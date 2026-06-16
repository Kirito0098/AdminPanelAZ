"""Decide whether background workers should start (resource profiles + toggles)."""

from __future__ import annotations

from app.config import get_settings
from app.services.feature_guards import get_feature_service


def should_start_traffic_collector() -> bool:
    settings = get_settings()
    return settings.traffic_sync_enabled and get_feature_service().is_enabled("traffic_sync")


def should_start_cert_sync() -> bool:
    return get_settings().cert_sync_enabled


def should_start_node_health() -> bool:
    return get_settings().node_health_sync_enabled


def should_start_resource_metrics() -> bool:
    return get_settings().resource_metrics_enabled


def should_start_panel_resource_metrics() -> bool:
    return get_settings().panel_resource_metrics_enabled


def should_start_backup_scheduler() -> bool:
    return get_feature_service().is_enabled("backups")


def should_start_runtime_backup_cleanup() -> bool:
    return get_feature_service().is_enabled("runtime_backup_cleanup")


def should_start_cidr_scheduler() -> bool:
    settings = get_settings()
    return settings.cidr_db_refresh_enabled and get_feature_service().is_enabled("routing")


def should_start_wg_policy_sync() -> bool:
    settings = get_settings()
    return settings.wg_policy_sync_enabled and get_feature_service().is_enabled("wg_policy_sync")


def should_start_node_sync_reconcile() -> bool:
    return get_settings().node_sync_reconcile_enabled


def should_start_nightly_idle_restart() -> bool:
    settings = get_settings()
    return settings.nightly_idle_restart_enabled and get_feature_service().is_enabled("nightly_idle_restart")


def should_start_key_rotation() -> bool:
    return get_settings().node_api_key_rotation_days > 0


def should_start_user_reminders() -> bool:
    return get_settings().self_service_reminder_enabled


def should_start_retention() -> bool:
    return get_settings().retention_enabled


def should_start_resource_monitor() -> bool:
    return get_feature_service().is_enabled("resource_monitor")


def should_start_noc_report_scheduler() -> bool:
    settings = get_settings()
    return settings.noc_report_enabled and get_feature_service().is_enabled("telegram")


def should_start_alert_rules_worker() -> bool:
    settings = get_settings()
    return settings.alert_rules_enabled and get_feature_service().is_enabled("telegram")
