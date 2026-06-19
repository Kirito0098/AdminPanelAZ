"""Stage 6 self-service: quotas, traffic scope, reminders, TG commands."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.auth import create_access_token, get_password_hash
from app.models import AppSetting, Node, User, UserRole, VpnConfig, VpnType
from app.schemas import TrafficClientRow, TrafficSummary
from app.services.self_service import (
    REMINDER_DEDUP_SECONDS,
    count_user_configs,
    enforce_user_can_create_config,
    record_reminder_sent,
    reminder_recently_sent,
)


def _set_active_node(session_factory, node_id: int) -> None:
    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
        if row:
            row.value = str(node_id)
        else:
            db.add(AppSetting(key="active_node_id", value=str(node_id)))
        db.commit()
    finally:
        db.close()


def _set_quota_default(session_factory, value: str) -> None:
    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "user_config_quota_default").first()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key="user_config_quota_default", value=value))
        db.commit()
    finally:
        db.close()


def _create_panel_user(session_factory, username: str, role: UserRole = UserRole.user) -> User:
    db = session_factory()
    try:
        user = User(
            username=username,
            password_hash=get_password_hash("secret123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def test_config_quota_endpoint(api_test_env):
    client = TestClient(api_test_env["app"])
    node = api_test_env["node"]
    _set_active_node(api_test_env["session_factory"], node.id)
    _set_quota_default(api_test_env["session_factory"], "2")

    panel_user = _create_panel_user(api_test_env["session_factory"], "quota_user")
    token = create_access_token({"sub": panel_user.username, "role": panel_user.role.value})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/configs/quota", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["used"] == 0
    assert body["limit"] == 2
    assert body["can_create"] is True


def test_count_user_configs_dedupes_same_client_across_nodes(api_test_env):
    db = api_test_env["session_factory"]()
    node = api_test_env["node"]
    other = Node(name="remote", host="10.0.0.9", port=9100)
    db.add(other)
    db.commit()
    db.refresh(other)
    panel_user = _create_panel_user(api_test_env["session_factory"], "dedup_user")
    db.add_all(
        [
            VpnConfig(
                node_id=node.id,
                client_name="shared-client",
                vpn_type=VpnType.openvpn,
                owner_id=panel_user.id,
            ),
            VpnConfig(
                node_id=other.id,
                client_name="shared-client",
                vpn_type=VpnType.openvpn,
                owner_id=panel_user.id,
            ),
            VpnConfig(
                node_id=other.id,
                client_name="other-wg",
                vpn_type=VpnType.wireguard,
                owner_id=panel_user.id,
            ),
        ]
    )
    db.commit()
    assert count_user_configs(db, panel_user.id) == 2
    db.close()


def test_config_create_quota_enforced(api_test_env):
    client = TestClient(api_test_env["app"])
    node = api_test_env["node"]
    mock_adapter = api_test_env["mock_adapter"]
    _set_active_node(api_test_env["session_factory"], node.id)
    _set_quota_default(api_test_env["session_factory"], "1")

    panel_user = _create_panel_user(api_test_env["session_factory"], "limited_user")
    token = create_access_token({"sub": panel_user.username, "role": panel_user.role.value})
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        "/api/configs",
        headers=headers,
        json={"client_name": "user-one", "vpn_type": "wireguard"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/configs",
        headers=headers,
        json={"client_name": "user-two", "vpn_type": "wireguard"},
    )
    assert second.status_code == 400
    assert "лимит" in second.json()["detail"].lower()


def test_traffic_overview_scoped_to_owner(api_test_env):
    client = TestClient(api_test_env["app"])
    node = api_test_env["node"]
    _set_active_node(api_test_env["session_factory"], node.id)

    db = api_test_env["session_factory"]()
    admin = db.query(User).filter(User.username == "api_admin").first()
    panel_user = _create_panel_user(api_test_env["session_factory"], "traffic_user")
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="mine-wg",
            vpn_type=VpnType.wireguard,
            owner_id=panel_user.id,
        )
    )
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="other-wg",
            vpn_type=VpnType.wireguard,
            owner_id=admin.id,
        )
    )
    db.commit()
    db.close()

    token = create_access_token({"sub": panel_user.username, "role": panel_user.role.value})
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.routers.traffic.TrafficCollectorService.get_summary",
        return_value=(
            [
                TrafficClientRow(
                    common_name="mine-wg",
                    protocol_type="wireguard",
                    total_received=100,
                    total_sent=50,
                    is_active=True,
                    total_received_vpn=100,
                    total_sent_vpn=50,
                ),
                TrafficClientRow(
                    common_name="other-wg",
                    protocol_type="wireguard",
                    total_received=900,
                    total_sent=900,
                    is_active=True,
                    total_received_vpn=900,
                    total_sent_vpn=900,
                ),
            ],
            TrafficSummary(
                users_count=2,
                active_users_count=2,
                total_received=1000,
                total_sent=950,
                total_received_vpn=1000,
                total_sent_vpn=950,
            ),
        ),
    ):
        resp = client.get("/api/traffic/overview?live=false", headers=headers)
    assert resp.status_code == 200
    names = {row["common_name"] for row in resp.json()["rows"]}
    assert names == {"mine-wg"}


def test_reminder_dedup_within_24h(api_test_env):
    db = api_test_env["session_factory"]()
    user = _create_panel_user(api_test_env["session_factory"], "reminder_user")
    assert reminder_recently_sent(db, user.id, "cert_expiry", "key-1") is False
    record_reminder_sent(db, user.id, "cert_expiry", "key-1")
    assert reminder_recently_sent(db, user.id, "cert_expiry", "key-1") is True

    from app.models import UserReminderLog

    row = db.query(UserReminderLog).filter(UserReminderLog.dedup_key == "key-1").first()
    row.sent_at = datetime.utcnow() - timedelta(seconds=REMINDER_DEDUP_SECONDS + 60)
    db.commit()
    assert reminder_recently_sent(db, user.id, "cert_expiry", "key-1") is False
    db.close()


def test_telegram_myconfigs_and_traffic_commands(api_test_env):
    from app.services.telegram_bot_handlers.base import BotContext
    from app.services.telegram_bot_handlers.configs import handle_configs
    from app.services.telegram_bot_handlers.traffic import handle_traffic

    node = api_test_env["node"]
    _set_active_node(api_test_env["session_factory"], node.id)
    panel_user = _create_panel_user(api_test_env["session_factory"], "tg_user")
    db = api_test_env["session_factory"]()
    db_user = db.query(User).filter(User.id == panel_user.id).first()
    db_user.telegram_id = "999001"
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="tg-client",
            vpn_type=VpnType.wireguard,
            owner_id=panel_user.id,
        )
    )
    db.commit()
    db.refresh(db_user)
    db.close()

    ctx_db = api_test_env["session_factory"]()
    ctx_user = ctx_db.query(User).filter(User.id == db_user.id).first()
    ctx = BotContext(
        db=ctx_db,
        bot_token="test-token",
        chat_id="999001",
        telegram_user_id="999001",
        user=ctx_user,
        mini_app_url="",
    )

    with patch("app.services.telegram_bot_handlers.configs.send_or_edit", new_callable=AsyncMock) as send:
        import asyncio

        asyncio.run(handle_configs(ctx))
        assert send.called

    with patch(
        "app.services.telegram_bot_handlers.traffic.TrafficCollectorService.get_summary",
        return_value=(
            [
                TrafficClientRow(
                    common_name="tg-client",
                    protocol_type="wireguard",
                    total_received=10,
                    total_sent=5,
                    is_active=False,
                ),
            ],
            TrafficSummary(total_received=10, total_sent=5),
        ),
    ), patch("app.services.telegram_bot_handlers.traffic.send_or_edit", new_callable=AsyncMock) as send_traffic:
        import asyncio

        asyncio.run(handle_traffic(ctx))
        assert send_traffic.called
    ctx_db.close()


def test_viewer_cannot_create_config(api_test_env):
    db = api_test_env["session_factory"]()
    viewer = db.query(User).filter(User.username == "api_viewer").first()
    db.close()
    from fastapi import HTTPException

    db = api_test_env["session_factory"]()
    try:
        try:
            enforce_user_can_create_config(db, viewer)
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 403
    finally:
        db.close()
