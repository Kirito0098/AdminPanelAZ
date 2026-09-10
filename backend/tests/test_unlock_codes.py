from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app import database
from app.database import Base, get_db, run_db_migrations
from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    UnlockCode,
    UnlockCodeRedemption,
    User,
    UserRole,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
from app.routers import unlock_codes as unlock_codes_router
from app.services.feature_guards import check_path_access, module_disabled_message
from app.services.feature_toggles import FeatureToggleService
from app.services.unlock_codes import create_unlock_code, generate_code_value, redeem_unlock_code



def _create_legacy_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL PRIMARY KEY,
                    username VARCHAR(64),
                    role VARCHAR(16) NOT NULL,
                    telegram_id VARCHAR(32),
                    can_create_configs INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE openvpn_access_policy (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
                    is_temp_blocked BOOLEAN,
                    is_permanent_blocked BOOLEAN,
                    block_reason VARCHAR(32),
                    block_started_at DATETIME,
                    block_days INTEGER,
                    block_until DATETIME,
                    traffic_limit_bytes BIGINT,
                    traffic_limit_period_days INTEGER,
                    updated_by VARCHAR(64),
                    updated_at DATETIME,
                    UNIQUE (node_id, client_name),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE amneziawg2_access_policies (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
                    is_temp_blocked BOOLEAN,
                    is_permanent_blocked BOOLEAN,
                    block_reason VARCHAR(32),
                    block_started_at DATETIME,
                    block_days INTEGER,
                    block_until DATETIME,
                    traffic_limit_bytes BIGINT,
                    traffic_limit_period_days INTEGER,
                    updated_by VARCHAR(64),
                    updated_at DATETIME,
                    UNIQUE (node_id, client_name),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE wg_access_policy (
                    id INTEGER NOT NULL PRIMARY KEY,
                    node_id INTEGER NOT NULL,
                    client_name VARCHAR(64) NOT NULL,
                    expires_at DATETIME,
                    is_temp_blocked BOOLEAN,
                    is_permanent_blocked BOOLEAN,
                    block_reason VARCHAR(32),
                    block_started_at DATETIME,
                    block_days INTEGER,
                    block_until DATETIME,
                    traffic_limit_bytes BIGINT,
                    traffic_limit_period_days INTEGER,
                    updated_by VARCHAR(64),
                    updated_at DATETIME,
                    UNIQUE (node_id, client_name),
                    FOREIGN KEY(node_id) REFERENCES nodes (id)
                )
                """
            )
        )



def _make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session



def _make_node(db, *, name: str = "node-1", is_local: bool = True) -> Node:
    node = Node(
        name=name,
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=is_local,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node



def _make_user(db, *, username: str = "admin", role: UserRole = UserRole.admin) -> User:
    user = User(username=username, password_hash="hash", role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user



def _make_configs(db, node_id: int, user_id: int, client_name: str, protocols: list[VpnType]) -> None:
    for vpn_type in protocols:
        db.add(
            VpnConfig(
                node_id=node_id,
                client_name=client_name,
                vpn_type=vpn_type,
                owner_id=user_id,
            )
        )
    db.commit()



def _make_policy_rows(db, node_id: int, client_name: str, *, blocked: bool = True) -> None:
    db.add(
        OpenVpnAccessPolicy(
            node_id=node_id,
            client_name=client_name,
            is_temp_blocked=blocked,
            is_permanent_blocked=False,
            block_reason="manual_temp" if blocked else None,
        )
    )
    db.add(
        WgAccessPolicy(
            node_id=node_id,
            client_name=client_name,
            expires_at=None,
            is_temp_blocked=blocked,
            is_permanent_blocked=False,
            block_reason="manual_temp" if blocked else None,
        )
    )
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=node_id,
            client_name=client_name,
            is_temp_blocked=blocked,
            is_permanent_blocked=False,
            block_reason="manual_temp" if blocked else None,
        )
    )
    db.commit()


@pytest.fixture()
def db():
    engine, Session = _make_db()
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()



def test_unlock_code_models_and_migrations_smoke(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    _create_legacy_schema(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))

    run_db_migrations()

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert UnlockCode.__tablename__ == "unlock_codes"
    assert UnlockCodeRedemption.__tablename__ == "unlock_code_redemptions"
    assert {"unlock_codes", "unlock_code_redemptions"}.issubset(tables)
    assert "access_until" in {col["name"] for col in inspector.get_columns("openvpn_access_policy")}
    assert "access_until" in {col["name"] for col in inspector.get_columns("amneziawg2_access_policies")}
    assert "access_until" not in {col["name"] for col in inspector.get_columns("wg_access_policy")}
    assert "redemption_count" in {col["name"] for col in inspector.get_columns("unlock_codes")}
    redemptions_uniques = inspector.get_unique_constraints("unlock_code_redemptions")
    assert any(
        set(constraint.get("column_names") or []) == {"code_id", "client_name", "node_id"}
        or constraint.get("name") == "uq_unlock_code_redemptions_code_client_node"
        for constraint in redemptions_uniques
    ) or any(
        index.get("unique") and set(index.get("column_names") or []) == {"code_id", "client_name", "node_id"}
        for index in inspector.get_indexes("unlock_code_redemptions")
    )

    engine.dispose()



def test_unlock_code_model_metadata():
    assert OpenVpnAccessPolicy.__tablename__ == "openvpn_access_policy"
    assert AmneziaWg2AccessPolicy.__tablename__ == "amneziawg2_access_policies"
    assert WgAccessPolicy.__tablename__ == "wg_access_policy"



def test_generate_code_value_is_url_safe():
    code = generate_code_value()
    assert len(code) == 14
    assert code.count("-") == 2
    assert all(part.isalnum() and part.upper() == part for part in code.split("-"))


def test_create_unlock_code_rejects_short_custom_code(db):
    admin = _make_user(db)
    with pytest.raises(ValueError, match="between 8 and 32"):
        create_unlock_code(
            db,
            grant_days=7,
            protocols=["openvpn"],
            mode="single",
            max_redemptions=1,
            code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
            creator=admin,
            code="SHORT7",
        )


def test_redeem_unlock_code_rejects_feature_off(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="FEATURE-OFF-1",
    )

    with patch(
        "app.services.unlock_codes.get_feature_service",
        return_value=SimpleNamespace(is_enabled=lambda key: False),
    ):
        with pytest.raises(ValueError, match="отключён"):
            redeem_unlock_code(db, code="feature-off-1", client_name="Alice", node_id=node.id)



def test_redeem_unlock_code_applies_protocols_and_extends_from_current(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn, VpnType.wireguard])
    _make_policy_rows(db, node.id, "alice")
    create_unlock_code(
        db,
        grant_days=7,
        protocols=["openvpn", "wireguard"],
        mode="multi",
        max_redemptions=3,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="ABCD-EFGH-IJKL",
    )

    fixed_now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    current_values = {
        "openvpn": fixed_now + timedelta(days=2),
        "wireguard": None,
    }
    calls: list[tuple[str, int, str, datetime]] = []

    def _fake_get_access_until(_db, protocol, _node_id, _client_name):
        return current_values[protocol]

    def _fake_set_access_until(_db, protocol, node_id, client_name, access_until, *, actor, commit):
        calls.append((protocol, node_id, client_name, access_until))
        current_values[protocol] = access_until
        return {"access_until": access_until.isoformat()}

    with (
        patch("app.services.unlock_codes._now", return_value=fixed_now),
        patch("app.services.unlock_codes.get_access_until", side_effect=_fake_get_access_until),
        patch("app.services.unlock_codes.set_access_until", side_effect=_fake_set_access_until),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch.object(db, "commit", wraps=db.commit) as commit_spy,
    ):
        result = redeem_unlock_code(db, code="abcd-efgh-ijkl", client_name="Alice", node_id=node.id)

    assert result["grant_days"] == 7
    assert result["protocols_applied"] == ["openvpn", "wireguard"]
    assert result["access_until_by_protocol"]["openvpn"] == (fixed_now + timedelta(days=9)).isoformat()
    assert result["access_until_by_protocol"]["wireguard"] == (fixed_now + timedelta(days=7)).isoformat()
    assert calls == [
        ("openvpn", node.id, "alice", fixed_now + timedelta(days=9)),
        ("wireguard", node.id, "alice", fixed_now + timedelta(days=7)),
    ]
    assert commit_spy.call_count == 1

    openvpn_row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="alice").first()
    wg_row = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").first()
    redemption = db.query(UnlockCodeRedemption).filter_by(client_name="alice", node_id=node.id).first()
    assert openvpn_row is not None and openvpn_row.is_temp_blocked is False and openvpn_row.block_reason is None
    assert wg_row is not None and wg_row.is_temp_blocked is False and wg_row.block_reason is None
    assert redemption is not None and redemption.code_id == 1


def test_redeem_unlock_code_replicates_access_until_to_ha(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn, VpnType.wireguard])
    create_unlock_code(
        db,
        grant_days=7,
        protocols=["openvpn", "wireguard"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="HA-REDEEM-01",
    )

    fixed_now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    replicate_calls: list[dict] = []

    def _fake_replicate(_db, *, node_id, client_name, vpn_type, op, **kwargs):
        replicate_calls.append(
            {
                "node_id": node_id,
                "client_name": client_name,
                "vpn_type": vpn_type,
                "op": op,
                "access_until": kwargs.get("access_until"),
                "actor": kwargs.get("actor"),
            }
        )
        return {"applied": [], "errors": [], "skipped": False}

    with (
        patch("app.services.unlock_codes._now", return_value=fixed_now),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            side_effect=lambda *_a, **_k: {"access_until": (fixed_now + timedelta(days=7)).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch(
            "app.services.node_sync.policy_sync.maybe_replicate_policy_op",
            side_effect=_fake_replicate,
        ),
    ):
        redeem_unlock_code(db, code="HA-REDEEM-01", client_name="Alice", node_id=node.id)

    assert len(replicate_calls) == 2
    assert {call["vpn_type"] for call in replicate_calls} == {VpnType.openvpn, VpnType.wireguard}
    assert all(call["op"] == "set_access_until" for call in replicate_calls)
    assert all(call["actor"] == "unlock_codes" for call in replicate_calls)
    assert all(call["node_id"] == node.id for call in replicate_calls)
    assert all(call["access_until"] == fixed_now + timedelta(days=7) for call in replicate_calls)


def test_redeem_unlock_code_same_client_twice_fails(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=5,
        protocols=["openvpn"],
        mode="multi",
        max_redemptions=2,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="SAME-CLIENT-01",
    )

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            return_value={"access_until": datetime(2030, 1, 6, tzinfo=timezone.utc).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
    ):
        redeem_unlock_code(db, code="same-client-01", client_name="Alice", node_id=node.id)
        with pytest.raises(ValueError, match="использован вами"):
            redeem_unlock_code(db, code="same-client-01", client_name="alice", node_id=node.id)


def test_redeem_unlock_code_same_client_name_on_different_nodes_ok(db):
    node_a = _make_node(db, name="node-a")
    node_b = _make_node(db, name="node-b")
    admin = _make_user(db)
    _make_configs(db, node_a.id, admin.id, "alice", [VpnType.openvpn])
    _make_configs(db, node_b.id, admin.id, "alice", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=5,
        protocols=["openvpn"],
        mode="multi",
        max_redemptions=5,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="CROSS-NODE-01",
    )

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            return_value={"access_until": datetime(2030, 1, 6, tzinfo=timezone.utc).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch("app.services.unlock_codes._policy_service_for_node", return_value=SimpleNamespace()),
    ):
        first = redeem_unlock_code(db, code="CROSS-NODE-01", client_name="Alice", node_id=node_a.id)
        second = redeem_unlock_code(db, code="CROSS-NODE-01", client_name="Alice", node_id=node_b.id)

    assert first["grant_days"] == 5
    assert second["grant_days"] == 5
    assert db.query(UnlockCodeRedemption).filter_by(client_name="alice").count() == 2
    assert (
        db.query(UnlockCodeRedemption).filter_by(client_name="alice", node_id=node_a.id).count() == 1
    )
    assert (
        db.query(UnlockCodeRedemption).filter_by(client_name="alice", node_id=node_b.id).count() == 1
    )


def test_redeem_unlock_code_rolls_back_on_protocol_failure(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn, VpnType.wireguard])
    _make_policy_rows(db, node.id, "alice")
    create_unlock_code(
        db,
        grant_days=5,
        protocols=["openvpn", "wireguard"],
        mode="multi",
        max_redemptions=2,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="ROLLBACK-01",
    )

    calls = 0

    def _fake_set_access_until(_db, protocol, node_id, client_name, access_until, *, actor, commit):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("boom")
        return {"access_until": access_until.isoformat()}

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch("app.services.unlock_codes.set_access_until", side_effect=_fake_set_access_until),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch.object(db, "commit", wraps=db.commit) as commit_spy,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            redeem_unlock_code(db, code="rollback-01", client_name="Alice", node_id=node.id)

    db.rollback()
    assert commit_spy.call_count == 0
    assert db.query(UnlockCodeRedemption).filter_by(client_name="alice", node_id=node.id).count() == 0
    openvpn_row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="alice").first()
    assert openvpn_row is not None and openvpn_row.is_temp_blocked is True


def test_redeem_unlock_code_second_client_ok(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    _make_configs(db, node.id, admin.id, "bob", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="multi",
        max_redemptions=2,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="MULTI-0001",
    )

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            return_value={"access_until": datetime(2030, 1, 4, tzinfo=timezone.utc).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
    ):
        first = redeem_unlock_code(db, code="multi-0001", client_name="Alice", node_id=node.id)
        second = redeem_unlock_code(db, code="multi-0001", client_name="Bob", node_id=node.id)

    assert first["protocols_applied"] == ["openvpn"]
    assert second["protocols_applied"] == ["openvpn"]
    assert db.query(UnlockCodeRedemption).filter_by(code_id=1).count() == 2



def test_redeem_unlock_code_converts_duplicate_integrity_error(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="multi",
        max_redemptions=2,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="DUPERR-0001",
    )

    integrity_error = IntegrityError(
        "insert",
        {},
        Exception("UNIQUE constraint failed: unlock_code_redemptions.code_id, unlock_code_redemptions.client_name"),
    )

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            return_value={"access_until": datetime(2030, 1, 4, tzinfo=timezone.utc).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch.object(db, "commit", side_effect=integrity_error),
    ):
        with pytest.raises(ValueError, match="использован вами"):
            redeem_unlock_code(db, code="duperr-0001", client_name="Alice", node_id=node.id)

    db.rollback()
    assert db.query(UnlockCodeRedemption).filter_by(client_name="alice", node_id=node.id).count() == 0


def test_redeem_unlock_code_rejects_revoked(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    row = create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        creator=admin,
        code="REVOKE-0001",
    )
    row.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    with pytest.raises(ValueError, match="отозван"):
        redeem_unlock_code(db, code="revoke-0001", client_name="Alice", node_id=node.id)



def test_redeem_unlock_code_rejects_no_protocol_overlap(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=3,
        protocols=["wireguard"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        creator=admin,
        code="NOPROTO-01",
    )

    with pytest.raises(ValueError, match="Нет пересечения протоколов"):
        redeem_unlock_code(db, code="noproto-01", client_name="Alice", node_id=node.id)


def test_redeem_single_code_second_client_hits_atomic_limit(db):
    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    _make_configs(db, node.id, admin.id, "bob", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime(2040, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="LIMIT-0001",
    )

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            return_value={"access_until": datetime(2030, 1, 4, tzinfo=timezone.utc).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch(
            "app.services.unlock_codes._policy_service_for_node",
            return_value=SimpleNamespace(
                reconcile_openvpn=lambda *_a, **_k: None,
                reconcile_wg=lambda *_a, **_k: None,
                reconcile_awg2=lambda *_a, **_k: None,
            ),
        ),
    ):
        redeem_unlock_code(db, code="LIMIT-0001", client_name="Alice", node_id=node.id)
        with pytest.raises(ValueError, match="Лимит"):
            redeem_unlock_code(db, code="LIMIT-0001", client_name="Bob", node_id=node.id)

    row = db.query(UnlockCode).filter_by(code="LIMIT-0001").one()
    assert row.redemption_count == 1
    assert db.query(UnlockCodeRedemption).filter_by(code_id=row.id).count() == 1


def test_list_unlock_codes_marks_exhausted_and_includes_redemptions(db):
    from app.services.unlock_codes import list_unlock_codes

    node = _make_node(db)
    admin = _make_user(db)
    _make_configs(db, node.id, admin.id, "alice", [VpnType.openvpn])
    create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime(2040, 1, 1, tzinfo=timezone.utc),
        creator=admin,
        code="MARKED-001",
    )

    with (
        patch("app.services.unlock_codes._now", return_value=datetime(2030, 1, 1, tzinfo=timezone.utc)),
        patch("app.services.unlock_codes.get_access_until", return_value=None),
        patch(
            "app.services.unlock_codes.set_access_until",
            return_value={"access_until": datetime(2030, 1, 4, tzinfo=timezone.utc).isoformat()},
        ),
        patch("app.services.unlock_codes._reconcile_access_until", return_value=None),
        patch("app.services.unlock_codes._policy_service_for_node", return_value=SimpleNamespace()),
    ):
        redeem_unlock_code(db, code="MARKED-001", client_name="Alice", node_id=node.id)

    listed = list_unlock_codes(db)
    assert len(listed) == 1
    item = listed[0]
    assert item["code"] == "MARKED-001"
    assert item["exhausted"] is True
    assert item["redemption_count"] == 1
    assert len(item["redemptions"]) == 1
    assert item["redemptions"][0]["client_name"] == "alice"
    assert item["redemptions"][0]["node_id"] == node.id
    assert item["redemptions"][0]["node_name"] == node.name


def test_atomic_redemption_slot_update_rejects_when_full(db):
    admin = _make_user(db)
    row = create_unlock_code(
        db,
        grant_days=3,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=None,
        creator=admin,
        code="SLOT-0001",
    )
    first = db.execute(
        text(
            """
            UPDATE unlock_codes
            SET redemption_count = redemption_count + 1
            WHERE id = :id AND redemption_count < max_redemptions
            """
        ),
        {"id": row.id},
    )
    db.commit()
    second = db.execute(
        text(
            """
            UPDATE unlock_codes
            SET redemption_count = redemption_count + 1
            WHERE id = :id AND redemption_count < max_redemptions
            """
        ),
        {"id": row.id},
    )
    db.rollback()
    assert first.rowcount == 1
    assert second.rowcount == 0
    db.refresh(row)
    assert row.redemption_count == 1


def test_unlock_codes_routes_and_feature_guard(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_UNLOCK_CODES_ENABLED=false\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    assert check_path_access("/api/unlock-codes", service=service)[0] == "unlock_codes"
    assert module_disabled_message("unlock_codes")



def test_unlock_codes_admin_routes():
    engine, Session = _make_db()
    db = Session()
    _make_node(db)
    admin = _make_user(db)
    app = FastAPI()
    app.include_router(unlock_codes_router.router, prefix="/api")

    def _override_db():
        request_db = Session()
        try:
            yield request_db
        finally:
            request_db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[unlock_codes_router.get_feature_service] = lambda: SimpleNamespace(
        is_enabled=lambda key: True
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/unlock-codes",
            json={
                "grant_days": 10,
                "protocols": ["openvpn", "wireguard"],
                "mode": "multi",
                "max_redemptions": 2,
                "code": "ADMIN-0001",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["code"] == "ADMIN-0001"
        assert body["grant_days"] == 10
        assert body["exhausted"] is False
        assert body["redemption_count"] == 0
        assert body["redemptions"] == []

        listed = client.get("/api/unlock-codes")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["exhausted"] is False
        assert listed.json()[0]["redemptions"] == []

        revoked = client.post(f"/api/unlock-codes/{body['id']}/revoke")
        assert revoked.status_code == 200
        assert revoked.json()["ok"] is True

        active = client.get("/api/unlock-codes")
        assert active.status_code == 200
        assert active.json() == []

        all_codes = client.get("/api/unlock-codes", params={"include_revoked": True})
        assert all_codes.status_code == 200
        assert all_codes.json()[0]["revoked_at"] is not None

    db.close()
    engine.dispose()


def test_unlock_codes_admin_routes_rejects_short_custom_code():
    engine, Session = _make_db()
    db = Session()
    _make_node(db)
    admin = _make_user(db)
    app = FastAPI()
    app.include_router(unlock_codes_router.router, prefix="/api")

    def _override_db():
        request_db = Session()
        try:
            yield request_db
        finally:
            request_db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[unlock_codes_router.get_feature_service] = lambda: SimpleNamespace(
        is_enabled=lambda key: True
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/unlock-codes",
            json={
                "grant_days": 10,
                "protocols": ["openvpn"],
                "mode": "single",
                "code": "SHORT7",
            },
        )
        assert resp.status_code == 400
        assert "between 8 and 32" in resp.json()["detail"]

    db.close()
    engine.dispose()
