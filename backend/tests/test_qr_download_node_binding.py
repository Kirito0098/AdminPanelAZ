"""One-time QR links read the profile from the node they were issued for."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base, get_db
from app.models import Node, QrDownloadToken
from app.routers import public_download as public_download_router
from app.services.qr_download import QrDownloadService

P = "app.routers.public_download"


def _client(db) -> TestClient:
    app = FastAPI()
    app.include_router(public_download_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _row(node_id: int | None) -> MagicMock:
    row = MagicMock()
    row.node_id = node_id
    row.pin_hash = None
    row.file_path = "/root/antizapret/client/wg/alice.conf"
    row.config_name = "alice.conf"
    return row


def _download(db, row, *, method: str = "GET", active_node=None, adapter=None):
    with (
        patch(f"{P}.ip_restriction_service"),
        patch(f"{P}.public_download_rate_limit_service"),
        patch(f"{P}._qr_settings", return_value={"ttl_seconds": 60, "max_downloads": 1, "pin": ""}),
        patch(f"{P}._global_pin_set", return_value=False),
        patch(f"{P}.QrDownloadService") as svc,
        patch(f"{P}.get_active_node", side_effect=lambda _db: active_node) as active,
        patch(f"{P}.get_adapter_for_node", return_value=adapter or MagicMock()) as for_node,
        patch(f"{P}.load_node_remote_hosts", return_value=["vpn.example"]) as hosts,
        patch(f"{P}.read_profile_file_for_delivery", return_value="cfg\n") as read,
    ):
        svc.return_value.peek_token.return_value = row
        svc.return_value.redeem_token.return_value = row
        client = _client(db)
        if method == "GET":
            response = client.get("/api/public/qr-download/tok")
        else:
            response = client.post("/api/public/qr-download/tok", json={"pin": ""})
        return response, SimpleNamespace(svc=svc, active=active, for_node=for_node, hosts=hosts, read=read)


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_link_reads_file_from_its_own_node(method):
    node7 = SimpleNamespace(id=7, name="vpn-7")
    db = MagicMock()
    db.get.return_value = node7
    adapter = MagicMock()

    response, calls = _download(db, _row(7), method=method, adapter=adapter)

    assert response.status_code == 200
    assert response.content == b"cfg\n"
    db.get.assert_called_once_with(Node, 7)
    calls.active.assert_not_called()
    calls.for_node.assert_called_once_with(node7)
    calls.hosts.assert_called_once_with(db, 7)
    calls.read.assert_called_once_with(adapter, "/root/antizapret/client/wg/alice.conf", ["vpn.example"])


def test_link_of_deleted_node_is_gone_without_spending_a_download():
    db = MagicMock()
    db.get.return_value = None

    response, calls = _download(db, _row(7))

    assert response.status_code == 410
    assert response.json()["detail"] == "Сервер этой ссылки удалён — запросите новую ссылку"
    calls.svc.return_value.redeem_token.assert_not_called()


def test_legacy_link_without_node_uses_active_node():
    active = SimpleNamespace(id=1, name="local")

    response, calls = _download(MagicMock(), _row(None), active_node=active)

    assert response.status_code == 200
    calls.for_node.assert_called_once_with(active)


def test_create_token_stores_node_id():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        QrDownloadService(db).create_token(
            file_path="/root/antizapret/client/wg/alice.conf",
            config_type="wireguard",
            config_name="alice.conf",
            node_id=7,
        )
        row = db.query(QrDownloadToken).one()
        assert row.node_id == 7
        assert row.pin_failures == 0
    engine.dispose()


def test_migration_adds_qr_token_columns(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE qr_download_tokens (id INTEGER PRIMARY KEY, token_hash VARCHAR(64))"))
        conn.execute(text("INSERT INTO qr_download_tokens (id, token_hash) VALUES (1, 'h')"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_qr_download_tokens_columns()
    database._migrate_qr_download_tokens_columns()

    cols = {col["name"] for col in inspect(engine).get_columns("qr_download_tokens")}
    assert {"node_id", "pin_failures"} <= cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT node_id, pin_failures FROM qr_download_tokens")).one() == (None, 0)
    engine.dispose()
