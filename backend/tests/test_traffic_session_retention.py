"""Retention for traffic session history and refresh tokens; collector loads only relevant sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, RefreshToken, TrafficSessionState, User, UserRole
from app.services import retention
from app.services.traffic.collector import TrafficCollectorService, build_session_key
from app.services.traffic.maintenance import TrafficMaintenanceService


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _settings(**overrides):
    base = dict(
        retention_batch_size=100,
        traffic_sample_retention_days=90,
        action_log_retention_days=365,
        resource_metrics_retention_days=30,
        panel_resource_metrics_retention_days=30,
        traffic_session_retention_days=30,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Node(id=1, name="local", host="127.0.0.1", is_local=True))
    session.add(User(id=1, username="admin", password_hash="x", role=UserRole.admin))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _session(key: str, *, active: bool, last_seen: datetime, name: str = "alice") -> TrafficSessionState:
    return TrafficSessionState(
        node_id=1,
        session_key=key,
        profile="antizapret-udp",
        common_name=name,
        is_active=active,
        last_seen_at=last_seen,
        ended_at=None if active else last_seen,
    )


def test_purge_drops_only_old_finished_sessions(db, monkeypatch):
    monkeypatch.setattr(retention, "get_settings", lambda: _settings(traffic_session_retention_days=30))
    now = _now()
    db.add_all(
        [
            _session("old-ended", active=False, last_seen=now - timedelta(days=31)),
            _session("recent-ended", active=False, last_seen=now - timedelta(days=29)),
            _session("old-but-active", active=True, last_seen=now - timedelta(days=60)),
        ]
    )
    db.commit()

    counts = retention.run_retention_purge(db)

    keys = {row.session_key for row in db.query(TrafficSessionState).all()}
    assert keys == {"recent-ended", "old-but-active"}
    assert counts["traffic_session_state"] == 1


def test_purge_follows_configured_session_retention(db, monkeypatch):
    monkeypatch.setattr(retention, "get_settings", lambda: _settings(traffic_session_retention_days=7))
    db.add(_session("ended-10d", active=False, last_seen=_now() - timedelta(days=10)))
    db.commit()

    retention.run_retention_purge(db)

    assert db.query(TrafficSessionState).count() == 0


def test_purge_drops_refresh_tokens_expired_over_a_week_ago(db, monkeypatch):
    monkeypatch.setattr(retention, "get_settings", lambda: _settings())
    now = _now()
    db.add_all(
        [
            RefreshToken(user_id=1, token_hash="expired-8d", expires_at=now - timedelta(days=8)),
            RefreshToken(user_id=1, token_hash="expired-2d", expires_at=now - timedelta(days=2)),
            RefreshToken(
                user_id=1,
                token_hash="revoked-live",
                expires_at=now + timedelta(days=5),
                revoked=True,
                revoke_reason="rotated",
            ),
        ]
    )
    db.commit()

    counts = retention.run_retention_purge(db)

    assert {row.token_hash for row in db.query(RefreshToken).all()} == {"expired-2d", "revoked-live"}
    assert counts["refresh_tokens"] == 1


def _wg_client(name: str, key: str) -> dict:
    return {
        "session_kind": "wireguard",
        "common_name": name,
        "peer_public_key": key,
        "virtual_address": "10.29.8.2",
        "bytes_received": 100,
        "bytes_sent": 200,
    }


def _count_session_loads(db) -> list[str]:
    loaded: list[str] = []

    @event.listens_for(TrafficSessionState, "load")
    def _on_load(target, _context):
        loaded.append(target.session_key)

    db._session_load_listener = _on_load
    return loaded


def _seed_history(db, returning_key: str) -> None:
    now = _now()
    db.add_all(
        [_session(f"history-{i}", active=False, last_seen=now - timedelta(hours=i + 1)) for i in range(40)]
    )
    db.add(_session("still-active", active=True, last_seen=now, name="carol"))
    db.add(
        TrafficSessionState(
            node_id=1,
            session_key=returning_key,
            profile="antizapret-wg",
            common_name="bob",
            is_active=False,
            last_seen_at=now - timedelta(days=1),
            ended_at=now - timedelta(days=1),
            last_bytes_received=50,
            last_bytes_sent=50,
        )
    )
    db.commit()
    db.expunge_all()


def test_collector_loads_only_active_and_snapshot_sessions(db):
    status_rows = [{"profile": "antizapret-wg", "traffic_clients": [_wg_client("bob", "pk-bob")]}]
    returning_key = build_session_key("antizapret-wg", status_rows[0]["traffic_clients"][0])
    _seed_history(db, returning_key)
    loaded = _count_session_loads(db)
    try:
        TrafficCollectorService(db, 1).persist_snapshot(status_rows)
    finally:
        event.remove(TrafficSessionState, "load", db._session_load_listener)

    assert sorted(loaded) == sorted(["still-active", returning_key])
    rows = {row.session_key: row for row in db.query(TrafficSessionState).all()}
    assert len(rows) == 42
    assert rows[returning_key].is_active is True
    assert rows["still-active"].is_active is False


def test_collector_reuses_returning_session_beyond_first_key_chunk(db):
    clients = [_wg_client(f"user{i:04d}", f"pk-{i:04d}") for i in range(1200)]
    status_rows = [{"profile": "antizapret-wg", "traffic_clients": clients}]
    returning_key = max(build_session_key("antizapret-wg", client) for client in clients)
    db.add(
        TrafficSessionState(
            node_id=1,
            session_key=returning_key,
            profile="antizapret-wg",
            common_name="returning",
            is_active=False,
            last_seen_at=_now() - timedelta(days=1),
        )
    )
    db.commit()

    TrafficCollectorService(db, 1).persist_snapshot(status_rows)

    assert db.query(TrafficSessionState).count() == 1200
    row = db.query(TrafficSessionState).filter_by(session_key=returning_key).one()
    assert row.is_active is True


def test_active_session_lookup_uses_partial_index(db, monkeypatch):
    from sqlalchemy import text

    from app import database

    engine = db.get_bind()
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_traffic_session_state_node_active"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_traffic_session_state_active_index()

    captured: list[str] = []

    def _capture(_conn, _cursor, statement, _params, _context, _many):
        if "FROM traffic_session_state" in statement and "session_key IN" not in statement:
            captured.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        TrafficCollectorService(db, 1).persist_snapshot([])
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert captured
    with engine.connect() as conn:
        plan = conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {captured[0]}", (1,)).fetchall()
    assert any("ix_traffic_session_state_node_active" in str(row) for row in plan), plan


def test_scope_baseline_loads_only_active_and_snapshot_sessions(db):
    status_rows = [{"profile": "antizapret-wg", "traffic_clients": [_wg_client("bob", "pk-bob")]}]
    returning_key = build_session_key("antizapret-wg", status_rows[0]["traffic_clients"][0])
    _seed_history(db, returning_key)
    loaded = _count_session_loads(db)
    try:
        TrafficMaintenanceService(db, 1).seed_traffic_session_baseline_for_scope(status_rows, "all")
        db.commit()
    finally:
        event.remove(TrafficSessionState, "load", db._session_load_listener)

    assert sorted(loaded) == sorted(["still-active", returning_key])
    rows = {row.session_key: row for row in db.query(TrafficSessionState).all()}
    assert len(rows) == 42
    assert rows[returning_key].is_active is True
    assert rows["still-active"].is_active is False


def test_retention_settings_api_exposes_session_retention(db, monkeypatch, tmp_path):
    from app.config import get_settings as load_app_config
    from app.routers import settings as settings_router
    from app.schemas import RetentionSettingsUpdate

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_router, "ENV_FILE", env_file)
    monkeypatch.setattr(settings_router.admin_notify_service, "send_settings_change", lambda *a, **k: None)
    # setenv first so monkeypatch restores the variable the route writes into os.environ.
    monkeypatch.setenv("TRAFFIC_SESSION_RETENTION_DAYS", "30")
    monkeypatch.delenv("TRAFFIC_SESSION_RETENTION_DAYS")
    load_app_config.cache_clear()
    admin = db.get(User, 1)
    request = SimpleNamespace(headers={}, cookies={}, query_params={})
    try:
        assert settings_router.get_retention_settings(_=admin).traffic_session_retention_days == 30

        updated = settings_router.update_retention_settings(
            RetentionSettingsUpdate(traffic_session_retention_days=14), request, db=db, admin=admin
        )

        assert updated.traffic_session_retention_days == 14
        assert "TRAFFIC_SESSION_RETENTION_DAYS=14" in env_file.read_text(encoding="utf-8")
        with pytest.raises(ValueError):
            RetentionSettingsUpdate(traffic_session_retention_days=0)
    finally:
        load_app_config.cache_clear()
