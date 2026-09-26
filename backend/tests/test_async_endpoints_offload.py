"""Streams, WebSocket and upload endpoints keep blocking work off the event loop."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.auth import create_access_token, require_admin
from app.database import Base, get_db
from app.models import User, UserRole


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class _Request:
    async def is_disconnected(self) -> bool:
        return False


async def _first_chunks(response, count: int) -> list[str]:
    chunks: list[str] = []
    iterator = response.body_iterator
    try:
        async for chunk in iterator:
            chunks.append(chunk)
            if len(chunks) >= count:
                break
    finally:
        await iterator.aclose()
    return chunks


def test_iterate_in_thread_steps_off_loop_and_closes_early():
    from app.services.async_iter import iterate_in_thread

    steps: list[bool] = []
    closed: list[bool] = []

    def source():
        try:
            for item in ("a", "b", "c"):
                steps.append(_on_event_loop())
                yield item
        finally:
            closed.append(_on_event_loop())

    async def scenario():
        received = []
        stream = iterate_in_thread(source())
        async for item in stream:
            received.append(item)
            if item == "b":
                break
        await stream.aclose()
        return received

    assert asyncio.run(scenario()) == ["a", "b"]
    assert steps == [False, False]
    assert closed == [False]


def test_awg2_install_stream_reads_agent_off_loop(monkeypatch):
    from app.routers import awg2

    seen: list[bool] = []

    class Adapter:
        def awg2_iter_install_stream(self, mode, **_kw):
            for step in ("download", "install"):
                seen.append(_on_event_loop())
                yield {"event": step}

    monkeypatch.setattr(awg2, "SessionLocal", MagicMock)
    monkeypatch.setattr(awg2, "_admin_from_stream_token", lambda _t, _db: None)
    monkeypatch.setattr(awg2, "get_active_adapter", lambda _db: Adapter())

    async def scenario():
        response = await awg2.awg2_install_stream(
            _Request(), token="t", mode="install", preset=None, template=None, mtu=None
        )
        return await _first_chunks(response, 2)

    chunks = asyncio.run(scenario())
    assert len(chunks) == 2 and "download" in chunks[0]
    assert seen == [False, False]


def test_warper_update_stream_reads_agent_off_loop(monkeypatch):
    from app.routers import warper

    seen: list[bool] = []

    class Adapter:
        def warper_iter_update_stream(self):
            seen.append(_on_event_loop())
            yield {"event": "done"}

    monkeypatch.setattr(warper, "SessionLocal", MagicMock)
    monkeypatch.setattr(warper, "_admin_from_stream_token", lambda _t, _db: None)
    monkeypatch.setattr(warper, "get_active_adapter", lambda _db: Adapter())

    async def scenario():
        response = await warper.warper_updates_stream(_Request(), token="t")
        return await _first_chunks(response, 1)

    assert "done" in asyncio.run(scenario())[0]
    assert seen == [False]


def test_monitoring_stream_builds_overview_off_loop(monkeypatch):
    from app.routers import monitoring

    seen: list[bool] = []

    def build(_db, **_kw):
        seen.append(_on_event_loop())
        return SimpleNamespace(model_dump=lambda mode: {"ok": True})

    monkeypatch.setattr(monitoring, "SessionLocal", MagicMock)
    monkeypatch.setattr(
        monitoring, "_user_from_access_token", lambda _t, _db: SimpleNamespace(role=SimpleNamespace(value="admin"))
    )
    monkeypatch.setattr(monitoring, "_build_monitoring_overview", build)
    monkeypatch.setattr(monitoring, "_stream_interval_seconds", lambda: 0)

    async def scenario():
        response = await monitoring.monitoring_stream(_Request(), token="t", scope="node", ha_mode="dedupe")
        return await _first_chunks(response, 2)

    chunks = asyncio.run(scenario())
    assert '"ok": true' in chunks[0]
    assert seen == [False, False]


def test_server_monitor_ws_reads_metrics_off_loop(monkeypatch):
    from app.routers import server_monitor

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(User(username="admin", password_hash="x", role=UserRole.admin, is_active=True))
    db.commit()
    db.close()

    seen: list[bool] = []

    class Adapter:
        def get_server_metrics(self):
            seen.append(_on_event_loop())
            return {"cpu_percent": 1.0, "memory_percent": 2.0, "timestamp": "t"}

        def get_server_live_throughput(self, **_kw):
            seen.append(_on_event_loop())
            return {"interfaces": []}

    monkeypatch.setattr(database_module, "SessionLocal", factory)
    monkeypatch.setattr(server_monitor, "_is_server_monitor_enabled", lambda: True)
    monkeypatch.setattr(server_monitor, "get_active_adapter", lambda _db: Adapter())
    monkeypatch.setattr(server_monitor, "_WS_TICK_SLEEP_S", 0)

    app = FastAPI()
    app.include_router(server_monitor.router)
    token = create_access_token({"sub": "admin"})
    try:
        with TestClient(app).websocket_connect(f"/server-monitor/ws?token={token}") as ws:
            assert ws.receive_json()["cpu_percent"] == 1.0
    finally:
        engine.dispose()
    assert seen[:2] == [False, False]


def _client(router, db) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    admin = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_awg2_restore_runs_off_loop(monkeypatch):
    from app.routers import awg2

    seen: list[bool] = []

    class Adapter:
        def restore_awg2_backup(self, data, filename):
            seen.append(_on_event_loop())
            assert data == b"archive"
            return {"success": True}

    monkeypatch.setattr(awg2, "get_active_node", lambda _db: SimpleNamespace(id=1, name="n", host="10.0.0.1"))
    monkeypatch.setattr(awg2, "get_active_adapter", lambda _db: Adapter())
    monkeypatch.setattr(awg2, "_ha_sync_awg2_from_active", lambda _db: {"attempted": False})

    response = _client(awg2.router, MagicMock()).post(
        "/awg2/restore", files={"archive": ("a.tar.gz", io.BytesIO(b"archive"))}
    )
    assert response.status_code == 200, response.text
    assert seen == [False]


def test_backup_upload_runs_off_loop(monkeypatch):
    from app.routers import backups

    seen: list[bool] = []

    class Manager:
        def import_uploaded_backup(self, path, original_name):
            seen.append(_on_event_loop())
            assert path.read_bytes() == b"archive"
            raise RuntimeError("stop after import")

    monkeypatch.setattr(backups, "_get_backup_manager", lambda: Manager())

    response = _client(backups.router, MagicMock()).post(
        "/backups/upload", files={"file": ("b.tar.gz", io.BytesIO(b"archive"))}
    )
    assert response.status_code == 500
    assert seen == [False]


def test_configs_csv_import_runs_off_loop(monkeypatch):
    from app.routers import configs

    seen: list[bool] = []

    def parse(content):
        seen.append(_on_event_loop())
        assert content == b"name\n"
        raise ValueError("bad csv")

    monkeypatch.setattr(configs, "require_ha_primary_for_client_ops", lambda _db: None)
    monkeypatch.setattr(configs, "parse_import_csv", parse)

    response = _client(configs.router, MagicMock()).post(
        "/configs/import", files={"file": ("c.csv", io.BytesIO(b"name\n"))}
    )
    assert response.status_code == 400
    assert seen == [False]
