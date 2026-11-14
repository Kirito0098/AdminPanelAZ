"""Mini App: чат абонент ↔ администратор (модуль user_messaging).

Абонент видит только свой диалог и отвечает в нём; админ получает список
диалогов и отвечает от лица панели. Хранилище — ``user_messages``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_tg_mini_user, require_tg_mini_admin
from app.database import get_db
from app.models import User, UserMessage
from app.schemas import (
    MessageThreadOut,
    SendMessageRequest,
    SendMessageResult,
    UserMessageOut,
)
from app.services import user_messages as chat
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.user_message_notify import notify_admins_new_message


def _require_user_messaging() -> None:
    if not get_feature_service().is_enabled("user_messaging"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("user_messaging"),
        )


router = APIRouter(dependencies=[Depends(_require_user_messaging)])


def _message_out(user_id: int, row: UserMessage) -> UserMessageOut:
    return UserMessageOut(
        id=row.id,
        direction=row.direction,
        admin_id=row.admin_id,
        text=row.text,
        created_at=row.created_at,
        read_by_admin_at=row.read_by_admin_at,
        read_by_user_at=row.read_by_user_at,
        attachment_url=(
            f"/messages/{user_id}/{row.id}/attachment" if row.attachment_file_id else None
        ),
    )


# --- Абонент: свой диалог ---


@router.get("/me/messages", response_model=list[UserMessageOut])
def my_messages(
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
    user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    """Лента своего диалога; `before_id` — подгрузка более ранних сообщений."""
    rows = chat.list_messages(db, user_id=user.id, limit=limit, before_id=before_id)
    return [_message_out(user.id, row) for row in rows]


@router.post("/me/messages", response_model=UserMessageOut)
async def send_my_message(
    payload: SendMessageRequest,
    user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    """Сообщение администратору: сохраняем и уведомляем админов."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустое сообщение")
    if len(text) > chat.MESSAGE_MAX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Текст длиннее {chat.MESSAGE_MAX_LEN} символов",
        )
    stored = chat.record_inbound(db, user=user, text=text, telegram_message_id=None)
    first_in_thread = chat.unread_for_user(db, user_id=user.id) == 1
    await notify_admins_new_message(
        db, user=user, message=stored, first_in_thread=first_in_thread
    )
    return _message_out(user.id, stored)


@router.get("/me/messages/unread")
def my_unread_count(
    user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    return {"count": chat.unread_for_user_side(db, user_id=user.id)}


@router.post("/me/messages/read")
def mark_my_messages_read(
    user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    return {"marked": chat.mark_read_by_user(db, user_id=user.id)}


# --- Админ: диалоги и ответы ---


@router.get("/messages/threads", response_model=list[MessageThreadOut])
def list_threads(
    q: str | None = Query(default=None, max_length=64),
    unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_tg_mini_admin),
):
    """Диалоги: последнее сообщение и число непрочитанных, новые сверху."""
    rows = chat.list_threads(db, query=q, unread_only=unread, limit=limit, offset=offset)
    return [MessageThreadOut(**row) for row in rows]


@router.get("/messages/unread-count")
def total_unread(
    db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)
) -> dict[str, int]:
    return {"count": chat.unread_total(db)}


@router.get("/messages/{user_id}", response_model=list[UserMessageOut])
def admin_messages(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_tg_mini_admin),
):
    """Лента диалога абонента; открытие помечает ответы админа прочитанными."""
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    rows = chat.list_messages(db, user_id=user_id, limit=limit, before_id=before_id)
    result = [_message_out(user_id, row) for row in rows]
    chat.mark_read(db, user_id=user_id)
    return result


@router.post("/messages/{user_id}", response_model=SendMessageResult)
def reply_to_user(
    user_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_tg_mini_admin),
):
    """Ответ абоненту: сохраняем всегда, доставка в Telegram — best-effort."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    limit = chat.MESSAGE_MAX_LEN - len(chat.REPLY_PREFIX) - 1
    if len(payload.text) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
