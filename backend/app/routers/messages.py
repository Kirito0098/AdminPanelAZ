"""Админский API чата с абонентами (модуль user_messaging)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
    rows = chat.list_messages(db, user_id=user_id, limit=limit, before_id=before_id)
    return [
        UserMessageOut(
            id=row.id,
            direction=row.direction,
            admin_id=row.admin_id,
            text=row.text,
            created_at=row.created_at,
            read_by_admin_at=row.read_by_admin_at,
            attachment_url=(
                f"/messages/{user_id}/{row.id}/attachment" if row.attachment_file_id else None
            ),
        )
        for row in rows
    ]


@router.get("/{user_id}/{message_id}/attachment")
def get_message_attachment(
    user_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Фото из переписки (чек): скачивание из Telegram и перекодировка в памяти."""
    from app.models import UserMessage
    from app.services.app_setting_store import _get_setting
    from app.services.request_receipt_preview import (
        ReceiptDecodeError,
        build_receipt_preview_jpeg,
    )

    row = db.get(UserMessage, message_id)
    if row is None or row.user_id != user_id or not row.attachment_file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Вложение не найдено")
    token = (_get_setting(db, "telegram_bot_token", "") or "").strip()
    try:
        data = build_receipt_preview_jpeg(row.attachment_file_id, token)
    except ReceiptDecodeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Не удалось открыть фото"
        )
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


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
