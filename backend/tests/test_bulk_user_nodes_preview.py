"""Stage 4 Task 1–2: область выбора и предпросмотр массовых операций с серверами.

TDD: предпросмотр не делает сетевых вызовов — только считает, что изменится.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Node,
    NodeStatus,
    NodeSyncGroup,
    User,
    UserRole,
    UserNodeAssignment,
    VpnConfig,
    VpnType,
)
from app.services.bulk_user_nodes import (
    BulkNodesScope,
    assert_assignable_vpn_node,
    build_bulk_nodes_preview,
    resolve_bulk_scope,
)


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


@pytest.fixture(autouse=True)
def _patch_sessions(monkeypatch, db):
    """Фоновые задачи и предпросмотр не должны ходить в боевую БД панели."""
    TestSessionLocal = sessionmaker(bind=db.bind)
    monkeypatch.setattr("app.services.background_tasks.SessionLocal", lambda: TestSessionLocal())
    monkeypatch.setattr("app.services.bulk_user_nodes.SessionLocal", lambda: TestSessionLocal())


@pytest.fixture(autouse=True)
def _features_on(monkeypatch):
    class _Service:
        def is_enabled(self, key):
            return True

    monkeypatch.setattr("app.services.bulk_user_nodes.get_feature_service", lambda: _Service())


def _node(db, *, name, status=NodeStatus.online, node_kind="vpn"):
    node = Node(
        name=name,
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=status,
        is_local=True,
        node_kind=node_kind,
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
    client_base_name=None,
    plan_config_indexes=(1,),
    role=UserRole.user,
    access_until=None,
    telegram_id=None,
):
    user = User(
        username=username,
        password_hash="x",
        role=role,
        client_base_name=client_base_name,
        plan_config_indexes=json.dumps(list(plan_config_indexes)),
        desired_protocols=json.dumps(["wireguard"]),
        access_until=access_until,
        telegram_id=telegram_id,
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


def count_in_plan_on_node(db, user, node_id) -> int:
    """Сколько конфигов пользователя на узле входит в план."""
    from app.services.user_provisioning import is_in_plan_config

    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.node_id == node_id)
        .all()
    )
    return sum(1 for config in configs if is_in_plan_config(db, user, config))


@pytest.fixture()
def germany(db):
    return _node(db, name="Germany")


@pytest.fixture()
def finland(db):
    return _node(db, name="Finland")


@pytest.fixture()
def germany_offline(db):
    return _node(db, name="Germany", status=NodeStatus.offline)


@pytest.fixture()
def proxy_node(db):
    return _node(db, name="Proxy", node_kind="proxy")


@pytest.fixture()
def ha_replica_node(db):
    primary = _node(db, name="HA-Primary")
    replica = _node(db, name="HA-Replica")
    group = NodeSyncGroup(
        name="HA",
        shared_domain="ha.example.com",
        primary_node_id=primary.id,
        replica_node_ids=json.dumps([replica.id]),
        sync_mode="manual_full",
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return replica


@pytest.fixture()
def user_with_plan(db):
    return _user(db, username="ivan", client_base_name="ivan", plan_config_indexes=(1,))


@pytest.fixture()
def another_planned_user(db):
    return _user(db, username="petr", client_base_name="petr", plan_config_indexes=(1,))


@pytest.fixture()
def unmanaged_user(db):
    return _user(db, username="guest", client_base_name=None)


@pytest.fixture()
def user_only_on_germany(db, germany):
    user = _user(db, username="solo", client_base_name="solo", plan_config_indexes=(1,))
    _assign(db, user, germany)
    return user


@pytest.fixture()
def user_two_nodes(db, germany, finland):
    user = _user(db, username="two", client_base_name="two", plan_config_indexes=(1, 2))
    _assign(db, user, germany)
    _assign(db, user, finland)
    return user


# --- Task 1: назначаемый сервер и область выбора -------------------------


def test_assert_assignable_rejects_proxy(db, proxy_node):
    with pytest.raises(HTTPException) as exc:
        assert_assignable_vpn_node(db, proxy_node.id)
    assert exc.value.status_code == 400
    detail = str(exc.value.detail).lower()
    assert "proxy" in detail or "прокси" in detail


def test_assert_assignable_rejects_replica(db, ha_replica_node):
    with pytest.raises(HTTPException) as exc:
        assert_assignable_vpn_node(db, ha_replica_node.id)
    assert exc.value.status_code == 400
    assert "реплик" in str(exc.value.detail).lower()


def test_assert_assignable_allows_ha_primary(db, ha_replica_node):
    primary = db.query(Node).filter(Node.name == "HA-Primary").one()
    assert assert_assignable_vpn_node(db, primary.id).id == primary.id


def test_assert_assignable_unknown_node_404(db):
    with pytest.raises(HTTPException) as exc:
        assert_assignable_vpn_node(db, 4242)
    assert exc.value.status_code == 404


def test_resolve_scope_all_only_users_with_plan(db, user_with_plan, unmanaged_user):
    users = resolve_bulk_scope(db, BulkNodesScope(mode="all"))
    ids = {u.id for u in users}
    assert user_with_plan.id in ids
    assert unmanaged_user.id not in ids


def test_resolve_scope_user_ids(db, user_with_plan, another_planned_user):
    users = resolve_bulk_scope(
        db, BulkNodesScope(mode="user_ids", user_ids=[user_with_plan.id])
    )
    assert [u.id for u in users] == [user_with_plan.id]


def test_resolve_scope_skips_admin_and_pending_deletion(db, user_with_plan):
    admin = _user(db, username="boss", client_base_name="boss", role=UserRole.admin)
    pending = _user(db, username="soon", client_base_name="soon")
    pending.provision_state = "pending_deletion"
    db.commit()

    ids = {u.id for u in resolve_bulk_scope(db, BulkNodesScope(mode="all"))}
    assert admin.id not in ids
    assert pending.id not in ids
    assert user_with_plan.id in ids


def test_resolve_scope_filter_by_state(db, user_with_plan, another_planned_user):
    user_with_plan.provision_state = "partial"
    db.commit()
    users = resolve_bulk_scope(db, BulkNodesScope(mode="filter", state="partial"))
    assert [u.id for u in users] == [user_with_plan.id]


# --- Task 2: предпросмотр ------------------------------------------------


def test_preview_remove_skips_only_server(db, user_only_on_germany, germany):
    prev = build_bulk_nodes_preview(
        db,
        action="remove",
        node_id=germany.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_only_on_germany.id]),
    )
    assert prev.affected == []
    assert any(
        u["user_id"] == user_only_on_germany.id for u in prev.skipped["only_server"]
    )


def test_preview_remove_counts_in_plan_deletes_only(
    db, user_two_nodes, germany, finland
):
    _config(db, node=germany, client_name="two", owner=user_two_nodes)
    _config(db, node=germany, client_name="off-plan", owner=user_two_nodes)
    prev = build_bulk_nodes_preview(
        db,
        action="remove",
        node_id=germany.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_two_nodes.id]),
    )
    assert prev.configs_to_delete == count_in_plan_on_node(db, user_two_nodes, germany.id)
    assert prev.configs_to_delete == 1  # off-plan конфиг не считается
    assert all(
        item.get("configs_delete", 0) == count_in_plan_on_node(db, user_two_nodes, germany.id)
        for item in prev.affected
    )


def test_preview_skips_busy_user_provision(db, user_with_plan, finland, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.services.bulk_user_nodes.background_task_service.find_active_task",
        lambda task_type, subject_key=None: (
            SimpleNamespace(id="t1")
            if task_type == "user_provision" and subject_key == f"user:{user_with_plan.id}"
            else None
        ),
    )
    prev = build_bulk_nodes_preview(
        db,
        action="add",
        node_id=finland.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_with_plan.id]),
    )
    assert any(u["user_id"] == user_with_plan.id for u in prev.skipped["busy_provision"])


def test_preview_offline_old_node_raises(db, user_two_nodes, germany_offline):
    with pytest.raises(HTTPException) as exc:
        build_bulk_nodes_preview(
            db,
            action="remove",
            node_id=germany_offline.id,
            to_node_id=None,
            scope=BulkNodesScope(mode="user_ids", user_ids=[user_two_nodes.id]),
        )
    assert exc.value.status_code == 400
    assert "недоступен" in str(exc.value.detail).lower()


def test_preview_replace_requires_to_node(db, finland):
    with pytest.raises(HTTPException):
        build_bulk_nodes_preview(
            db,
            action="replace",
            node_id=finland.id,
            to_node_id=None,
            scope=BulkNodesScope(mode="all"),
        )


def test_preview_replace_rejects_same_node(db, finland):
    with pytest.raises(HTTPException) as exc:
        build_bulk_nodes_preview(
            db,
            action="replace",
            node_id=finland.id,
            to_node_id=finland.id,
            scope=BulkNodesScope(mode="all"),
        )
    assert exc.value.status_code == 400


def test_preview_add_counts_creates_and_skips_assigned(db, user_with_plan, finland):
    _assign(db, user_with_plan, finland)
    prev = build_bulk_nodes_preview(
        db,
        action="add",
        node_id=finland.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_with_plan.id]),
    )
    assert prev.affected == []
    assert any(u["user_id"] == user_with_plan.id for u in prev.skipped["already_assigned"])


def test_preview_add_creates_for_planned_user(db, user_with_plan, finland):
    prev = build_bulk_nodes_preview(
        db,
        action="add",
        node_id=finland.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_with_plan.id]),
    )
    assert len(prev.affected) == 1
    assert prev.affected[0]["configs_create"] == 1
    assert prev.configs_to_create == 1
    assert prev.configs_to_delete == 0


def test_preview_remove_skips_not_assigned(db, user_with_plan, germany):
    prev = build_bulk_nodes_preview(
        db,
        action="remove",
        node_id=germany.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_with_plan.id]),
    )
    assert prev.affected == []
    assert any(u["user_id"] == user_with_plan.id for u in prev.skipped["not_assigned"])


def test_preview_expired_user_is_affected_without_creates(db, germany, finland):
    expired = _user(
        db,
        username="old",
        client_base_name="old",
        plan_config_indexes=(1,),
        access_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    prev = build_bulk_nodes_preview(
        db,
        action="add",
        node_id=finland.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[expired.id]),
    )
    assert len(prev.affected) == 1
    assert prev.affected[0]["configs_create"] == 0
    assert prev.affected[0]["expired"] is True
    # Истёкший доступ — примечание, а не пропуск.
    assert prev.affected[0]["detail"] == "expired_no_create"
    assert "expired_no_create" not in prev.skipped


def test_preview_lists_users_without_telegram(db, germany, finland):
    without = _user(db, username="notg", client_base_name="notg", plan_config_indexes=(1,))
    prev = build_bulk_nodes_preview(
        db,
        action="add",
        node_id=finland.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="all"),
    )
    assert any(u["user_id"] == without.id for u in prev.without_telegram)


def test_preview_renders_notify_text(db, user_with_plan, finland):
    prev = build_bulk_nodes_preview(
        db,
        action="add",
        node_id=finland.id,
        to_node_id=None,
        scope=BulkNodesScope(mode="user_ids", user_ids=[user_with_plan.id]),
        notify_telegram=True,
        note="Обновите приложение",
    )
    assert prev.notify_text_preview is not None
    assert "Finland" in prev.notify_text_preview
    assert "Обновите приложение" in prev.notify_text_preview
