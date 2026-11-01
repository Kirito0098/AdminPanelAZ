"""Админский API чата с абонентами (модуль user_messaging)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    MessageThreadOut,
    SendMessageRequest,
    SendMessageResult,
    UserMessageOut,
)
from app.services import user_messages as chat

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/threads", response_model=list[MessageThreadOut])
def list_threads(
    q: str | None = Query(default=None, max_length=64),
    unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Диалоги: последнее сообщение и число непрочитанных, новые сверху."""
    rows = chat.list_threads(db, query=q, unread_only=unread, limit=limit, offset=offset)
    return [MessageThreadOut(**row) for row in rows]


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> dict[str, int]:
    return {"count": chat.unread_total(db)}


@router.get("/{user_id}/unread")
def unread_for_user(
    user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> dict[str, int]:
    """Счётчик непрочитанных по одному абоненту (бейдж на вкладке «Чат»)."""
    return {"count": chat.unread_for_user(db, user_id=user_id)}


@router.get("/{user_id}", response_model=list[UserMessageOut])
def list_messages(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Лента диалога; `before_id` — подгрузка более ранних сообщений."""
    return chat.list_messages(db, user_id=user_id, limit=limit, before_id=before_id)


@router.post("/{user_id}/read")
def mark_read(
    user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> dict[str, int]:
    return {"marked": chat.mark_read(db, user_id=user_id)}


@router.post("/{user_id}", response_model=SendMessageResult)
def send_message_to_user(
    user_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Ответ абоненту: сохраняем всегда, доставка в Telegram — best-effort."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    # Префикс «Сообщение от администратора:» тоже уходит в Telegram — учитываем лимит.
    limit = chat.MESSAGE_MAX_LEN - len(chat.REPLY_PREFIX) - 1
    if len(payload.text) > limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Текст длиннее {limit} символов — не поместится в сообщение Telegram",
        )
    message, delivered, warning = chat.send_admin_reply(
        db, user=user, admin=admin, text=payload.text
    )
    return SendMessageResult(
        message=UserMessageOut.model_validate(message),
        delivered=delivered,
        warning=warning,
    )
