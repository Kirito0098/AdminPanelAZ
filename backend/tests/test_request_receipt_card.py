"""Чек по заявке: админам уходит фото-карточка вместо текстовой."""

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import UserAccessRequest
from app.services import user_access_requests as uar


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


def _request(db, receipt="file-1"):
    req = UserAccessRequest(
        request_type="extend_access",
        telegram_id="555",
        requested_count=1,
        status="pending",
        receipt_file_id=receipt,
        admin_message_refs=json.dumps([{"chat_id": "777", "message_id": 10}]),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def test_receipt_card_replaces_text_card(db, monkeypatch):
    req = _request(db)
    calls: list[tuple[str, dict]] = []

    async def _fake(token, method, *, payload=None):
        calls.append((method, payload))
        if method == "sendPhoto":
            return {"message_id": 42}
        return {}

    monkeypatch.setattr(uar.telegram_api, "call_bot_api", _fake)
    monkeypatch.setattr(uar, "_bot_token", lambda db: "tok")

    asyncio.run(uar.send_receipt_card_to_admins(db, req))

    assert [method for method, _ in calls] == ["sendPhoto", "deleteMessage"]
    assert calls[0][1]["photo"] == "file-1"
    assert calls[0][1]["reply_markup"] is not None
    db.refresh(req)
    assert json.loads(req.admin_message_refs) == [{"chat_id": "777", "message_id": 42}]


def test_receipt_marker_in_admin_text(db):
    req = _request(db)

    assert "Чек: приложен" in uar._admin_request_text(db, req)
