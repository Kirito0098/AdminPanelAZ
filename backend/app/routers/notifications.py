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
from datetime import datetime, timezone
from time import monotonic
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import SessionLocal, get_db
from app.models import BELL_NOTIFY_CATEGORIES, User, UserAccessRequest
from app.schemas import (
    MarkReadRequest,
    MarkReadResponse,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    NotificationStateResponse,
    NotificationStateUpdate,
    NotificationsListResponse,
)
from app.services.admin_panel_notifications import (
    _UNSET,
    list_notifications_for_admin,
    mark_notifications_read,
    notifications_stream_snapshot,
    set_notification_state,
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
    category: str | None = Query(default=None, description="Фильтр по категории"),
    level: Literal["info", "warning", "error"] | None = Query(default=None, description="Фильтр по уровню"),
    unread_only: bool = Query(default=False, description="Только непрочитанные"),
    q: str | None = Query(default=None, max_length=100, description="Поиск по заголовку и тексту"),
    hidden_only: bool = Query(default=False, description="Только скрытые"),
    limit: int = Query(default=50, ge=1, le=100, description="Размер страницы"),
    before_id: int | None = Query(default=None, description="id строго меньше — страница назад"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items, unread, counts = list_notifications_for_admin(
        db,
        admin,
        category=category,
        level=level,
        unread_only=unread_only,
        q=q,
        hidden_only=hidden_only,
        before_id=before_id,
        limit=limit,
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
        "counts": counts,
    }


@router.get(
    "/preferences",
    response_model=NotificationPreferences,
    summary="Подписка админа на категории уведомлений",
)
def get_notification_preferences(admin: User = Depends(require_admin)):
    return {"categories": admin.bell_categories()}


@router.put(
    "/preferences",
    response_model=NotificationPreferences,
    summary="Сохранить подписку на категории уведомлений",
)
def put_notification_preferences(
    body: NotificationPreferencesUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    unknown = set(body.categories) - set(BELL_NOTIFY_CATEGORIES)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестные категории: {', '.join(sorted(unknown))}",
        )
    admin.bell_notify_categories = json.dumps(
        {key: bool(body.categories.get(key, True)) for key in BELL_NOTIFY_CATEGORIES},
        ensure_ascii=False,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return {"categories": admin.bell_categories()}


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


@router.post(
    "/{notification_id}/state",
    response_model=NotificationStateResponse,
    summary="Личное состояние уведомления: прочитано / скрыто / отложено",
)
def post_notification_state(
    notification_id: int,
    body: NotificationStateUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snoozed_until: object = _UNSET
    if "snoozed_until" in body.model_fields_set:
        snoozed_until = None
        if body.snoozed_until is not None:
            value = body.snoozed_until
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            if value <= datetime.utcnow():
                raise HTTPException(
                    status_code=422, detail="Срок откладывания должен быть в будущем"
                )
            snoozed_until = value
    state = set_notification_state(
        db,
        admin,
        notification_id,
        read=body.read,
        hidden=body.hidden,
        snoozed_until=snoozed_until,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    return {"state": state}


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
