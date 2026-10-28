"""HA client create/delete/renew: no client.sh 7 on create; crypto sync is background + serialized."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnType
from app.services import config_provisioning
from app.services.node_sync import client_sync
from app.services.openvpn_profile_repair import finalize_openvpn_profiles_after_add


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def node(db):
    n = Node(
        name="primary",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def admin(db):
    u = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
        theme="dark",
        timezone="",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="",
        noc_weekly_time="",
        can_create_configs=True,
        can_manage_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class _FeatureService:
    def is_enabled(self, key: str) -> bool:
        return True


def test_finalize_after_add_never_recreates_profiles():
    adapter = MagicMock()
    with (
        patch(
            "app.services.openvpn_profile_repair.patch_openvpn_profiles_on_node",
            return_value={"patched": 0, "warnings": []},
        ) as patch_hosts,
        patch(
            "app.services.openvpn_profile_repair.validate_openvpn_profiles",
            return_value=SimpleNamespace(ready=True, issues=[]),
        ),
        patch(
            "app.services.openvpn_profile_repair.recreate_openvpn_profiles",
        ) as recreate,
    ):
        result = finalize_openvpn_profiles_after_add(
            adapter,
            client_names=["matvey"],
            hosts=["vpn.example"],
        )

    assert result.success is True
    assert result.recreated is False
    recreate.assert_not_called()
    adapter.recreate_profiles.assert_not_called()
    patch_hosts.assert_called_once()


def test_provision_openvpn_skips_recreate_and_enqueues_ha(db, node, admin, monkeypatch):
    adapter = MagicMock()
    adapter.add_openvpn_client.return_value = None
    adapter.get_profile_files.return_value = []
    monkeypatch.setattr(config_provisioning, "get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr(config_provisioning, "get_feature_service", lambda: _FeatureService())
    monkeypatch.setattr(
        config_provisioning,
        "load_node_remote_hosts",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        config_provisioning,
        "refresh_config_cert_expiry",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        config_provisioning,
        "apply_owner_access_until_to_config",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        config_provisioning,
        "replicate_inherited_access_until",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        config_provisioning,
        "find_sync_group_for_primary",
        lambda *_a, **_k: SimpleNamespace(id=42, sync_mode="auto"),
    )

    enqueue = MagicMock(return_value={"task_id": "task-ha-1", "queued": True})
    replicate_sync = MagicMock()
    monkeypatch.setattr(config_provisioning, "enqueue_maybe_replicate_create", enqueue)
    monkeypatch.setattr(client_sync, "replicate_client_create", replicate_sync)

    with patch(
        "app.services.config_provisioning.finalize_openvpn_profiles_after_add",
        wraps=finalize_openvpn_profiles_after_add,
    ) as finalize:
        config, warning, task_id = config_provisioning.provision_config(
            db,
            node=node,
            client_name="matvey",
            vpn_type=VpnType.openvpn,
            owner=admin,
            actor=admin,
            notify=False,
        )

    adapter.add_openvpn_client.assert_called_once()
    adapter.recreate_profiles.assert_not_called()
    finalize.assert_called_once()
    enqueue.assert_called_once()
    replicate_sync.assert_not_called()
    assert warning is None
    assert task_id == "task-ha-1"
    assert config.client_name == "matvey"


def test_ha_group_lock_serializes_same_group():
    order: list[str] = []
    first_holds = threading.Event()
    release_first = threading.Event()

    def first() -> None:
        with client_sync._ha_group_lock(99):
            order.append("a-enter")
            first_holds.set()
            release_first.wait(timeout=2)
            order.append("a-exit")

    def second() -> None:
        assert first_holds.wait(timeout=2)
        with client_sync._ha_group_lock(99):
            order.append("b-enter")
            order.append("b-exit")

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()
    assert first_holds.wait(timeout=1)
    time.sleep(0.05)
    release_first.set()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert order == ["a-enter", "a-exit", "b-enter", "b-exit"]


def test_enqueue_create_uses_ha_group_subject_key(monkeypatch):
    group = SimpleNamespace(id=7, sync_mode="auto")
    config = SimpleNamespace(id=11, client_name="c1")
    captured: dict = {}

    def fake_enqueue(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="bg-99")

    monkeypatch.setattr(client_sync, "find_sync_group_for_primary", lambda *_a, **_k: group)
    monkeypatch.setattr(client_sync, "is_auto_sync_enabled", lambda _g: True)
    monkeypatch.setattr(client_sync, "_enqueue_ha_client_sync", fake_enqueue)

    result = client_sync.enqueue_maybe_replicate_create(
        MagicMock(),
        node_id=1,
        primary_config=config,
        created_by_username="admin",
    )

    assert result == {"task_id": "bg-99", "queued": True}
    assert captured["group_id"] == 7
    assert captured["op"] == "create"
    assert captured["payload"]["primary_config_id"] == 11
