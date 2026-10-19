"""Stage 3 Task 10: grace-period alerts and cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, UserReminderLog, VpnConfig, VpnType
from app.services.user_grace import get_grace_months, run_grace_cleanup, scan_grace_period_alerts, set_grace_months


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


def _user(db, *, username, access_until, client_base_name="ivan"):
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        access_until=access_until,
        client_base_name=client_base_name,
        plan_config_indexes="[1]",
        desired_protocols='["wireguard"]',
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_grace_zero_never_alerts(db):
    past = datetime.now(timezone.utc) - timedelta(days=120)
    _user(db, username="old", access_until=past.replace(tzinfo=None))
    set_grace_months(db, 0)
    assert get_grace_months(db) == 0
    assert scan_grace_period_alerts(db)["alerted"] == 0


def test_grace_alert_fires_once(db, monkeypatch):
    past = datetime.now(timezone.utc) - timedelta(days=120)
    user = _user(db, username="old", access_until=past.replace(tzinfo=None))
    set_grace_months(db, 3)
    notifies: list = []
    monkeypatch.setattr(
        "app.services.user_grace.admin_notify_service",
        MagicMock(send=lambda *a, **k: notifies.append(k)),
    )
    assert scan_grace_period_alerts(db)["alerted"] == 1
    assert scan_grace_period_alerts(db)["alerted"] == 0
    assert len(notifies) == 1
    assert db.query(UserReminderLog).filter_by(user_id=user.id, reminder_type="grace_cleanup").count() == 1


def test_grace_cleanup_deletes_configs_keeps_plan(db, monkeypatch):
    admin = User(username="admin", password_hash="x", role=UserRole.admin)
    db.add(admin)
    db.commit()
    user = _user(db, username="ivan", access_until=None)
    node = Node(
        name="n1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="e",
        status=NodeStatus.online,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    cfg = VpnConfig(node_id=node.id, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=user.id)
    db.add(cfg)
    db.commit()

    monkeypatch.setattr("app.services.user_grace.deprovision_config", lambda *a, **k: None)
    result = run_grace_cleanup(db, user, actor=admin)
    assert result["deleted"] == 1
    db.refresh(user)
    assert user.client_base_name == "ivan"
    assert user.provision_state == "pending"
