from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import configs as configs_router
from app.schemas import VpnConfigCreate
from app.services import awg2
from app.services.awg2 import compute_expires_at
import app.services.awg2_expire_worker as awg2_expire_worker


class _QueryStub:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _FakeDb:
    def __init__(self, *, owner=None, existing=None):
        self.owner = owner
        self.existing = existing
        self.add = MagicMock()
        self.commit = MagicMock()
        self.refresh = MagicMock()

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "User":
            return _QueryStub(self.owner)
        if name == "VpnConfig":
            return _QueryStub(self.existing)
        return _QueryStub(None)


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [
        ("15s", 15),
        ("30m", 30 * 60),
        ("2h", 2 * 60 * 60),
        ("7d", 7 * 24 * 60 * 60),
    ],
)
def test_parse_ttl_to_seconds_accepts_supported_units(raw: str, seconds: int):
    assert awg2.parse_ttl_to_seconds(raw) == seconds


@pytest.mark.parametrize("raw", ["", "15", "0h", "-1h", "2w", "abc"])
def test_parse_ttl_to_seconds_rejects_invalid_values(raw: str):
    with pytest.raises(ValueError):
        awg2.parse_ttl_to_seconds(raw)


def test_create_amneziawg2_sets_expires_at_and_passes_ttl():
    db = _FakeDb(owner=SimpleNamespace(id=1, username="owner"))
    current_user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    payload = VpnConfigCreate(client_name="awg2user", vpn_type=VpnType.amneziawg2, ttl="2h")
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": True}
    captured: dict[str, VpnConfig] = {}
    db.add.side_effect = lambda config: captured.setdefault("config", config)

    def fake_to_response(config, *_args, **_kwargs):
        return {
            "client_name": config.client_name,
            "expires_at": config.expires_at,
        }

    def fake_provision(db, *, node, client_name, vpn_type, owner, actor, notify, ttl=None, **kwargs):
        expires_at = compute_expires_at(ttl)
        if ttl:
            adapter.awg2_add_client(client_name, ttl=ttl)
        else:
            adapter.awg2_add_client(client_name)
        config = VpnConfig(
            node_id=node.id,
            client_name=client_name,
            vpn_type=vpn_type,
            owner_id=owner.id,
            expires_at=expires_at,
        )
        db.add(config)
        return config, None, None

    before = datetime.utcnow()
    with (
        patch.object(configs_router, "enforce_user_can_create_config"),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "require_vpn_type"),
        patch.object(configs_router, "enforce_can_create_vpn_type"),
        patch.object(configs_router, "validate_new_client_name"),
        patch.object(configs_router, "_active_node_id", return_value=1),
        patch.object(configs_router, "get_active_adapter", return_value=adapter),
        patch.object(configs_router, "get_active_node", return_value=SimpleNamespace(id=1, name="node-1")),
        patch.object(configs_router, "provision_config", side_effect=fake_provision),
        patch.object(configs_router, "_viewer_visibility_policy", return_value={}),
        patch.object(configs_router, "resolve_openvpn_group_for_user", return_value=None),
        patch.object(configs_router, "_local_ip_for_config", return_value=None),
        patch.object(configs_router, "_to_response", side_effect=fake_to_response),
        patch.object(configs_router, "get_feature_service", return_value=SimpleNamespace()),
    ):
        result = configs_router.create_config(
            payload,
            SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
            db,
            current_user,
        )
    after = datetime.utcnow()

    expires_at = result["expires_at"]
    assert expires_at is not None
    assert before + timedelta(hours=2) <= expires_at <= after + timedelta(hours=2)
    assert captured["config"].expires_at == expires_at
    adapter.awg2_add_client.assert_called_once_with("awg2user", ttl="2h")


@contextmanager
def _expire_test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    try:
        yield Session
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_owner(db) -> User:
    owner = User(username="owner", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner


def _seed_node(db, name: str = "node-1") -> Node:
    node = Node(
        name=name,
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _remaining_client_names(Session) -> set[str]:
    db = Session()
    try:
        return {row.client_name for row in db.query(VpnConfig).filter(VpnConfig.vpn_type == VpnType.amneziawg2).all()}
    finally:
        db.close()


def test_run_awg2_expire_once_deletes_expired_rows_only():
    with _expire_test_db() as Session:
        db = Session()
        owner = _seed_owner(db)
        node = _seed_node(db)
        now = datetime.utcnow()
        db.add_all(
            [
                VpnConfig(
                    node_id=node.id,
                    client_name="active",
                    vpn_type=VpnType.amneziawg2,
                    owner_id=owner.id,
                    expires_at=now + timedelta(hours=1),
                ),
                VpnConfig(
                    node_id=node.id,
                    client_name="expired-live",
                    vpn_type=VpnType.amneziawg2,
                    owner_id=owner.id,
                    expires_at=now - timedelta(hours=1),
                ),
                VpnConfig(
                    node_id=node.id,
                    client_name="expired-missing",
                    vpn_type=VpnType.amneziawg2,
                    owner_id=owner.id,
                    expires_at=now - timedelta(hours=2),
                ),
            ]
        )
        db.commit()
        db.close()

        adapter = MagicMock()
        adapter.awg2_expire_check.return_value = "expired"
        adapter.list_amneziawg2_clients.return_value = ["active", "expired-live"]
        adapter.awg2_expiry_map.return_value = {}

        with patch.object(awg2_expire_worker, "get_adapter_for_node", return_value=adapter):
            result = awg2_expire_worker.run_awg2_expire_once(Session)

        remaining = _remaining_client_names(Session)

    assert result["nodes_processed"] == 1
    assert result["nodes_failed"] == 0
    assert result["deleted_cli"] == 1
    assert result["deleted_db"] == 2
    adapter.awg2_expire_check.assert_called_once_with()
    adapter.awg2_delete_client.assert_called_once_with("expired-live")
    assert remaining == {"active"}


def test_run_awg2_expire_once_uses_ha_aware_delete_path():
    with _expire_test_db() as Session:
        db = Session()
        owner = _seed_owner(db)
        node = _seed_node(db)
        config = VpnConfig(
            node_id=node.id,
            client_name="expired-live",
            vpn_type=VpnType.amneziawg2,
            owner_id=owner.id,
            expires_at=datetime.utcnow() - timedelta(minutes=5),
        )
        db.add(config)
        db.commit()
        config_id = config.id
        db.close()

        adapter = MagicMock()
        adapter.list_amneziawg2_clients.return_value = ["expired-live"]
        adapter.awg2_expiry_map.return_value = {}
        sync_group = SimpleNamespace(id=7)

        with (
            patch.object(awg2_expire_worker, "get_adapter_for_node", return_value=adapter),
            patch.object(awg2_expire_worker, "find_sync_group_for_primary", return_value=sync_group) as find_group,
            patch.object(awg2_expire_worker, "enqueue_maybe_replicate_delete") as replicate_delete,
            patch.object(awg2_expire_worker, "purge_ha_shadow_configs") as purge_shadows,
        ):
            result = awg2_expire_worker.run_awg2_expire_once(Session)

        remaining = _remaining_client_names(Session)

    assert result["deleted_db"] == 1
    find_group.assert_called_once()
    assert replicate_delete.call_count == 1
    assert replicate_delete.call_args.kwargs["node_id"] == 1
    assert replicate_delete.call_args.kwargs["primary_config"].client_name == "expired-live"
    purge_shadows.assert_called_once()
    assert purge_shadows.call_args.args[1] == config_id
    assert remaining == set()
