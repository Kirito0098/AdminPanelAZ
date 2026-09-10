from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus, OpenVpnAccessPolicy, WgAccessPolicy
from app.routers import client_access
from app.services.access_until import (
    apply_due_access_blocks,
    effective_access_until_for_client,
    get_access_until,
    set_access_until,
)


def _make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session


def _make_node(db):
    node = Node(
        name="node-1",
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


def _adapter():
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.write_config_file.return_value = None
    adapter.ensure_openvpn_ban_check.return_value = None
    adapter.block_wireguard_client_runtime.return_value = {"success": True}
    adapter.unblock_wireguard_client_runtime.return_value = {"success": True}
    adapter.block_awg2_client_runtime.return_value = {"success": True}
    adapter.unblock_awg2_client_runtime.return_value = {"success": True}
    return adapter


def test_set_access_until_openvpn_and_effective_min():
    engine, db = _make_db()
    try:
        node = _make_node(db)
        now = datetime.now(timezone.utc)
        openvpn_until = now + timedelta(days=10)
        wg_until = now + timedelta(days=3)
        awg2_until = now + timedelta(days=7)
        with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
            openvpn_state = set_access_until(db, "openvpn", node.id, "Alice", openvpn_until, actor="admin")
            set_access_until(db, "wireguard", node.id, "Alice", wg_until, actor="admin")
            set_access_until(db, "amneziawg2", node.id, "Alice", awg2_until, actor="admin")

        assert openvpn_state["access_until"] == openvpn_until.isoformat()
        assert get_access_until(db, "openvpn", node.id, "Alice") == openvpn_until
        assert effective_access_until_for_client(db, node.id, "Alice") == wg_until
    finally:
        db.close()
        engine.dispose()


def test_apply_due_access_blocks_sets_access_expired():
    engine, db = _make_db()
    try:
        node = _make_node(db)
        now = datetime.now(timezone.utc)
        adapter = _adapter()
        with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
            db.add(
                OpenVpnAccessPolicy(
                    node_id=node.id,
                    client_name="ovpn",
                    access_until=now - timedelta(minutes=5),
                )
            )
            db.add(
                WgAccessPolicy(
                    node_id=node.id,
                    client_name="wg",
                    expires_at=now - timedelta(minutes=5),
                )
            )
            db.add(
                AmneziaWg2AccessPolicy(
                    node_id=node.id,
                    client_name="awg2",
                    access_until=now - timedelta(minutes=5),
                )
            )
            db.commit()

            counts = apply_due_access_blocks(db)

        assert counts["blocked"] == 3
        assert counts["openvpn"] == 1
        assert counts["wireguard"] == 1
        assert counts["amneziawg2"] == 1
        assert (
            db.query(OpenVpnAccessPolicy)
            .filter_by(node_id=node.id, client_name="ovpn")
            .first()
            .block_reason
            == "access_expired"
        )
        assert (
            db.query(WgAccessPolicy)
            .filter_by(node_id=node.id, client_name="wg")
            .first()
            .block_reason
            == "access_expired"
        )
        assert (
            db.query(AmneziaWg2AccessPolicy)
            .filter_by(node_id=node.id, client_name="awg2")
            .first()
            .block_reason
            == "access_expired"
        )
    finally:
        db.close()
        engine.dispose()


def test_wg_access_until_aliases_expires_at():
    engine, db = _make_db()
    try:
        node = _make_node(db)
        until = datetime.now(timezone.utc) + timedelta(days=4)
        with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
            state = set_access_until(db, "wireguard", node.id, "Alice", until, actor="admin")

        row = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").first()
        assert row is not None
        assert row.expires_at == until
        assert get_access_until(db, "wireguard", node.id, "Alice") == until
        assert state["access_until"] == until.isoformat()
    finally:
        db.close()
        engine.dispose()


def test_openvpn_access_until_route_wires_replication():
    db = MagicMock()
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    user = SimpleNamespace(id=7, username="admin")
    until = datetime(2030, 1, 1, tzinfo=timezone.utc)

    with (
        patch.object(client_access, "_set_access_until", return_value={"access_until": until.isoformat()}) as set_until,
        patch.object(client_access, "log_action") as log_action,
        patch.object(client_access, "_replicate_policy_after_success") as replicate,
    ):
        result = client_access.openvpn_set_access_until(
            "Ivan",
            client_access.AccessUntilRequest(access_until=until),
            request=request,
            db=db,
            user=user,
        )

    assert result["access_until"] == until.isoformat()
    set_until.assert_called_once_with(
        db,
        protocol="openvpn",
        client_name="Ivan",
        access_until=until,
        actor="admin",
    )
    log_action.assert_called_once()
    replicate.assert_called_once_with(
        db,
        client_name="Ivan",
        vpn_type=client_access.VpnType.openvpn,
        op="set_access_until",
        actor="admin",
        access_until=until,
    )
