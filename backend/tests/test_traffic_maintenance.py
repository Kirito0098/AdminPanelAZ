"""Tests for traffic maintenance parity (phase 33)."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, UserTrafficSample, UserTrafficStatProtocol, VpnConfig, VpnType
from app.auth import get_password_hash
from app.services.traffic.maintenance import (
    TrafficMaintenanceService,
    cleanup_openvpn_status_logs_now,
    normalize_traffic_protocol_scope,
)


@pytest.fixture()
def maintenance_db(tmp_path):
    db_path = tmp_path / "traffic_maint.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True, status=NodeStatus.online)
    admin = User(
        username="admin",
        password_hash=get_password_hash("secret"),
        role=UserRole.admin,
        is_active=True,
    )
    db.add_all([node, admin])
    db.commit()
    db.refresh(node)
    db.refresh(admin)
    yield db, node, admin
    db.close()


def test_normalize_traffic_protocol_scope():
    assert normalize_traffic_protocol_scope("openvpn") == "openvpn"
    assert normalize_traffic_protocol_scope("invalid") == "all"


def test_never_connected_clients_lists_configs_without_traffic(maintenance_db):
    db, node, admin = maintenance_db
    db.add_all([
        VpnConfig(
            node_id=node.id,
            client_name="alice",
            vpn_type=VpnType.openvpn,
            owner_id=admin.id,
        ),
        VpnConfig(
            node_id=node.id,
            client_name="alice",
            vpn_type=VpnType.wireguard,
            owner_id=admin.id,
        ),
        VpnConfig(
            node_id=node.id,
            client_name="bob",
            vpn_type=VpnType.openvpn,
            owner_id=admin.id,
        ),
        UserTrafficStatProtocol(
            node_id=node.id,
            common_name="alice",
            protocol_type="openvpn",
            total_received=100,
            total_sent=50,
        ),
    ])
    db.commit()

    service = TrafficMaintenanceService(db, node.id)
    rows, summary = service.get_never_connected_config_rows()
    names = {(row["common_name"], row["protocol_type"]) for row in rows}
    assert summary["rows_count"] == 2
    assert summary["users_count"] == 2
    assert ("alice", "wireguard") in names
    assert ("bob", "openvpn") in names
    assert ("alice", "openvpn") not in names


def test_deleted_clients_excludes_active_configs(maintenance_db):
    db, node, admin = maintenance_db
    db.add(
        VpnConfig(
            node_id=node.id,
            client_name="alice",
            vpn_type=VpnType.openvpn,
            owner_id=admin.id,
        )
    )
    db.add(
        UserTrafficStatProtocol(
            node_id=node.id,
            common_name="alice",
            protocol_type="openvpn",
            total_received=100,
            total_sent=50,
        )
    )
    db.add(
        UserTrafficStatProtocol(
            node_id=node.id,
            common_name="ghost",
            protocol_type="openvpn",
            total_received=200,
            total_sent=100,
        )
    )
    db.commit()

    service = TrafficMaintenanceService(db, node.id)
    rows, summary = service.get_deleted_persisted_traffic_rows()
    assert summary["users_count"] == 1
    assert rows[0]["common_name"] == "ghost"


def test_delete_client_traffic_stats(maintenance_db):
    db, node, _admin = maintenance_db
    db.add(
        UserTrafficStatProtocol(
            node_id=node.id,
            common_name="orphan",
            protocol_type="wireguard",
            total_received=10,
            total_sent=5,
        )
    )
    db.add(
        UserTrafficSample(
            node_id=node.id,
            common_name="orphan",
            network_type="vpn",
            protocol_type="wireguard",
            delta_received=10,
            delta_sent=5,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    service = TrafficMaintenanceService(db, node.id)
    ok, message = service.delete_client_traffic_stats("orphan")
    assert ok is True
    assert "orphan" in message
    remaining = db.query(UserTrafficStatProtocol).filter_by(node_id=node.id, common_name="orphan").count()
    assert remaining == 0


def test_cleanup_openvpn_status_logs_now_missing_dir(tmp_path):
    missing = str(tmp_path / "no-logs")
    ok, message = cleanup_openvpn_status_logs_now(missing)
    assert ok is True
    assert "0" in message
