"""One-time tickets for SSE/WebSocket streams, where browsers cannot send an Authorization header."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.services.shared_state import pop_state, put_state

StreamName = Literal["monitoring", "warper_update", "awg2_install", "server_monitor"]
STREAM_TICKET_TTL = timedelta(seconds=30)
_NAMESPACE = "stream_ticket"


def _key(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def issue_stream_ticket(user: User, stream: StreamName) -> str:
    ticket = secrets.token_urlsafe(32)
    put_state(
        _NAMESPACE,
        _key(ticket),
        {"user_id": user.id, "stream": stream, "tv": user.token_version or 0},
        ttl=STREAM_TICKET_TTL,
    )
    return ticket


def redeem_stream_ticket(db: Session, ticket: str, stream: StreamName) -> User | None:
    if not ticket:
        return None
    data = pop_state(_NAMESPACE, _key(ticket))
    if not data or data.get("stream") != stream:
        return None
    user = db.get(User, data.get("user_id"))
    if user is None or not user.is_active:
        return None
    if int(data.get("tv") or 0) != (user.token_version or 0):
        return None
    return user


def admin_from_stream_ticket(db: Session, ticket: str, stream: StreamName) -> User:
    user = redeem_stream_ticket(db, ticket, stream)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user
