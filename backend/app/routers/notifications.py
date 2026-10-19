"""Центр уведомлений: REST-лента + SSE-поток с авторизацией через stream ticket.

Все эндпоинты админ-only. Лента и «отметить прочитанное» принимают обычный
Authorization-заголовок SPA; SSE-поток принимает разовый ticket (браузер не может
послать Authorization в query строке SSE) и шлёт событие только при изменении
снимка состояния.
"""

from __future__ import annotations

import asyncio
import json
import logging
from time import monotonic
from typing import Callable

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import SessionLocal, get_db
from app.models import User, UserAccessRequest
from app.schemas import (
    MarkReadRequest,
    MarkReadResponse,
    NotificationItem,
    NotificationsListResponse,
)
from app.services.admin_panel_notifications import (
    list_notifications_for_admin,
    mark_notifications_read,
    notifications_stream_snapshot,
)
from app.services.feature_guards import get_feature_service
from app.services.stream_ticket import admin_from_stream_ticket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_STREAM_NAME = "notifications"
_POLL_INTERVAL_SECONDS = 2.5
_HEARTBEAT_INTERVAL_SECONDS = 15

# Фабрика сессий для тиков SSE-потока. В проде — SessionLocal (живая БД),
# в тестах подменяется на тестовую sqlite-сессию через monkeypatch.
_db_session_factory: Callable[[], Session] = SessionLocal


@router.get(
    "",
    response_model=NotificationsListResponse,
    summary="Лента уведомлений для админа",
)
def get_notifications(
    category: str | None = Query(default=None, description="Фильтр по категории bell-вкладки"),
    limit: int = Query(default=50, ge=1, le=100, description="Размер страницы"),
    before_id: int | None = Query(default=None, description="id строго меньше — страница назад"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items, unread = list_notifications_for_admin(
        db, admin, category=category, limit=limit, before_id=before_id
    )
    pending = 0
    if get_feature_service().is_enabled("user_provisioning"):
        pending = (
            db.query(UserAccessRequest)
            .filter(UserAccessRequest.status == "pending")
            .count()
        )
    return {
        "items": items,
        "unread_count": unread,
        "pending_requests_count": pending,
    }


@router.post(
    "/read",
    response_model=MarkReadResponse,
    summary="Отметить уведомления прочитанными до up_to_id",
)
def post_read(
    body: MarkReadRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    mark_notifications_read(db, admin, body.up_to_id)
    return {"ok": True}


@router.get(
    "/stream",
    summary="SSE-поток уведомлений (авторизация через stream ticket)",
)
async def notifications_stream(
    request: Request,
    ticket: str = Query(..., description="Разовый ticket из POST /api/stream-ticket"),
):
    # Билет разовый: проверяем один раз при подключении на короткой сессии.
    auth_db = _db_session_factory()
    try:
        admin_from_stream_ticket(auth_db, ticket, _STREAM_NAME)
    finally:
        auth_db.close()

    async def event_generator() -> str:
        previous: str | None = None
        last_heartbeat = monotonic()
        while True:
            if await request.is_disconnected():
                break
            now = monotonic()
            if now - last_heartbeat >= _HEARTBEAT_INTERVAL_SECONDS:
                yield ": heartbeat\n\n"
                last_heartbeat = now
            db = _db_session_factory()
            try:
                snap = await asyncio.to_thread(notifications_stream_snapshot, db)
            except Exception as exc:  # тик потока не должен рвать соединение
                logger.warning("notifications stream tick failed: %s", exc)
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)}, default=str)}\n\n"
            else:
                payload = json.dumps(snap, sort_keys=True, default=str)
                if payload != previous:
                    previous = payload
                    yield f"event: update\ndata: {payload}\n\n"
            finally:
                db.close()
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
