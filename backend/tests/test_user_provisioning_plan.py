"""Stage 1 Task 4: compute_plan — pure desired-state diff for user provisioning."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.services.user_provisioning import compute_plan, user_has_plan


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


def _node(db, *, name, status=NodeStatus.online):
    node = Node(
        name=name,
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=status,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _user(
    db,
    *,
    username,
    client_base_name,
    plan_config_indexes=None,
    desired_protocols=None,
    access_until=None,
    role=UserRole.user,
):
    user = User(
        username=username,
        password_hash="x",
        role=role,
        client_base_name=client_base_name,
        plan_config_indexes=json.dumps(plan_config_indexes) if plan_config_indexes is not None else None,
        desired_protocols=json.dumps(desired_protocols) if desired_protocols is not None else None,
        access_until=access_until,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _assign(db, user, node):
    assignment = UserNodeAssignment(user_id=user.id, node_id=node.id)
    db.add(assignment)
    db.commit()
    return assignment


def _config(db, *, node, client_name, vpn_type=VpnType.wireguard, owner=None, ha_primary_config_id=None):
    config = VpnConfig(
        node_id=node.id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=owner.id if owner is not None else None,
        ha_primary_config_id=ha_primary_config_id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture()
def features_on(monkeypatch):
    class _Service:
        def is_enabled(self, key):
            return True

    monkeypatch.setattr("app.services.user_provisioning.get_feature_service", lambda: _Service())


def plan_items_by_action(plan):
    return {action: [it.client_name for it in getattr(plan, action)] for action in ("create", "delete", "conflict", "skipped")}


def test_user_has_plan_false_without_base_name(db):
    user = _user(db, username="noplan", client_base_name=None)
    assert user_has_plan(user) is False


def test_user_has_plan_true_with_base_name(db):
    user = _user(db, username="ivan", client_base_name="ivan")
    assert user_has_plan(user) is True


def test_compute_plan_creates_missing_combos(db, features_on):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1], desired_protocols=["wireguard"])
    primary = _node(db, name="Germany")
    other = _node(db, name="USA")
    _assign(db, ivan, primary)
    _assign(db, ivan, other)

    plan = compute_plan(db, ivan)
    assert plan.blocked is False
    assert len(plan.create) == 2  # one name × 2 nodes × wireguard
    assert plan.delete == []
    assert {it.node_label for it in plan.create} == {"Germany", "USA"}


def test_compute_plan_multiple_protocols_and_indexes(db, features_on):
    ivan = _user(
        db,
        username="ivan",
        client_base_name="ivan",
        plan_config_indexes=[1, 3],
        desired_protocols=["wireguard", "openvpn"],
    )
    primary = _node(db, name="Germany")
    _assign(db, ivan, primary)
    # base (index1) + openvpn already exists -> should NOT be recreated
    _config(db, node=primary, client_name="ivan", vpn_type=VpnType.openvpn, owner=ivan)

    plan = compute_plan(db, ivan)
    created = {(it.client_name, it.vpn_type) for it in plan.create}
    assert ("ivan", "wireguard") in created
    assert ("ivan-3", "wireguard") in created
    assert ("ivan-3", "openvpn") in created
    # "ivan"/openvpn already exists -> not in create
    assert ("ivan", "openvpn") not in created


def test_compute_plan_middle_index_removal_deletes_only_base_2(db, features_on):
    ivan = _user(
        db,
        username="ivan",
        client_base_name="ivan",
        plan_config_indexes=[1, 3],  # was [1,2,3] -> base-2 removed
        desired_protocols=["wireguard"],
    )
    primary = _node(db, name="Germany")
    _assign(db, ivan, primary)
    _config(db, node=primary, client_name="ivan", vpn_type=VpnType.wireguard, owner=ivan)
    _config(db, node=primary, client_name="ivan-2", vpn_type=VpnType.wireguard, owner=ivan)  # to delete
    _config(db, node=primary, client_name="ivan-3", vpn_type=VpnType.wireguard, owner=ivan)

    plan = compute_plan(db, ivan)
    deleted = {it.client_name for it in plan.delete}
    assert deleted == {"ivan-2"}
    assert plan.create == []
    assert plan.conflict == []


def test_compute_plan_conflict_other_owner(db, features_on):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1], desired_protocols=["wireguard"])
    other = _user(db, username="petr", client_base_name="petr")
    primary = _node(db, name="Germany")
    _assign(db, ivan, primary)
    # petr owns "ivan" on Germany -> conflict for ivan's desired base
    _config(db, node=primary, client_name="ivan", vpn_type=VpnType.wireguard, owner=other)

    plan = compute_plan(db, ivan)
    assert len(plan.conflict) == 1
    assert plan.conflict[0].config_id is not None
    assert "занято" in (plan.conflict[0].reason or "")
    assert plan.create == []


def test_compute_plan_blocked_when_expired(db, features_on):
    ivan = _user(
        db,
        username="ivan",
        client_base_name="ivan",
        plan_config_indexes=[1],
        desired_protocols=["wireguard"],
        access_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    primary = _node(db, name="Germany")
    _assign(db, ivan, primary)

    plan = compute_plan(db, ivan)
    assert plan.blocked is True
    assert plan.block_reason == "access_expired"
    assert plan.create == []
    assert plan.delete == []


def test_compute_plan_off_plan_configs_ignored(db, features_on):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1], desired_protocols=["wireguard"])
    primary = _node(db, name="Germany")
    _assign(db, ivan, primary)
    # unrelated name owned by ivan -> not in delete/create
    _config(db, node=primary, client_name="unrelated-alice", vpn_type=VpnType.wireguard, owner=ivan)

    plan = compute_plan(db, ivan)
    # The plan base "ivan" has no config -> one create. The off-plan "unrelated-alice"
    # is ignored -> not in delete/create/conflict.
    assert [(it.client_name, it.action) for it in plan.create] == [("ivan", "create")]
    assert plan.delete == []
    assert plan.conflict == []


def test_compute_plan_case_insensitive_match(db, features_on):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1], desired_protocols=["wireguard"])
    primary = _node(db, name="Germany")
    _assign(db, ivan, primary)
    # existing config with different case -> considered present, no create
    _config(db, node=primary, client_name="IVAN", vpn_type=VpnType.wireguard, owner=ivan)

    plan = compute_plan(db, ivan)
    assert plan.create == []
    assert plan.delete == []
    assert plan.conflict == []


def test_compute_plan_wireguard_allowed_when_amneziawg_enabled(db, monkeypatch):
    """Align with require_vpn_type: WG OK if wireguard OR amneziawg module is on."""

    class _Service:
        def is_enabled(self, key):
            return key == "amneziawg"

    monkeypatch.setattr("app.services.user_provisioning.get_feature_service", lambda: _Service())
    ivan = _user(
        db,
        username="ivan",
        client_base_name="ivan",
        plan_config_indexes=[1],
        desired_protocols=["wireguard", "openvpn", "amneziawg2"],
    )
    node = _node(db, name="Germany")
    _assign(db, ivan, node)

    plan = compute_plan(db, ivan)
    create_types = sorted(it.vpn_type for it in plan.create)
    skipped = {it.vpn_type: it.reason for it in plan.skipped}
    assert "wireguard" in create_types
    assert skipped.get("openvpn") == "protocol_disabled"
    assert skipped.get("amneziawg2") == "protocol_disabled"


def test_compute_plan_node_offline_skips(db, features_on):
    ivan = _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=[1], desired_protocols=["wireguard"])
    offline = _node(db, name="Offline", status=NodeStatus.offline)
    _assign(db, ivan, offline)

    plan = compute_plan(db, ivan)
    assert len(plan.skipped) == 1
    assert plan.skipped[0].reason == "node_offline"
    assert plan.create == []


def test_compute_plan_no_plan_returns_empty(db):
    user = _user(db, username="noplan", client_base_name=None)
    plan = compute_plan(db, user)
    assert plan.create == []
    assert plan.delete == []
    assert plan.conflict == []
    assert plan.skipped == []
    assert plan.blocked is False
