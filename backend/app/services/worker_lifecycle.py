"""Decide whether background workers should start (resource profiles + toggles)."""

from __future__ import annotations

from app.config import get_settings
from app.services.feature_guards import get_feature_service


def should_start_traffic_collector() -> bool:
    # Settings gate only — feature toggle is re-checked each collect loop tick
    # so TRAFFIC_SYNC / traffic_sync can flip without process restart.
    return get_settings().traffic_sync_enabled


def should_start_cert_sync() -> bool:
    # Always spawn — loop re-checks CERT_SYNC_ENABLED / openvpn each tick.
    return True


def should_start_node_health() -> bool:
    # Always spawn — loop re-checks NODE_HEALTH_SYNC_ENABLED each tick.
    return True


def should_start_resource_metrics() -> bool:
    return get_settings().resource_metrics_enabled


def should_start_panel_resource_metrics() -> bool:
    return get_settings().panel_resource_metrics_enabled


def should_start_backup_scheduler() -> bool:
    # Always spawn when lifecycle is on — loop re-checks backups toggle each hour.
    return True


def should_start_runtime_backup_cleanup() -> bool:
    # Always spawn — loop re-checks runtime_backup_cleanup toggle each hour.
    return True


def should_start_cidr_scheduler() -> bool:
    settings = get_settings()
    return settings.cidr_db_refresh_enabled and get_feature_service().is_enabled("routing")


def should_start_wg_policy_sync() -> bool:
    # Always spawn — loop re-checks wg_policy_sync toggle each tick.
    return True


def should_start_node_sync_reconcile() -> bool:
    return get_settings().node_sync_reconcile_enabled


def should_start_nightly_idle_restart() -> bool:
    # Always spawn — loop re-checks settings + nightly_idle_restart toggle each tick.
    return True


def should_start_key_rotation() -> bool:
    return get_settings().node_api_key_rotation_days > 0


def should_start_user_reminders() -> bool:
    return get_settings().self_service_reminder_enabled


def should_start_retention() -> bool:
    # Always spawn — loop re-checks RETENTION_ENABLED each tick so settings
    # API flips apply without process restart.
    return True


def should_start_resource_monitor() -> bool:
    return get_feature_service().is_enabled("resource_monitor")


def should_start_noc_report_scheduler() -> bool:
    settings = get_settings()
    return settings.noc_report_enabled and get_feature_service().is_enabled("telegram")


def should_start_alert_rules_worker() -> bool:
    # Always spawn — loop re-checks alert_rules_enabled + telegram each tick.
    return True


def should_start_awg2_expire() -> bool:
    return get_feature_service().is_enabled("awg2")


def should_start_cloudflare_ips_scheduler() -> bool:
    return True
