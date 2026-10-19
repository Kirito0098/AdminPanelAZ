"""Stage 2 Task 12: платёжное фото — превью в панели (6.8).

Перекодировка Pillow в памяти, без диска, лимит 5 МБ, заголовки безопасности —
покрытие service-функций; заголовки проверяются в приложении (webapp-testing).
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

import pytest

from app.services.request_receipt_preview import (
    ReceiptDecodeError,
    build_receipt_preview_jpeg,
    get_cached_or_build_preview,
    reencode_receipt_bytes,
)


def _jpeg_with_exif(size=(2000, 1000)) -> bytes:
    img = Image.new("RGB", size, color=(10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_reencode_strips_size_and_has_no_exif(monkeypatch):
    raw = _jpeg_with_exif()
    monkeypatch.setattr(
        "app.services.request_receipt_preview.download_telegram_file",
        lambda *_a, **_k: raw,
    )
    out = build_receipt_preview_jpeg(file_id="x", bot_token="t")
    img = Image.open(BytesIO(out))
    assert max(img.size) <= 1600
    assert img.format == "JPEG"
    assert not img.getexif() or dict(img.getexif()) == {}


def test_reencode_respects_5mb_cap():
    big = b"\x00" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ReceiptDecodeError):
        reencode_receipt_bytes(big)


def test_broken_image_raises():
    with pytest.raises(ReceiptDecodeError):
        reencode_receipt_bytes(b"not-an-image")


def test_preview_never_writes_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.services.request_receipt_preview.download_telegram_file",
        lambda *_: _jpeg_with_exif((800, 600)),
    )
    build_receipt_preview_jpeg(file_id="x", bot_token="t")
    assert list(tmp_path.iterdir()) == []


def test_cache_returns_same_bytes(monkeypatch):
    raw = _jpeg_with_exif((300, 300))
    monkeypatch.setattr(
        "app.services.request_receipt_preview.download_telegram_file",
        lambda *_a, **_k: raw,
    )
    out1 = build_receipt_preview_jpeg(file_id="x", bot_token="t")
    out2 = build_receipt_preview_jpeg(file_id="x", bot_token="t")
    assert out1 == out2


def test_get_cached_or_build_preview_raises_without_receipt():
    from app.models import Base, UserAccessRequest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        req = UserAccessRequest(
            request_type="extend_access",
            telegram_id="1",
            status="pending",
        )
        session.add(req)
        session.commit()
        with pytest.raises(ReceiptDecodeError):
            get_cached_or_build_preview(session, req)
    finally:
        session.close()
        engine.dispose()
