"""Integration tests: API actions trigger AdminNotify when configured."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_password_hash
from app.config import Settings
from app.database import Base, get_db
from app.main import app
from app.models import AppSetting, DEFAULT_TG_NOTIFY_EVENTS, Node, NodeStatus, User, UserRole


@pytest.fixture()
def notify_client(tmp_path):
    db_path = tmp_path / "integration.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="notify_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
        telegram_id="900001",
        tg_notify_events=json.dumps({**DEFAULT_TG_NOTIFY_EVENTS, "login_success": True}),
    )
    viewer = User(
        username="notify_viewer",
        password_hash=get_password_hash("secret123"),
        role=UserRole.viewer,
        is_active=True,
        telegram_id="900002",
        tg_notify_events=json.dumps({**DEFAULT_TG_NOTIFY_EVENTS, "login_success": False}),
    )
    session.add_all([admin, viewer])
    session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
    session.add(AppSetting(key="telegram_notify_enabled", value="true"))
    session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    test_settings = Settings(
        app_env="development",
        enforce_password_policy=False,
        auth_rate_limit_enabled=False,
        audit_log_enabled=False,
    )

    sent: list[tuple] = []

    def _capture_send(token, chat_id, text, **kwargs):
        sent.append((token, chat_id, text))
        return True

    mock_feature = MagicMock()
    mock_feature.is_enabled.return_value = True

    with (
        patch("app.services.admin_notify.get_settings", return_value=test_settings),
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.services.admin_notify.get_feature_service", return_value=mock_feature),
        patch("app.services.admin_notify.send_tg_message", side_effect=_capture_send),
        patch("app.services.auth_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.ip_restriction.ip_restriction_service.login_needs_captcha", return_value=False),
        patch("app.services.ip_restriction.ip_restriction_service.record_login_attempt", return_value=0),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.check", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_failure", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_success", return_value=None),
    ):
        client = TestClient(app)
        yield client, sent, session

    app.dependency_overrides.clear()
    session.close()


def test_login_triggers_admin_notify(notify_client):
    client, sent, _session = notify_client
    response = client.post(
        "/api/auth/login/json",
        json={"username": "notify_admin", "password": "secret123"},
    )
    assert response.status_code == 200
    assert response.json().get("access_token")
    assert len(sent) == 1
    assert sent[0][0] == "test-bot-token"
    assert sent[0][1] == "900001"
    assert "Вход в панель" in sent[0][2]


def test_viewer_login_skips_admin_notify(notify_client):
    client, sent, _session = notify_client
    response = client.post(
        "/api/auth/login/json",
        json={"username": "notify_viewer", "password": "secret123"},
    )
    assert response.status_code == 200
    assert sent == []


def _sign_telegram_init_data(fields: dict[str, str], bot_token: str) -> str:
    body = dict(fields)
    data_check_string = "\n".join(f"{k}={body[k]}" for k in sorted(body.keys()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    out = dict(body)
    out["hash"] = digest
    return urlencode(out)


@pytest.fixture()
def hooks_client(tmp_path):
    db_path = tmp_path / "hooks.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    events = {**DEFAULT_TG_NOTIFY_EVENTS, "user_create": True, "user_delete": True, "client_ban": True, "tg_unlinked": True}
    admin = User(
        username="hooks_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
        telegram_id="910001",
        tg_notify_events=json.dumps(events),
    )
    session.add(admin)
    node = Node(
        name="node-a",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add(node)
    session.add(AppSetting(key="telegram_bot_token", value="hooks-bot-token"))
    session.add(AppSetting(key="telegram_notify_enabled", value="true"))
    session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    test_settings = Settings(
        app_env="development",
        enforce_password_policy=False,
        auth_rate_limit_enabled=False,
        audit_log_enabled=False,
    )

    sent: list[tuple] = []

    def _capture_send(token, chat_id, text, **kwargs):
        sent.append((token, chat_id, text))
        return True

    banned_clients: set[str] = set()
    mock_adapter = MagicMock()

    def _read_config_file(name: str) -> str:
        if name == "banned_clients":
            return "\n".join(sorted(banned_clients)) + ("\n" if banned_clients else "")
        return ""

    def _write_config_file(name: str, content: str) -> None:
        if name == "banned_clients":
            banned_clients.clear()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    banned_clients.add(line)

    mock_adapter.read_config_file.side_effect = _read_config_file
    mock_adapter.write_config_file.side_effect = _write_config_file
    mock_adapter.ensure_openvpn_ban_check.return_value = None
    mock_adapter.block_wireguard_client_runtime.return_value = {"success": True}
    mock_adapter.unblock_wireguard_client_runtime.return_value = {"success": True}

    mock_feature = MagicMock()
    mock_feature.is_enabled.return_value = True

    az_path = tmp_path / "az"

    with (
        patch("app.services.admin_notify.get_settings", return_value=test_settings),
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.services.admin_notify.get_feature_service", return_value=mock_feature),
        patch("app.services.admin_notify.send_tg_message", side_effect=_capture_send),
        patch("app.services.auth_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.ip_restriction.ip_restriction_service.login_needs_captcha", return_value=False),
        patch("app.services.ip_restriction.ip_restriction_service.record_login_attempt", return_value=0),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.check", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_failure", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_success", return_value=None),
        patch("app.routers.client_access.get_active_node", return_value=node),
        patch("app.routers.client_access.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.client_access.get_node_antizapret_path", return_value=az_path),
    ):
        client = TestClient(app)
        login = client.post(
            "/api/auth/login/json",
            json={"username": "hooks_admin", "password": "secret123"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        yield client, sent, session, headers, node

    app.dependency_overrides.clear()
    session.close()


def test_user_create_triggers_admin_notify(hooks_client):
    client, sent, _session, headers, _node = hooks_client
    sent.clear()
    response = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "new_user",
            "password": "secret123",
            "role": "user",
            "theme": "dark",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    assert len(sent) == 1
    assert "Новый пользователь" in sent[0][2]
    assert "<code>new_user</code>" in sent[0][2]


def test_user_delete_triggers_admin_notify(hooks_client):
    client, sent, session, headers, _node = hooks_client
    victim = User(
        username="victim_user",
        password_hash=get_password_hash("secret123"),
        role=UserRole.user,
        is_active=True,
    )
    session.add(victim)
    session.commit()
    sent.clear()
    response = client.delete(f"/api/users/{victim.id}", headers=headers)
    assert response.status_code == 200
    assert len(sent) == 1
    assert "Удаление пользователя" in sent[0][2]
    assert "<code>victim_user</code>" in sent[0][2]


def test_wg_temp_block_triggers_admin_notify(hooks_client):
    client, sent, _session, headers, node = hooks_client
    sent.clear()
    response = client.post(
        "/api/client-access/wireguard/temp-block",
        headers=headers,
        json={"client_name": "wg-client", "days": 7},
    )
    assert response.status_code == 200
    assert len(sent) == 1
    assert "Временная блокировка" in sent[0][2]
    assert "WireGuard" in sent[0][2]
    assert f"<code>{node.name}</code>" in sent[0][2]


def test_openvpn_unblock_triggers_admin_notify(hooks_client):
    client, sent, _session, headers, _node = hooks_client
    client.post(
        "/api/client-access/openvpn/permanent-block",
        headers=headers,
        json={"client_name": "ovpn-client"},
    )
    sent.clear()
    response = client.post(
        "/api/client-access/openvpn/unblock",
        headers=headers,
        json={"client_name": "ovpn-client"},
    )
    assert response.status_code == 200
    assert len(sent) == 1
    assert "Разблокировка клиента" in sent[0][2]
    assert "OpenVPN" in sent[0][2]


def test_tg_mini_unlinked_triggers_admin_notify(hooks_client):
    client, sent, _session, _headers, _node = hooks_client
    sent.clear()
    bot_token = "123456789:AAHooksHooksHooksHooksHooksHooksHo"
    init_data = _sign_telegram_init_data(
        {
            "auth_date": str(int(time.time())),
            "query_id": "AAQhooks",
            "user": '{"id":424242,"first_name":"Ghost"}',
        },
        bot_token,
    )
    with patch("app.routers.tg_mini._get_bot_token", return_value=bot_token):
        response = client.post("/api/tg-mini/auth", json={"init_data": init_data})
    assert response.status_code == 401
    assert len(sent) == 1
    assert "TG ID не привязан" in sent[0][2]
    assert "мини-приложение" in sent[0][2]
    assert "<code>424242</code>" in sent[0][2]


def test_user_create_skips_notify_when_toggle_disabled(hooks_client):
    client, sent, session, headers, _node = hooks_client
    admin = session.query(User).filter(User.username == "hooks_admin").first()
    events = admin.merged_tg_notify_events()
    events["user_create"] = False
    admin.tg_notify_events = json.dumps(events)
    session.commit()
    sent.clear()
    response = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "quiet_user",
            "password": "secret123",
            "role": "user",
            "theme": "dark",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    assert sent == []
