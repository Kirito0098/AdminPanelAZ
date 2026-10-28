"""B1: GET qr-download shows HTML page and must not bump download_count."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import QrDownloadToken
from app.routers import public_download as public_download_router
from app.services.qr_download import QrDownloadService


@pytest.fixture()
def factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qr.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture
def client(factory):
    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(public_download_router.router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c


def _issue(factory) -> str:
    with factory() as db:
        return QrDownloadService(db, max_downloads=1).create_token(
            file_path="/root/antizapret/client/wg/alice.conf",
            config_type="wireguard",
            config_name="alice.conf",
            node_id=1,
        )["token"]


def test_qr_download_get_does_not_increment_download_count(client, factory):
    token = _issue(factory)
    with (
        patch("app.routers.public_download.ip_restriction_service") as ip_svc,
        patch("app.routers.public_download.public_download_rate_limit_service"),
        patch(
            "app.routers.public_download._qr_settings",
            return_value={"ttl_seconds": 600, "max_downloads": 1, "pin": ""},
        ),
        patch("app.routers.public_download._global_pin_set", return_value=False),
    ):
        ip_svc.get_client_ip.return_value = "203.0.113.10"
        resp = client.get(f"/api/public/qr-download/{token}")

    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Скачать" in resp.text
    assert "alice.conf" in resp.text
    assert "document.forms[0].submit()" in resp.text
    assert "script-src 'nonce-" in resp.text
    with factory() as db:
        row = db.query(QrDownloadToken).one()
        assert row.download_count == 0


def test_qr_download_post_increments_download_count_and_returns_file(client, factory):
    token = _issue(factory)
    row_peek = MagicMock()
    row_peek.node_id = 1
    with (
        patch("app.routers.public_download.ip_restriction_service") as ip_svc,
        patch("app.routers.public_download.public_download_rate_limit_service"),
        patch(
            "app.routers.public_download._qr_settings",
            return_value={"ttl_seconds": 600, "max_downloads": 1, "pin": ""},
        ),
        patch("app.routers.public_download._qr_delivery_source", return_value=(MagicMock(), [])),
        patch("app.routers.public_download.read_profile_file_for_delivery", return_value="client\n"),
    ):
        ip_svc.get_client_ip.return_value = "198.51.100.2"
        resp = client.post(f"/api/public/qr-download/{token}", json={})

    assert resp.status_code == 200
    assert resp.content == b"client\n"
    assert "alice.conf" in resp.headers.get("content-disposition", "")
    with factory() as db:
        row = db.query(QrDownloadToken).one()
        assert row.download_count == 1
