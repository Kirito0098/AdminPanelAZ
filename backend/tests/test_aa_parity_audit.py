"""AdminAntizapret → AdminPanelAZ test suite parity audit (phase 32).

Maps all 53 AA pytest modules to AZ equivalents or documented N/A reasons.
Adds targeted behavioral tests for AA modules that have no direct file copy
(auth captcha threshold, traffic collector rows, wg subprocess errors).
"""

from unittest.mock import MagicMock, patch

from app.schemas import OpenVpnClient, WireGuardPeer
from app.services import wg_runtime
from app.services.ip_restriction import ip_restriction_service
from app.services.traffic.collector import build_status_rows

# AA module basename → (AZ module(s) or "N/A", note)
AA_PARITY_MATRIX: dict[str, tuple[str, str]] = {
    "test_access_remaining.py": ("test_access_remaining.py", "direct"),
    "test_admin_notify.py": ("test_admin_notify.py", "direct"),
    "test_admin_routes.py": ("test_security.py", "Flask admin routes → FastAPI auth/system"),
    "test_antizapret_backup.py": ("test_antizapret_backup.py", "direct"),
    "test_app_auto_backup.py": ("test_backup_scheduler.py", "renamed"),
    "test_audit_view_presenter_action_logs.py": ("N/A", "Jinja audit presenter"),
    "test_audit_view_presenter_tg.py": ("N/A", "Jinja audit presenter"),
    "test_auth_routes_login.py": ("test_security.py, test_aa_parity_audit.py", "JWT login + captcha threshold"),
    "test_background_tasks_service.py": ("test_background_tasks_service.py", "direct"),
    "test_backup_manager_service.py": ("test_backup_manager.py", "renamed"),
    "test_backup_telegram_job.py": ("test_backup_manager.py, test_admin_notify.py", "split coverage"),
    "test_catalog_data.py": ("N/A", "AA in-panel pytest catalog metadata"),
    "test_cidr_db_updater_service.py": ("test_cidr_db_updater_service.py", "direct"),
    "test_cidr_list_updater.py": ("test_cidr_list_updater.py", "direct"),
    "test_config_routes_openvpn_block.py": ("test_client_access_openvpn_block.py", "renamed"),
    "test_db_backup_export.py": ("test_backup_manager.py", "export via backup manager"),
    "test_db_migration_service.py": ("test_db_migration_service.py", "direct"),
    "test_edit_files_page_context.py": ("test_edit_files_api.py", "page context → API tests"),
    "test_feature_toggles.py": ("test_feature_toggles_service.py, test_feature_guards.py", "split"),
    "test_firewall_tools_check.py": ("test_firewall_tools_check.py", "direct"),
    "test_game_catalog_coverage.py": ("N/A", "game filters removed from AdminPanelAZ"),
    "test_http_security.py": ("test_http_security.py", "direct"),
    "test_index_page_context.py": ("N/A", "Jinja page context"),
    "test_index_routes_wg_access.py": ("test_wg_access_policy_service.py", "route logic in service tests"),
    "test_ip_restriction_scanner_block.py": ("test_ip_restriction_scanner_block.py", "direct"),
    "test_ip_restriction_temporary.py": ("test_ip_restriction_temporary.py", "direct"),
    "test_ip_restriction_whitelist_firewall_gating.py": (
        "test_ip_restriction_whitelist_firewall_gating.py",
        "direct",
    ),
    "test_jinja_templates_compile.py": ("N/A", "Jinja/Flask-only; intentionally not ported"),
    "test_maintenance_scheduler_backup.py": ("test_backup_scheduler.py", "scheduler parity"),
    "test_notify_time.py": ("test_notify_time.py", "direct"),
    "test_openvpn_access_policy_service.py": ("test_openvpn_access_policy_service.py", "direct"),
    "test_panel_port_firewall.py": ("test_panel_port_firewall.py", "direct"),
    "test_panel_publish_info.py": ("test_panel_publish_info.py", "direct"),
    "test_routing_page_context.py": ("N/A", "Jinja page context"),
    "test_safe_browsing_status_cli.py": ("test_safe_browsing_status_cli.py", "direct"),
    "test_scanner_firewall_store.py": ("test_scanner_firewall_store.py", "direct"),
    "test_script_executor.py": ("N/A", "Flask script executor UI"),
    "test_session_security.py": (
        "test_active_web_session.py, test_session_heartbeat.py",
        "Flask sessions → JWT/web sessions",
    ),
    "test_settings_api_action_logs_export.py": ("test_action_logs_export.py", "renamed"),
    "test_settings_api_cidr_games.py": ("test_cidr_db_presets.py", "N/A — game filters removed"),
    "test_settings_page_context.py": ("N/A", "Jinja page context"),
    "test_settings_post_handlers.py": ("test_settings_post_handlers.py", "direct"),
    "test_site_diagnostics.py": ("test_site_diagnostics.py", "direct"),
    "test_system_preflight.py": ("N/A", "AA install.sh preflight; AZ uses install.sh + menu"),
    "test_telegram_webapp_init_data.py": ("test_tg_mini_init_data.py", "renamed"),
    "test_temporary_whitelist_store.py": ("test_ip_restriction_temporary.py", "merged"),
    "test_tg_mini_session.py": ("test_tg_mini_init_data.py, test_security.py", "split"),
    "test_traffic_limit_notify.py": ("test_traffic_limit_notify.py", "direct"),
    "test_traffic_limit.py": ("test_traffic_limit.py", "direct"),
    "test_traffic_sync_cli.py": ("test_aa_parity_audit.py, test_traffic_limit.py", "CLI → worker collector"),
    "test_wg_access_policy_service.py": ("test_wg_access_policy_service.py", "direct"),
    "test_wg_awg_runtime_enforcer.py": ("test_wg_access_policy_service.py", "CLI enforcer → policy worker"),
    "test_wg_runtime_subprocess.py": ("test_wg_runtime.py, test_aa_parity_audit.py", "inline wg_runtime"),
}

AA_NON_PORTABLE = frozenset(
    name
    for name, (target, _) in AA_PARITY_MATRIX.items()
    if target == "N/A"
)


def test_all_aa_modules_accounted_for():
    assert len(AA_PARITY_MATRIX) == 53
    assert len(AA_NON_PORTABLE) == 10


def test_jinja_only_module_is_documented_non_portable():
    assert "test_jinja_templates_compile.py" in AA_NON_PORTABLE


def test_login_captcha_after_three_failed_attempts():
    client_ip = "203.0.113.50"
    ip_restriction_service.record_login_attempt(client_ip, success=True)

    assert ip_restriction_service.login_needs_captcha(client_ip) is False
    for _ in range(3):
        ip_restriction_service.record_login_attempt(client_ip, success=False)
    assert ip_restriction_service.login_needs_captcha(client_ip) is True

    ip_restriction_service.record_login_attempt(client_ip, success=True)
    assert ip_restriction_service.login_needs_captcha(client_ip) is False


def test_traffic_collector_build_status_rows():
    ovpn = OpenVpnClient(
        common_name="alice",
        profile="vpn-udp",
        real_address="1.2.3.4:12345",
        virtual_address="10.8.0.2",
        bytes_received=100,
        bytes_sent=200,
        connected_since="2023-11-14 12:00:00",
        connected_since_ts=1700000000,
    )
    wg = WireGuardPeer(
        interface="vpn",
        client_name="bob",
        public_key="abc123",
        endpoint="5.6.7.8:51820",
        allowed_ips="10.9.0.3/32",
        transfer_rx=300,
        transfer_tx=400,
    )

    rows = build_status_rows([ovpn], [wg])

    assert len(rows) == 2
    assert rows[0]["profile"] == "vpn-udp"
    assert rows[0]["traffic_clients"][0]["session_kind"] == "openvpn"
    assert rows[1]["profile"] == "vpn-wg"
    assert rows[1]["traffic_clients"][0]["peer_public_key"] == "abc123"


def test_wg_runtime_block_reports_subprocess_errors(tmp_path):
    config = tmp_path / "vpn.conf"
    config.write_text(
        "[Peer]\nPublicKey = peerkey\nAllowedIPs = 10.0.0.2/32\n",
        encoding="utf-8",
    )
    files = {"vpn": config}

    with patch.object(wg_runtime, "WG_CONFIG_FILES", files):
        with patch.object(wg_runtime, "_collect_client_peers", return_value=[("vpn", "peerkey")]):
            with patch.object(wg_runtime, "_run") as run_mock:
                run_mock.return_value = MagicMock(returncode=1, stderr="permission denied")
                result = wg_runtime.block_client_runtime("bob")

    assert result["success"] is False
    assert result["removed_count"] == 0
    assert result["error_count"] == 1
    assert "permission denied" in result["errors"][0]["stderr"]
