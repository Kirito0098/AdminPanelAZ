"""A user portal link works only while its user is active and does not reveal the internal user id."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserPortalToken, UserRole
from app.services import client_portal as portal


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user_link(db, *, active: bool) -> UserPortalToken:
    user = User(username="bob", password_hash="x", role=UserRole.user, is_active=active)
    db.add(user)
    db.commit()
    row = UserPortalToken(token="u_link", user_id=user.id)
    db.add(row)
    db.commit()
    return row


def test_link_of_active_user_resolves(db):
    row = _user_link(db, active=True)

    resolved = portal.get_valid_portal_token(db, "u_link")

    assert resolved.kind == "user" and resolved.user_row.id == row.id


def test_link_of_deactivated_user_is_refused(db):
    _user_link(db, active=False)

    with pytest.raises(HTTPException) as exc:
        portal.get_valid_portal_token(db, "u_link")

    assert exc.value.status_code == 403


def test_user_portal_payload_has_no_user_id(db):
    row = _user_link(db, active=True)

    with patch("app.services.client_portal.resolve_portal_base_url", return_value="https://sub.example.com"):
        payload = portal.build_user_portal_payload(db, row)

    assert payload["kind"] == "user"
    assert "user_id" not in payload
