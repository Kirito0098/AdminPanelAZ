"""The owner subscription deadline inherited by a new profile must reach HA replicas.

Replica policy ops look up the shadow ``VpnConfig``; it exists only after the create is replicated.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy, User, UserRole, VpnConfig, VpnType
from app.routers import configs as configs_router
from app.schemas import VpnConfigCreate
from app.services import config_csv_ops
from app.services import user_subscription as usub

_DEADLINE = datetime(2031, 3, 1, 12, 0)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db) -> Node:
    node = Node(
        name="primary",
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
    return node


def _owner(db, *, access_until: datetime | None = _DEADLINE) -> User:
    user = User(username="claymore", password_hash="x", role=UserRole.user, access_until=access_until)
    db.add(user)
    db.commit()
    return user


class _Timeline:
    """Records create replication and policy replication; policy ops fail without a shadow."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.shadow_exists = False

    def replicate_create(self, _db, *, node_id, primary_config):
        self.shadow_exists = True
        self.events.append(("create", primary_config.client_name))
        return {"successes": [{"node_id": 2}], "errors": []}

    def replicate_policy(self, _db, *, node_id, client_name, vpn_type, op, **kwargs):
        self.events.append(("policy", op, client_name, kwargs.get("access_until")))
        if not self.shadow_exists:
            return {
                "applied": [],
                "errors": [{"node_id": 2, "node_name": "replica", "error": "shadow VpnConfig not found"}],
            }
        return {"applied": [{"node_id": 2}], "errors": []}


def _create_via_route(db, node: Node, owner: User, timeline: _Timeline, **overrides):
    adapter = MagicMock()
    response = MagicMock(return_value={"ok": True})
    patches = {
        "enforce_user_can_create_config": MagicMock(),
        "require_ha_primary_for_client_ops": MagicMock(),
        "require_vpn_type": MagicMock(),
        "enforce_can_create_vpn_type": MagicMock(),
        "_active_node_id": MagicMock(return_value=node.id),
        "get_active_adapter": MagicMock(return_value=adapter),
        "recreate_openvpn_profiles_after_admin_change": MagicMock(),
        "load_node_remote_hosts": MagicMock(return_value=[]),
        "find_sync_group_for_primary": MagicMock(return_value=SimpleNamespace(id=7)),
        "maybe_replicate_create": MagicMock(side_effect=timeline.replicate_create),
        "refresh_config_cert_expiry": MagicMock(),
        "purge_traffic_history_for_reused_name": MagicMock(),
        "get_active_node": MagicMock(return_value=node),
        "get_client_timezone_from_request": MagicMock(return_value="UTC"),
        "_viewer_visibility_policy": MagicMock(return_value={}),
        "resolve_openvpn_group_for_user": MagicMock(return_value=None),
        "_local_ip_for_config": MagicMock(return_value=None),
        "_to_response": response,
        "get_feature_service": MagicMock(return_value=SimpleNamespace()),
        **overrides,
    }
    admin = SimpleNamespace(id=999, username="admin", role=UserRole.admin)
    payload = VpnConfigCreate(client_name="alina", vpn_type=VpnType.openvpn, owner_id=owner.id)
    with (
        patch.multiple(configs_router, **patches),
        patch.object(configs_router.admin_notify_service, "send_config_create"),
        patch("app.services.access_until.get_adapter_for_node", return_value=MagicMock()),
        patch("app.services.node_sync.policy_sync.maybe_replicate_policy_op", side_effect=timeline.replicate_policy),
    ):
        configs_router.create_config(payload, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, admin)
    return response.call_args.kwargs


def test_route_replicates_inherited_deadline_after_the_replica_profile_exists(db):
    node, owner = _node(db), _owner(db)
    timeline = _Timeline()

    response_kwargs = _create_via_route(db, node, owner, timeline)

    expected = _DEADLINE.replace(tzinfo=timezone.utc)
    assert timeline.events == [("create", "alina"), ("policy", "set_access_until", "alina", expected)]
    assert response_kwargs["ha_replicate_warning"] is None
    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="alina").one()
    assert row.access_until == _DEADLINE


def test_route_reports_failed_deadline_replication(db):
    node, owner = _node(db), _owner(db)
    timeline = _Timeline()
    timeline.replicate_create = lambda _db, *, node_id, primary_config: timeline.events.append(("create",)) or {
        "successes": [],
        "errors": [],
    }

    response_kwargs = _create_via_route(db, node, owner, timeline)

    assert timeline.events[0] == ("create",)
    assert "HA: 1 сбой" in response_kwargs["ha_replicate_warning"]
    assert "shadow VpnConfig not found" in response_kwargs["ha_replicate_warning"]


def test_route_warning_keeps_reconcile_and_replication_failures(db):
    node, owner = _node(db), _owner(db)
    timeline = _Timeline()
    timeline.replicate_create = lambda _db, *, node_id, primary_config: {"successes": [], "errors": []}

    with patch.object(usub, "_reconcile_access_until", side_effect=RuntimeError("agent down")):
        response_kwargs = _create_via_route(db, node, owner, timeline)

    warning = response_kwargs["ha_replicate_warning"]
    assert "reconcile: 1 сбой" in warning and "agent down" in warning
    assert "HA: 1 сбой" in warning


def test_route_without_owner_deadline_replicates_nothing(db):
    node, owner = _node(db), _owner(db, access_until=None)
    timeline = _Timeline()

    _create_via_route(db, node, owner, timeline)

    assert timeline.events == [("create", "alina")]


def test_csv_import_replicates_inherited_deadline_after_create(db):
    node, owner = _node(db), _owner(db)
    timeline = _Timeline()
    with (
        patch.object(config_csv_ops, "require_vpn_type"),
        patch.object(config_csv_ops, "get_feature_service", return_value=SimpleNamespace()),
        patch.object(config_csv_ops, "get_active_adapter", return_value=MagicMock()),
        patch.object(config_csv_ops, "refresh_config_cert_expiry"),
        patch.object(config_csv_ops, "purge_traffic_history_for_reused_name"),
        patch.object(config_csv_ops, "maybe_replicate_create", side_effect=timeline.replicate_create),
        patch("app.services.access_until.get_adapter_for_node", return_value=MagicMock()),
        patch("app.services.node_sync.policy_sync.maybe_replicate_policy_op", side_effect=timeline.replicate_policy),
    ):
        result = config_csv_ops._import_single_row(
            db,
            row={"client_name": "alina", "vpn_type": "openvpn", "_line": "2"},
            node_id=node.id,
            default_owner_id=owner.id,
            owner_by_username={},
            actor_username="admin",
        )

    assert result["ok"] is True
    expected = _DEADLINE.replace(tzinfo=timezone.utc)
    assert timeline.events == [("create", "alina"), ("policy", "set_access_until", "alina", expected)]


def test_cascade_reports_errors_returned_by_policy_replication(db):
    node, owner = _node(db), _owner(db)
    db.add(VpnConfig(node_id=node.id, client_name="alina", vpn_type=VpnType.openvpn, owner_id=owner.id))
    db.commit()
    timeline = _Timeline()

    with (
        patch("app.services.access_until.get_adapter_for_node", return_value=MagicMock()),
        patch("app.services.node_sync.policy_sync.maybe_replicate_policy_op", side_effect=timeline.replicate_policy),
    ):
        _, cascade = usub.set_user_access_until(db, owner, _DEADLINE + timedelta(days=5), actor="admin")

    assert [(e["client_name"], e["node_id"], e["error"]) for e in cascade["replicate_errors"]] == [
        ("alina", 2, "shadow VpnConfig not found")
    ]
    assert "HA: 1 сбой" in cascade["warning"]
