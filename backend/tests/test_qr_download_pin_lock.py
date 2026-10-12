"""One-time links: wrong PINs lock the link, downloads are claimed atomically."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import QrDownloadAuditLog, QrDownloadToken
from app.services.qr_download import MAX_PIN_FAILURES, QrDownloadService


@pytest.fixture()
def factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qr.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


def _issue(factory, *, pin: str = "", max_downloads: int = 1) -> str:
    with factory() as db:
        return QrDownloadService(db, max_downloads=max_downloads, pin=pin).create_token(
            file_path="/root/antizapret/client/wg/alice.conf",
            config_type="wireguard",
            config_name="alice.conf",
            node_id=1,
        )["token"]


def test_parallel_redeem_cannot_exceed_max_downloads(factory):
    token = _issue(factory)
    with factory() as late, factory() as early:
        late_svc = QrDownloadService(late)
        stale = late_svc.peek_token(token)
        assert stale.download_count == 0

        QrDownloadService(early).redeem_token(token)

        with pytest.raises(HTTPException) as exc:
            late_svc.redeem_token(token)

    assert exc.value.status_code == 410
    with factory() as db:
        assert db.query(QrDownloadToken).one().download_count == 1
        events = [row.event_type for row in db.query(QrDownloadAuditLog).order_by(QrDownloadAuditLog.id)]
    assert events == ["generated", "downloaded"]


def test_multi_download_link_counts_each_download(factory):
    token = _issue(factory, max_downloads=3)
    with factory() as db:
        svc = QrDownloadService(db)
        for expected in (1, 2, 3):
            assert svc.redeem_token(token).download_count == expected
        with pytest.raises(HTTPException) as exc:
            svc.redeem_token(token)
    assert exc.value.status_code == 410


def test_five_wrong_pins_lock_the_link(factory):
    token = _issue(factory, pin="4321")
    with factory() as db:
        svc = QrDownloadService(db)
        for _ in range(MAX_PIN_FAILURES - 1):
            with pytest.raises(HTTPException) as exc:
                svc.redeem_token(token, pin="0000")
            assert exc.value.status_code == 403

        with pytest.raises(HTTPException) as exc:
            svc.redeem_token(token, pin="0000")
        assert exc.value.status_code == 410
        assert exc.value.detail == "Ссылка заблокирована после 5 неверных PIN — запросите новую"

        with pytest.raises(HTTPException) as exc:
            svc.redeem_token(token, pin="4321")
        assert exc.value.status_code == 410

        row = db.query(QrDownloadToken).one()
        assert row.download_count == 0
        assert row.pin_failures == MAX_PIN_FAILURES


def test_correct_pin_after_a_mistake_still_downloads(factory):
    token = _issue(factory, pin="4321")
    with factory() as db:
        svc = QrDownloadService(db)
        with pytest.raises(HTTPException):
            svc.redeem_token(token, pin="0000")

        row = svc.redeem_token(token, pin="4321")

        assert row.download_count == 1
        assert row.used_at is not None
