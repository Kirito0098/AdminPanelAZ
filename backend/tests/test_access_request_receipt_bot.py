"""Stage 2 Task 11: приём чеков фото со стороны бота (6.8).

Только фото, largest file_id, лимит 5 шт на 600 с по ключу tg-receipt:{telegram_id}.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, UserAccessRequest, UserRole
from app.services.app_setting_store import _set_setting
from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import RateLimitExceeded, SlidingWindowLimiter
from app.services.user_access_requests import (
    ReceiptMustBePhoto,
    attach_receipt_from_update,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def enable_new_user_requests(db):
    _set_setting(db, "telegram_accept_access_requests", "true")
    db.commit()


@pytest.fixture()
def bound_user(db):
    user = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        telegram_id="444",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def pending_extend(db, bound_user):
    req = UserAccessRequest(
        request_type="extend_access",
        user_id=bound_user.id,
        telegram_id="444",
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def test_document_image_rejected(db, enable_new_user_requests, pending_extend):
    with pytest.raises(ReceiptMustBePhoto):
        attach_receipt_from_update(
            db,
            request_id=pending_extend.id,
            message={"document": {"mime_type": "image/jpeg"}},
            telegram_id="444",
        )


def test_photo_stores_largest_file_id(db, enable_new_user_requests, pending_extend):
    msg = {"photo": [{"file_id": "s"}, {"file_id": "L", "width": 1280}]}
    attach_receipt_from_update(
        db,
        request_id=pending_extend.id,
        message=msg,
        telegram_id="444",
    )
    db.refresh(pending_extend)
    assert pending_extend.receipt_file_id == "L"


def test_receipt_rate_limit(db, enable_new_user_requests, pending_extend, monkeypatch):
    # Изолируем модульный счётчик лимита от других тестов.
    monkeypatch.setattr(
        "app.services.user_access_requests._receipt_rate_limit",
        SlidingWindowLimiter(MemoryRateLimitBackend()),
    )
    for i in range(5):
        attach_receipt_from_update(
            db,
            request_id=pending_extend.id,
            message={"photo": [{"file_id": f"f{i}"}]},
            telegram_id="444",
        )
    with pytest.raises(RateLimitExceeded):
        attach_receipt_from_update(
            db,
            request_id=pending_extend.id,
            message={"photo": [{"file_id": "z"}]},
            telegram_id="444",
        )


def test_receipt_only_for_owner_and_pending(db, enable_new_user_requests, pending_extend):
    # Чужие telegram_id — не к этой заявке.
    with pytest.raises(ValueError):
        attach_receipt_from_update(
            db,
            request_id=pending_extend.id,
            message={"photo": [{"file_id": "f"}]},
            telegram_id="999",
        )
    # Уже решённая заявка — нельзя.
    pending_extend.status = "approved"
    pending_extend.reviewed_at = datetime.utcnow()
    db.commit()
    with pytest.raises(ValueError):
        attach_receipt_from_update(
            db,
            request_id=pending_extend.id,
            message={"photo": [{"file_id": "f"}]},
            telegram_id="444",
        )
