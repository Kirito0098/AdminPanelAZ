"""Очистка статистики при переиспользовании имени идёт порциями, не одним DELETE."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Node,
    NodeStatus,
    TrafficSessionState,
    UserTrafficSample,
    UserTrafficStatProtocol,
)
from app.services.traffic import maintenance


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_purge_deletes_all_rows_across_chunks(monkeypatch):
    db = _session()
    node = Node(
        name="n", host="127.0.0.1", port=9100, api_key_hash="", api_key_encrypted="",
        status=NodeStatus.online, is_local=True, node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    monkeypatch.setattr(maintenance, "_PURGE_CHUNK_ROWS", 2)
    now = datetime.utcnow()
    for _ in range(5):
        db.add(UserTrafficSample(node_id=node.id, common_name="Reused_Name", created_at=now))
        db.add(UserTrafficSample(node_id=node.id, common_name="other", created_at=now))
    db.add(TrafficSessionState(node_id=node.id, session_key="s1", common_name="reused_name"))
    db.add(UserTrafficStatProtocol(node_id=node.id, common_name="reused_name"))

    deleted = maintenance.purge_traffic_history_for_reused_name(
        db, node_id=node.id, client_name="reused_name"
    )

    assert deleted == 7  # 5 сэмплов + сессия + статистика протокола
    assert db.query(UserTrafficSample).filter_by(node_id=node.id).count() == 5
    assert db.query(TrafficSessionState).filter_by(node_id=node.id).count() == 0
    assert db.query(UserTrafficStatProtocol).filter_by(node_id=node.id).count() == 0
    db.close()


def test_purge_skips_name_still_used_by_another_config(monkeypatch):
    from app.models import User, UserRole, VpnConfig, VpnType

    db = _session()
    node = Node(
        name="n", host="127.0.0.1", port=9100, api_key_hash="", api_key_encrypted="",
        status=NodeStatus.online, is_local=True, node_metadata="{}",
    )
    owner = User(
        username="owner", password_hash="x", role=UserRole.user, is_active=True, theme="dark",
        timezone="", last_client_timezone="", noc_daily_time="", noc_weekly_dow="",
        noc_weekly_time="", can_create_configs=True, can_manage_configs=True,
        panel_login_enabled=True, provision_state="unmanaged",
    )
    db.add_all([node, owner])
    db.commit()
    db.refresh(node)
    db.refresh(owner)
    db.add(VpnConfig(node_id=node.id, client_name="Reused_Name", vpn_type=VpnType.openvpn, owner_id=owner.id))
    db.add(UserTrafficSample(node_id=node.id, common_name="Reused_Name", created_at=datetime.utcnow()))
    db.commit()

    deleted = maintenance.purge_traffic_history_for_reused_name(
        db, node_id=node.id, client_name="reused_name"
    )

    assert deleted == 0
    assert db.query(UserTrafficSample).filter_by(node_id=node.id).count() == 1
    db.close()
