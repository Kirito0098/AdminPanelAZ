"""Stage 1 Task 12: HA assignment move + purge pending.

Ожидаемый FAIL до реализации Task 12, PASS после.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Node, NodeStatus, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.services.node_manager import purge_node_related
from app.services.user_provisioning import move_user_node_assignments


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def nodes(db):
    first = Node(
        name="Germany", host="127.0.0.1", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    second = Node(
        name="USA", host="127.0.0.2", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    db.add_all([first, second])
    db.commit()
    db.refresh(first)
    db.refresh(second)
    return first, second


def _user(db, username, indexes=None, plan=True):
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        client_base_name=username if plan else None,
        plan_config_indexes=json.dumps(indexes or [1]) if plan else None,
        desired_protocols=json.dumps(["wireguard"]) if plan else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _assign(db, user, node):
    db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
    db.commit()


def _assignments(db, user):
    return {
        row.node_id
        for row in db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    }


# --- 1. первичный узел сменяется — присвоения пользователей переносятся на новый primary ---

def test_primary_change_moves_assignments(db, nodes):
    ivan = _user(db, "ivan")
    petr = _user(db, "petr")
    _assign(db, ivan, nodes[0])
    _assign(db, petr, nodes[0])

    move_user_node_assignments(db, ivan.id, nodes[0].id, nodes[1].id)
    move_user_node_assignments(db, petr.id, nodes[0].id, nodes[1].id)

    assert _assignments(db, ivan) == {nodes[1].id}
    assert _assignments(db, petr) == {nodes[1].id}
    assert db.query(UserNodeAssignment).filter_by(node_id=nodes[0].id).count() == 0


# --- 2. standalone-узел становится репликой — присвоения переезжают на primary ---

def test_standalone_becomes_replica_moves_to_primary(db, nodes):
    ivan = _user(db, "ivan")
    _assign(db, ivan, nodes[1])  # standalone узел USA

    move_user_node_assignments(db, ivan.id, nodes[1].id, nodes[0].id)  # на primary Germany

    assert _assignments(db, ivan) == {nodes[0].id}


# --- 3. purge узла: удаляет UserNodeAssignment, пользователи с планом → pending ---

def test_purge_node_marks_users_pending(db, nodes):
    ivan = _user(db, "ivan", plan=True)
    petr = _user(db, "petr", plan=False)
    _assign(db, ivan, nodes[0])
    _assign(db, petr, nodes[0])

    purge_node_related(db, nodes[0].id)
    db.commit()

    assert db.query(UserNodeAssignment).filter_by(node_id=nodes[0].id).count() == 0
    ivan_row = db.query(User).filter_by(username="ivan").one()
    assert ivan_row.provision_state == "pending"
    petr_row = db.query(User).filter_by(username="petr").one()
    assert petr_row.provision_state != "pending"


# --- 4. перенос дедуплируется, если пользователь уже назначен на целевой узел ---

def test_move_dedupes_existing_assignment(db, nodes):
    ivan = _user(db, "ivan")
    _assign(db, ivan, nodes[0])
    _assign(db, ivan, nodes[1])  # уже назначен на целевой

    move_user_node_assignments(db, ivan.id, nodes[0].id, nodes[1].id)

    assert _assignments(db, ivan) == {nodes[1].id}
    assert (
        db.query(UserNodeAssignment)
        .filter_by(user_id=ivan.id, node_id=nodes[1].id)
        .count()
        == 1
    )
