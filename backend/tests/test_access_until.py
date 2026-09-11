from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import warnings

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

warnings.filterwarnings("ignore", category=DeprecationWarning)


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
            counts_again = apply_due_access_blocks(db)

        assert counts["blocked"] == 3
        assert counts_again["blocked"] == 0
        assert counts["openvpn"] == 1
        assert counts["wireguard"] == 1
        assert counts["amneziawg2"] == 1
        assert adapter.block_wireguard_client_runtime.call_count == 1
        assert adapter.block_awg2_client_runtime.call_count == 1
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
        assert row.expires_at == until.replace(tzinfo=None)
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


def test_wg_access_renew_preserves_manual_permanent_block():
    engine, db = _make_db()
    try:
        node = _make_node(db)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=7)
        db.add(
            WgAccessPolicy(
                node_id=node.id,
                client_name="alice",
                expires_at=past.replace(tzinfo=None),
                is_temp_blocked=False,
                is_permanent_blocked=True,
                block_reason="access_expired",
            )
        )
        db.add(
            AmneziaWg2AccessPolicy(
                node_id=node.id,
                client_name="alice",
                access_until=past.replace(tzinfo=None),
                is_temp_blocked=False,
                is_permanent_blocked=True,
                block_reason="access_expired",
            )
        )
        db.commit()

        with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
            wg_state = set_access_until(db, "wireguard", node.id, "alice", future, actor="admin")
            awg2_state = set_access_until(db, "amneziawg2", node.id, "alice", future, actor="admin")

        wg_row = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
        awg2_row = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
        assert wg_row.is_permanent_blocked is True
        assert awg2_row.is_permanent_blocked is True
        assert wg_state["block_mode"] == "permanent"
        assert awg2_state["block_mode"] == "permanent"
        assert wg_state["is_blocked"] is True
        assert awg2_state["is_blocked"] is True
    finally:
        db.close()
        engine.dispose()


def test_manual_unblock_while_access_expired_defers_reblock_to_worker():
    from pathlib import Path

    from app.services.access_policy import AccessPolicyService

    engine, db = _make_db()
    try:
        node = _make_node(db)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        db.add(
            OpenVpnAccessPolicy(
                node_id=node.id,
                client_name="Alice",
                access_until=past.replace(tzinfo=None),
                is_temp_blocked=False,
                is_permanent_blocked=False,
                block_reason="access_expired",
            )
        )
        db.add(
            WgAccessPolicy(
                node_id=node.id,
                client_name="alice",
                expires_at=past.replace(tzinfo=None),
                is_temp_blocked=False,
                is_permanent_blocked=False,
                block_reason="access_expired",
            )
        )
        db.commit()

        adapter = _adapter()
        service = AccessPolicyService(
            db,
            antizapret_path=Path("/tmp"),
            node_id=node.id,
            node_name=node.name,
            adapter=adapter,
        )
        with (
            patch.object(service, "read_banned_clients", return_value={"Alice"}),
            patch.object(service, "write_banned_clients") as write_banned,
        ):
            ovpn_state = service.openvpn_unblock("Alice", actor="admin")
            write_banned.assert_called_once_with(set())

        wg_state = service.wg_unblock("alice", actor="admin")
        adapter.unblock_wireguard_client_runtime.assert_called_once_with("alice")

        # Policy date still expired (state reports access_expired), but reason cleared for worker re-apply.
        ovpn_row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
        wg_row = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
        assert ovpn_row.block_reason is None
        assert wg_row.block_reason is None
        assert ovpn_state["block_mode"] == "access_expired"
        assert wg_state["block_mode"] == "access_expired"

        with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
            counts = apply_due_access_blocks(db)
        assert counts["blocked"] >= 1
        db.refresh(ovpn_row)
        db.refresh(wg_row)
        assert ovpn_row.block_reason == "access_expired"
        assert wg_row.block_reason == "access_expired"
    finally:
        db.close()
        engine.dispose()


def test_set_access_until_require_deadline_skips_when_extended():
    engine, db = _make_db()
    try:
        node = _make_node(db)
        now = datetime.now(timezone.utc)
        expired = now - timedelta(minutes=5)
        future = now + timedelta(days=10)
        adapter = _adapter()
        with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
            set_access_until(db, "openvpn", node.id, "Alice", expired, actor="admin")
            set_access_until(db, "openvpn", node.id, "Alice", future, actor="unlock_codes")
            result = set_access_until(
                db,
                "openvpn",
                node.id,
                "Alice",
                expired,
                actor="access_expiry_worker",
                require_deadline_lte=now,
            )

        assert result is None
        assert get_access_until(db, "openvpn", node.id, "Alice") == future
        row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
        assert row.block_reason != "access_expired"
    finally:
        db.close()
        engine.dispose()


def test_apply_due_access_blocks_does_not_clobber_concurrent_extension():
    engine, db = _make_db()
    try:
        node = _make_node(db)
        now = datetime.now(timezone.utc)
        expired = now - timedelta(minutes=5)
        future = now + timedelta(days=14)
        adapter = _adapter()
        with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
            db.add(
                OpenVpnAccessPolicy(
                    node_id=node.id,
                    client_name="Alice",
                    access_until=expired.replace(tzinfo=None),
                )
            )
            db.add(
                WgAccessPolicy(
                    node_id=node.id,
                    client_name="alice",
                    expires_at=expired.replace(tzinfo=None),
                )
            )
            db.commit()

            # After worker collects due rows and releases its read snapshot, a
            # concurrent redeem extends deadlines before claim UPDATEs run.
            orig_commit = db.commit
            released = {"done": False}

            def commit_then_concurrent_redeem():
                if not released["done"]:
                    released["done"] = True
                    orig_commit()
                    other = sessionmaker(bind=engine)()
                    try:
                        set_access_until(other, "openvpn", node.id, "Alice", future, actor="unlock_codes")
                        set_access_until(other, "wireguard", node.id, "Alice", future, actor="unlock_codes")
                    finally:
                        other.close()
                    return None
                return orig_commit()

            db.commit = commit_then_concurrent_redeem  # type: ignore[method-assign]
            try:
                counts = apply_due_access_blocks(db)
            finally:
                db.commit = orig_commit  # type: ignore[method-assign]

        assert counts["rows_due"] == 2
        assert counts["blocked"] == 0
        assert counts["skipped"] == 2
        assert get_access_until(db, "openvpn", node.id, "Alice") == future
        assert get_access_until(db, "wireguard", node.id, "Alice") == future
        ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
        wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
        assert ovpn.block_reason != "access_expired"
        assert wg.block_reason != "access_expired"
    finally:
        db.close()
        engine.dispose()
