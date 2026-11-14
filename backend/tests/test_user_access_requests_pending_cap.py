"""Pending-cap заявок: просроченные не держат очередь, уведомление не спамит."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AdminPanelNotification, UserAccessRequest
from app.services import user_access_requests as uar
from app.services.app_setting_store import _set_setting


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _enable(db, *, cap: int | None = None) -> None:
    _set_setting(db, uar.SETTING_ACCEPT_REQUESTS, "true")
    if cap is not None:
        _set_setting(db, uar.SETTING_PENDING_CAP, str(cap))
    db.commit()


def _pending(db, count: int, *, age: timedelta) -> None:
    created_at = datetime.utcnow() - age
    for index in range(count):
        db.add(
            UserAccessRequest(
                request_type=uar.REQUEST_TYPE_NEW_USER,
                telegram_id=f"tg-{age.days}-{index}",
                status="pending",
                created_at=created_at,
            )
        )
    db.commit()


def _cap_notifications(db) -> int:
    return (
        db.query(AdminPanelNotification)
        .filter(AdminPanelNotification.event_type == "access_request_cap")
        .count()
    )


def test_old_pending_requests_do_not_hold_the_cap(db):
    _enable(db)
    _pending(db, 50, age=timedelta(days=uar.PENDING_REQUEST_TTL_DAYS + 1))

    row = uar.submit_access_request(db, request_type=uar.REQUEST_TYPE_NEW_USER, telegram_id="999")

    assert row.status == "pending"
    expired = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.telegram_id.like("tg-%"), UserAccessRequest.status == "expired")
        .count()
    )
    assert expired == 50


def test_fresh_pending_requests_still_block_new_ones(db):
    _enable(db)
    _pending(db, 50, age=timedelta(minutes=5))

    with pytest.raises(uar.RequestsClosed):
        uar.submit_access_request(db, request_type=uar.REQUEST_TYPE_NEW_USER, telegram_id="999")


def test_cap_notification_is_sent_at_most_once_per_hour(db):
    _enable(db)
    _pending(db, 50, age=timedelta(minutes=5))

    with pytest.raises(uar.RequestsClosed):
        uar.submit_access_request(db, request_type=uar.REQUEST_TYPE_NEW_USER, telegram_id="999")
    with pytest.raises(uar.RequestsClosed):
        uar.submit_access_request(db, request_type=uar.REQUEST_TYPE_NEW_USER, telegram_id="998")

    assert _cap_notifications(db) == 1

    _set_setting(
        db,
        uar.CAP_NOTIFIED_AT_SETTING,
        (datetime.utcnow() - timedelta(hours=2)).isoformat(),
    )
    db.commit()

    with pytest.raises(uar.RequestsClosed):
        uar.submit_access_request(db, request_type=uar.REQUEST_TYPE_NEW_USER, telegram_id="997")

    assert _cap_notifications(db) == 2
