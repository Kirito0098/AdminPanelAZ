"""Stage 4 Task 4: применение массовой операции к одному пользователю.

Критичные узлы: удаление трогает только in-plan конфиги, «Перенести» не убирает
старый сервер, если конфиги на новом создать не удалось, истёкший доступ меняет
присвоения без создания конфигов.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Node,
    NodeStatus,
    User,
    UserRole,
    UserNodeAssignment,
    VpnConfig,
    VpnType,
)
from app.services.bulk_user_nodes import apply_bulk_user_node


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    base,
    plan_config_indexes=(1,),
    desired_protocols=("wireguard",),
    access_until=None,
):
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        client_base_name=base,
        plan_config_indexes=json.dumps(list(plan_config_indexes)),
        desired_protocols=json.dumps(list(desired_protocols)),
        access_until=access_until,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _assign(db, user, node):
    db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
    db.commit()


def _config(db, *, node, client_name, owner, vpn_type=VpnType.wireguard):
    config = VpnConfig(
        node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=owner.id
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def assignments(db, user_id) -> set[int]:
    return {
        row.node_id
        for row in db.query(UserNodeAssignment).filter_by(user_id=user_id).all()
    }


@pytest.fixture(autouse=True)
def fake_provisioning(monkeypatch):
    """Сеть не трогаем: конфиги создаются и удаляются только в БД."""

    def fake_provision(
        session, *, node, client_name, vpn_type, owner, actor, notify=False, **kwargs
    ):
        config = VpnConfig(
            node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=owner.id
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return (config, None)

    def fake_deprovision(session, *, config, actor, notify=False, **kwargs):
        session.delete(config)
        session.commit()

    monkeypatch.setattr("app.services.bulk_user_nodes.provision_config", fake_provision)
    monkeypatch.setattr("app.services.bulk_user_nodes.deprovision_config", fake_deprovision)


@pytest.fixture()
def features_on(monkeypatch):
    class _Service:
        def is_enabled(self, key):
            return True

    monkeypatch.setattr("app.services.bulk_user_nodes.get_feature_service", lambda: _Service())


@pytest.fixture()
def actor(db):
    admin = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@pytest.fixture()
def germany(db):
    return _node(db, name="Germany")


@pytest.fixture()
def finland(db):
    return _node(db, name="Finland")


@pytest.fixture()
def poland(db):
    """Узел, на который пользователь не назначен."""
    return _node(db, name="Poland")


@pytest.fixture()
def user(db, germany, finland):
    ivan = _user(db, username="ivan", base="ivan", plan_config_indexes=(1, 2))
    _assign(db, ivan, germany)
    _assign(db, ivan, finland)
    return ivan


@pytest.fixture()
def user_one_node(db, germany):
    ivan = _user(db, username="solo", base="solo", plan_config_indexes=(1,))
    _assign(db, ivan, germany)
    return ivan


@pytest.fixture()
def expired_user(db, finland):
    return _user(
        db,
        username="old",
        base="old",
        plan_config_indexes=(1,),
        access_until=datetime.now(timezone.utc) - timedelta(days=1),
    )


@pytest.fixture()
def inplan_wg(db, germany, user):
    return _config(db, node=germany, client_name="ivan", owner=user)


@pytest.fixture()
def offplan_ovpn(db, germany, user):
    return _config(
        db, node=germany, client_name="someone-else", owner=user, vpn_type=VpnType.openvpn
    )


# --- «Убрать» -----------------------------------------------------------


def test_remove_deletes_only_in_plan_on_node(
    db, features_on, user, germany, inplan_wg, offplan_ovpn, actor
):
    result = apply_bulk_user_node(
        db, user=user, action="remove", node=germany, to_node=None, actor=actor
    )
    assert result.status == "ok"
    assert result.deleted == 1
    assert db.get(VpnConfig, inplan_wg.id) is None
    assert db.get(VpnConfig, offplan_ovpn.id) is not None
    assert germany.id not in assignments(db, user.id)


def test_remove_skips_only_server(db, features_on, user_one_node, germany, actor):
    result = apply_bulk_user_node(
        db, user=user_one_node, action="remove", node=germany, to_node=None, actor=actor
    )
    assert result.status == "skipped"
    assert result.skip_reason == "only_server"
    assert germany.id in assignments(db, user_one_node.id)


def test_remove_not_assigned_is_noop(db, features_on, user, poland, actor):
    result = apply_bulk_user_node(
        db, user=user, action="remove", node=poland, to_node=None, actor=actor
    )
    assert result.status == "noop"


def test_remove_keeps_assignment_when_delete_fails(
    db, features_on, user, germany, inplan_wg, actor, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("agent down")

    monkeypatch.setattr("app.services.bulk_user_nodes.deprovision_config", boom)
    result = apply_bulk_user_node(
        db, user=user, action="remove", node=germany, to_node=None, actor=actor
    )
    assert result.status == "failed"
    assert "agent down" in (result.error or "")
    # Присвоение остаётся: конфиг ещё жив, повторять удаление можно.
    assert germany.id in assignments(db, user.id)


# --- «Добавить» ---------------------------------------------------------


def test_add_creates_plan_configs(db, features_on, user, poland, actor, monkeypatch):
    created = []

    def fake_provision(session, *, node, client_name, vpn_type, owner, actor, notify=False, **kw):
        created.append((node.id, client_name, vpn_type))
        config = VpnConfig(
            node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=owner.id
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return (config, None)

    monkeypatch.setattr("app.services.bulk_user_nodes.provision_config", fake_provision)
    result = apply_bulk_user_node(
        db, user=user, action="add", node=poland, to_node=None, actor=actor
    )
    assert result.status == "ok"
    assert result.created == 2  # два имени плана
    assert poland.id in assignments(db, user.id)
    assert {name for _, name, _ in created} == {"ivan", "ivan-2"}


def test_add_already_assigned_is_noop(db, features_on, user, germany, actor):
    result = apply_bulk_user_node(
        db, user=user, action="add", node=germany, to_node=None, actor=actor
    )
    assert result.status == "noop"


def test_add_expired_changes_assignment_without_create(
    db, features_on, expired_user, finland, actor, monkeypatch
):
    called = []
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.provision_config",
        lambda *a, **k: called.append(1),
    )
    result = apply_bulk_user_node(
        db, user=expired_user, action="add", node=finland, to_node=None, actor=actor
    )
    assert result.status == "ok"
    assert result.created == 0
    assert called == []
    assert finland.id in assignments(db, expired_user.id)


# --- «Перенести» --------------------------------------------------------


def test_replace_keeps_old_when_new_create_fails(
    db, features_on, user, germany, finland, actor, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("agent down")

    monkeypatch.setattr("app.services.bulk_user_nodes.provision_config", boom)
    result = apply_bulk_user_node(
        db, user=user, action="replace", node=germany, to_node=finland, actor=actor
    )
    assert result.status == "failed"
    assert germany.id in assignments(db, user.id)
    assert "agent down" in (result.error or "")
    assert result.replaced is False


def test_replace_removes_old_when_new_fully_created(
    db, features_on, user, germany, finland, actor, monkeypatch
):
    from unittest.mock import MagicMock

    monkeypatch.setattr(
        "app.services.bulk_user_nodes.provision_config",
        lambda *a, **k: (MagicMock(id=1), None),
    )
    monkeypatch.setattr(
        "app.services.bulk_user_nodes.deprovision_config",
        lambda *a, **k: None,
    )
    result = apply_bulk_user_node(
        db, user=user, action="replace", node=germany, to_node=finland, actor=actor
    )
    assert result.status == "ok"
    assert result.replaced is True
    assert germany.id not in assignments(db, user.id)
    assert finland.id in assignments(db, user.id)


def test_replace_expired_user_moves_assignment(db, features_on, expired_user, germany, finland, actor):
    _assign(db, expired_user, germany)
    result = apply_bulk_user_node(
        db, user=expired_user, action="replace", node=germany, to_node=finland, actor=actor
    )
    assert result.status == "ok"
    assert result.replaced is True
    assert result.created == 0
    assert germany.id not in assignments(db, expired_user.id)
    assert finland.id in assignments(db, expired_user.id)


def test_replace_not_assigned_is_noop(db, features_on, user, poland, finland, actor):
    result = apply_bulk_user_node(
        db, user=user, action="replace", node=poland, to_node=finland, actor=actor
    )
    assert result.status == "noop"
    assert poland.id not in assignments(db, user.id)
