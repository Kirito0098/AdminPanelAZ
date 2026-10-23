"""ACL privacy: grants, enumeration 404, node scrub, settings redaction, owner PII."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models import UserRole, VpnType
from app.routers import client_portal as portal_router
from app.routers import configs as configs_router
from app.routers import nodes as nodes_router
from app.routers import settings as settings_router
from app.routers.tg_mini import configs as mini_configs
from app.routers.tg_mini import helpers as mini_helpers
from app.routers.tg_mini import settings as mini_settings
from app.schemas import VpnConfigResponse
from app.services.config_access import (
    _grant_matches,
    matches_user_config_grant,
    migrate_grants_to_explicit_prefix,
)


class _FakeGrantQuery:
    def __init__(self, grants: list[str]):
        self._grants = grants

    def filter_by(self, **_kwargs):
        return self

    def all(self):
        return [SimpleNamespace(config_group=g) for g in self._grants]


class _FakeDb:
    def __init__(self, grants: list[str] | None = None):
        self.grants = grants or []

    def query(self, *models):
        model = models[0] if models else None
        name = getattr(model, "__name__", str(model))
        if "UserConfigAccess" in name or name.endswith("UserConfigAccess"):
            return _FakeGrantQuery(self.grants)
        return _FakeGrantQuery([])


# --- C3 grants ---


def test_grant_ivan_does_not_match_ivanov():
    assert _grant_matches("ivanov", "ivan") is False
    assert matches_user_config_grant(_FakeDb(["ivan"]), 1, "ivanov") is False


def test_grant_ivan_matches_exact_and_base_n():
    assert _grant_matches("ivan", "ivan") is True
    assert _grant_matches("ivan-2", "ivan") is True
    assert _grant_matches("ivan-20", "ivan") is True
    assert _grant_matches("ivan-1", "ivan") is False
    assert _grant_matches("ivan-21", "ivan") is False


def test_grant_explicit_star_is_prefix():
    assert _grant_matches("ivanov", "ivan*") is True
    assert _grant_matches("ivan-2", "ivan*") is True
    assert _grant_matches("petr", "ivan*") is False
    assert _grant_matches("ivan", "*") is False


def test_migrate_grants_appends_star_once(monkeypatch):
    rows = [SimpleNamespace(config_group="ivan"), SimpleNamespace(config_group="fam*")]
    setting = {"config_access_explicit_prefix": ""}

    class _Q:
        def all(self):
            return rows

    class _Db:
        def query(self, *_a):
            return _Q()

        def commit(self):
            return None

    monkeypatch.setattr(
        "app.services.app_setting_store._get_setting",
        lambda _db, key, default="": setting.get(key, default),
    )
    monkeypatch.setattr(
        "app.services.app_setting_store._set_setting",
        lambda _db, key, value: setting.__setitem__(key, value),
    )

    assert migrate_grants_to_explicit_prefix(_Db()) == 1
    assert rows[0].config_group == "ivan*"
    assert rows[1].config_group == "fam*"
    assert setting["config_access_explicit_prefix"] == "1"
    assert migrate_grants_to_explicit_prefix(_Db()) == 0


# --- C1 / C2 nodes ---


def test_active_node_response_scrubs_host_for_user(monkeypatch):
    node = SimpleNamespace(
        id=1,
        name="n1",
        host="203.0.113.10",
        port=9100,
        status="online",
        is_local=True,
        transport="https",
        mtls_enabled=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_seen_at=None,
        version=None,
        node_kind="vpn",
        agent_version=None,
        ssh_host="203.0.113.10",
        ssh_port=22,
        ssh_username="root",
        ssh_private_key_encrypted="x",
        ssh_remote_agent_host="127.0.0.1",
        ssh_remote_agent_port=9100,
        destination_ip="203.0.113.10",
        node_metadata="{}",
        panel_url=None,
        linked_vpn_node_id=None,
        portal_label=None,
    )
    monkeypatch.setattr(nodes_router, "build_ha_node_context", lambda *_a, **_k: None)
    user = SimpleNamespace(role=UserRole.user)
    resp = nodes_router._active_node_response(MagicMock(), node, user)
    assert resp.node.host == "hidden"
    assert resp.node.port == 1
    assert resp.node.ssh_host is None
    assert resp.node.destination_ip is None


# --- C4 enumeration ---


_NOT_FOUND = "Конфигурация не найдена"


def test_get_config_foreign_and_missing_same_404(monkeypatch):
    foreign = SimpleNamespace(id=9, owner_id=99, client_name="secret", vpn_type=VpnType.wireguard)
    user = SimpleNamespace(id=2, role=UserRole.user)
    monkeypatch.setattr(configs_router, "_get_config_for_active_node", lambda *_a: foreign)
    monkeypatch.setattr(configs_router, "_can_access_config", lambda *_a: False)

    with pytest.raises(HTTPException) as foreign_exc:
        configs_router.get_config(9, True, MagicMock(), user)
    monkeypatch.setattr(configs_router, "_get_config_for_active_node", lambda *_a: None)
    with pytest.raises(HTTPException) as missing_exc:
        configs_router.get_config(9, True, MagicMock(), user)

    assert foreign_exc.value.status_code == 404
    assert missing_exc.value.status_code == 404
    assert foreign_exc.value.detail == missing_exc.value.detail == _NOT_FOUND


def test_update_delete_foreign_config_is_404_not_403(monkeypatch):
    foreign = SimpleNamespace(id=9, owner_id=99, client_name="secret", vpn_type=VpnType.wireguard)
    user = SimpleNamespace(id=2, role=UserRole.user, can_manage_configs=True, username="u")
    monkeypatch.setattr(configs_router, "_get_config_for_active_node", lambda *_a: foreign)
    monkeypatch.setattr(configs_router, "_can_access_config", lambda *_a: False)

    with pytest.raises(HTTPException) as upd:
        configs_router.update_config(9, MagicMock(), MagicMock(), user)
    with pytest.raises(HTTPException) as dele:
        configs_router.delete_config(9, MagicMock(), MagicMock(), user)

    assert upd.value.status_code == 404
    assert dele.value.status_code == 404
    assert upd.value.detail == dele.value.detail == _NOT_FOUND


def test_mini_helper_foreign_config_is_404(monkeypatch):
    foreign = SimpleNamespace(id=9, owner_id=99, client_name="secret")
    user = SimpleNamespace(id=2, role=UserRole.user)
    monkeypatch.setattr(
        mini_helpers,
        "get_active_node",
        lambda _db: SimpleNamespace(id=1),
        raising=False,
    )
    # Patch inside the function's import path
    import app.services.node_manager as nm

    monkeypatch.setattr(nm, "get_active_node", lambda _db: SimpleNamespace(id=1))

    class _CfgQ:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return foreign

    monkeypatch.setattr(MagicMock(), "query", lambda *_a: _CfgQ())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = foreign
    monkeypatch.setattr(
        "app.services.config_access.can_view_config",
        lambda *_a: False,
    )

    with pytest.raises(HTTPException) as exc:
        mini_helpers._get_accessible_config(db, 9, user)
    assert exc.value.status_code == 404
    assert exc.value.detail == _NOT_FOUND


def test_portal_foreign_client_is_404(monkeypatch):
    configs = [SimpleNamespace(owner_id=1, client_name="alice")]
    monkeypatch.setattr(portal_router, "_configs_for_client", lambda *_a: configs)

    with pytest.raises(HTTPException) as exc:
        portal_router._assert_can_manage_client(
            SimpleNamespace(id=2, role=UserRole.user), MagicMock(), "alice"
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Клиент не найден"


# --- C5 / C6 settings redaction ---


def test_get_settings_hides_antizapret_path_for_user(monkeypatch):
    monkeypatch.setattr(
        settings_router,
        "get_active_adapter",
        lambda _db: SimpleNamespace(read_file=lambda *_a, **_k: ""),
    )
    monkeypatch.setattr(
        settings_router,
        "_read_config_files_parallel",
        lambda *_a, **_k: {
            "include-hosts.txt": "h",
            "exclude-hosts.txt": "h",
            "include-ips.txt": "h",
            "exclude-ips.txt": "h",
            "allow-ips.txt": "h",
        },
    )
    monkeypatch.setattr(
        settings_router,
        "get_active_node",
        lambda _db: SimpleNamespace(id=1, name="local"),
    )
    monkeypatch.setattr(
        settings_router,
        "get_node_antizapret_path",
        lambda _db: "/secret/antizapret",
    )
    user = SimpleNamespace(
        role=SimpleNamespace(value="user"),
        theme="dark",
        timezone="",
        noc_daily_time="",
        noc_weekly_dow="",
        noc_weekly_time="",
    )
    resp = settings_router.get_settings(user, MagicMock())
    assert resp.antizapret_path == ""
    assert resp.include_hosts == ""


def test_mini_notify_hides_admin_fields_for_user(monkeypatch):
    full = SimpleNamespace(
        telegram_id="1",
        recipient_user_ids=[1, 2],
        notify_enabled=True,
        bot_token_set=True,
        events=[],
        groups=[],
        node_offline_grace_seconds=999,
    )
    monkeypatch.setattr(mini_settings, "_admin_notify_settings_response", lambda *_a: full)
    user = SimpleNamespace(
        id=5,
        role=UserRole.user,
        merged_tg_notify_events=lambda: {},
    )
    resp = mini_settings._mini_notify_settings_response(MagicMock(), user)
    assert resp.bot_token_set is False
    assert resp.notify_enabled is False
    assert resp.node_offline_grace_seconds == 0
    assert resp.recipient_user_ids == []


# --- C7 owner PII ---


def test_to_response_hides_owner_username_from_grantee(monkeypatch):
    owner = SimpleNamespace(id=1, username="alice")
    viewer = SimpleNamespace(id=2, role=UserRole.user)
    config = SimpleNamespace(
        id=10,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=1,
        cert_expire_days=None,
        cert_expires_at=None,
        expires_at=None,
        description=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        sync_group_id=None,
    )

    class _UQ:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return owner

    db = MagicMock()
    db.query.return_value = _UQ()
    monkeypatch.setattr(configs_router, "_ha_info_for_config", lambda *_a: None)

    resp = configs_router._to_response(config, db, viewer=viewer)
    assert isinstance(resp, VpnConfigResponse)
    assert resp.owner_username is None
    assert resp.owner_id is None

    owner_viewer = SimpleNamespace(id=1, role=UserRole.user)
    own = configs_router._to_response(config, db, viewer=owner_viewer)
    assert own.owner_username == "alice"
    assert own.owner_id == 1


def test_mini_configs_hide_owner_pii_for_grantee(monkeypatch):
    owner = SimpleNamespace(id=1, username="alice", telegram_id="999")
    other = SimpleNamespace(
        id=10,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=1,
        owner=owner,
    )
    mine = SimpleNamespace(
        id=11,
        client_name="bob",
        vpn_type=VpnType.wireguard,
        owner_id=2,
        owner=SimpleNamespace(id=2, username="bob", telegram_id="111"),
    )
    viewer = SimpleNamespace(id=2, role=UserRole.user)
    monkeypatch.setattr(mini_configs, "get_active_node", lambda _db: SimpleNamespace(id=1))
    monkeypatch.setattr(
        "app.services.config_access.list_accessible_configs",
        lambda *_a: [other, mine],
    )
    monkeypatch.setattr(
        mini_configs,
        "resolve_effective_visible_vpn_profiles",
        lambda *_a: {},
    )
    monkeypatch.setattr(mini_configs, "can_create_vpn_type", lambda *_a: True)

    db = MagicMock()
    db.query.return_value.filter.return_value.options.return_value = MagicMock()
    payload = mini_configs.mini_configs(viewer, db)
    by_id = {c["id"]: c for c in payload["configs"]}
    assert by_id[10]["owner_username"] is None
    assert by_id[10]["owner_telegram_linked"] is False
    assert by_id[11]["owner_username"] == "bob"
    assert by_id[11]["owner_telegram_linked"] is True
