"""Telegram bot: заявки на доступ (Task 10) и приём чеков (Task 11).

Все взаимодействия — только в личном чате (chat.id == from.id). Карточки заявок
отправляются только в личные чаты админов (их telegram_id), callback_data —
только id заявки (ar:a:{id}, ar:r:{id}, ar:e30:{id}, ar:e60:{id}, ar:ec:{id}),
никогда ссылки на портал.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User, UserAccessRequest
from app.services.rate_limit.sliding_window import RateLimitExceeded
from app.services.telegram_api import answer_callback_query, edit_message_reply_markup, send_message
from app.services.telegram_bot_handlers.base import BotContext, is_admin
from app.services import telegram_bot_i18n as i18n
from app.services.user_access_requests import (
    AlreadyDecided,
    AlreadyPending,
    NotBound,
    ReceiptMustBePhoto,
    RequestsClosed,
    TelegramAlreadyBound,
    approve_request,
    attach_receipt_from_update,
    reject_request,
    submit_access_request,
    sync_admin_request_messages,
)

SETTING_BOT_TOKEN = "telegram_bot_token"


async def _tg_answer(bot_token: str, callback_id: str, **kwargs: object) -> None:
    """Ответить на callback_query; ошибки Telegram (повторный ответ) не критичны."""
    if not callback_id:
        return
    try:
        await answer_callback_query(bot_token, callback_id, **kwargs)
    except Exception:
        pass


async def handle_request_access(ctx: BotContext) -> None:
    """«Запросить доступ» — новая заявка new_user (только если приём включён)."""
    try:
        submit_access_request(
            ctx.db,
            request_type="new_user",
            telegram_id=ctx.telegram_user_id,
            telegram_username=None,
            telegram_name=None,
        )
    except RequestsClosed as exc:
        await send_message(ctx.bot_token, ctx.chat_id, str(exc) or i18n.REQUESTS_CLOSED)
        return
    except AlreadyPending as exc:
        await send_message(ctx.bot_token, ctx.chat_id, str(exc))
        return
    await send_message(ctx.bot_token, ctx.chat_id, i18n.REQUEST_SUBMITTED)


async def handle_request_more_config(ctx: BotContext) -> None:
    """«Запросить ещё конфиг» — заявка add_config от привязанного пользователя."""
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.UNLINKED)
        return
    try:
        submit_access_request(
            ctx.db,
            request_type="add_config",
            telegram_id=ctx.telegram_user_id,
            user_id=ctx.user.id,
            requested_count=1,
        )
    except RequestsClosed as exc:
        await send_message(ctx.bot_token, ctx.chat_id, str(exc) or i18n.REQUESTS_CLOSED)
        return
    except AlreadyPending as exc:
        await send_message(ctx.bot_token, ctx.chat_id, str(exc))
        return
    except NotBound:
        await send_message(ctx.bot_token, ctx.chat_id, "Ваш Telegram не привязан к пользователю панели.")
        return
    await send_message(ctx.bot_token, ctx.chat_id, i18n.REQUEST_MORE_SUBMITTED)


async def handle_link_code(ctx: BotContext) -> None:
    """«У меня есть код привязки» — подсказка /link <код>."""
    await send_message(ctx.bot_token, ctx.chat_id, i18n.REQUEST_LINK_HINT)


async def handle_request_photo(ctx: BotContext, message: dict) -> bool:
    """Фото от пользователя — приложить как чек к его pending-заявке. True — обработано."""
    req = (
        ctx.db.query(UserAccessRequest)
        .filter(
            UserAccessRequest.telegram_id == ctx.telegram_user_id,
            UserAccessRequest.status == "pending",
        )
        .order_by(UserAccessRequest.id.desc())
        .first()
    )
    if req is None:
        return False
    try:
        attach_receipt_from_update(
            ctx.db,
            request_id=req.id,
            message=message,
            telegram_id=ctx.telegram_user_id,
        )
    except ReceiptMustBePhoto:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.RECEIPT_NOT_PHOTO)
        return True
    except RateLimitExceeded as exc:
        await send_message(ctx.bot_token, ctx.chat_id, exc.detail)
        return True
    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, str(exc))
        return True
    await send_message(ctx.bot_token, ctx.chat_id, i18n.REQUEST_RECEIPT_OK)
    return True


async def handle_request_document(ctx: BotContext, message: dict) -> bool:
    """Документ вместо чека у пользователя с pending-заявкой — нейтральный ответ."""
    req = (
        ctx.db.query(UserAccessRequest)
        .filter(
            UserAccessRequest.telegram_id == ctx.telegram_user_id,
            UserAccessRequest.status == "pending",
        )
        .order_by(UserAccessRequest.id.desc())
        .first()
    )
    if req is None:
        return False
    await send_message(ctx.bot_token, ctx.chat_id, i18n.RECEIPT_NOT_PHOTO)
    return True


async def handle_admin_request_callback(
    ctx: BotContext,
    data: str,
    *,
    message_id: int | None,
    callback_id: str = "",
) -> bool:
    """Админские callback по заявке: ar:a:{id} / ar:r:{id} / ar:e30:{id} / ar:e60:{id} / ar:ec:{id}."""
    if not data.startswith("ar:"):
        return False
    if not is_admin(ctx.user):
        await _tg_answer(ctx.bot_token, callback_id, text=i18n.ADMIN_NO_RIGHTS, show_alert=True)
        return True
    parts = data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        return True
    action, request_id = parts[1], int(parts[2])
    db: Session = ctx.db
    admin: User = ctx.user
    request = db.get(UserAccessRequest, request_id)
    if request is None or request.status != "pending":
        if message_id is not None:
            await edit_message_reply_markup(
                ctx.bot_token, ctx.chat_id, message_id, reply_markup={"inline_keyboard": []}
            )
        await _tg_answer(ctx.bot_token, callback_id, text=i18n.REQUEST_ALREADY_DECIDED, show_alert=True)
        return True

    try:
        if action == "a":
            if request.request_type == "new_user":
                from app.services.user_access_requests import _default_preset_id

                preset_id = _default_preset_id(db)
                if preset_id is None:
                    await send_message(
                        ctx.bot_token,
                        ctx.chat_id,
                        i18n.REQUEST_OPEN_IN_PANEL.format(request_id=request_id),
                    )
                    await _tg_answer(ctx.bot_token, callback_id)
                    return True
                approve_request(db, request_id=request_id, admin=admin, preset_id=preset_id)
            elif request.request_type == "add_config":
                approve_request(
                    db,
                    request_id=request_id,
                    admin=admin,
                    ad_hoc={"count": max(1, int(request.requested_count or 1))},
                )
            else:
                await _tg_answer(
                    ctx.bot_token, callback_id, text="Это заявка не на выдачу конфига", show_alert=True
                )
                return True
        elif action == "r":
            reject_request(db, request_id=request_id, admin=admin)
        elif action in ("e30", "e60"):
            if request.request_type != "extend_access":
                await _tg_answer(
                    ctx.bot_token, callback_id, text="Это заявка не на продление", show_alert=True
                )
                return True
            approve_request(
                db,
                request_id=request_id,
                admin=admin,
                ad_hoc={"days": 30 if action == "e30" else 60},
            )
        elif action == "ec":
            await send_message(ctx.bot_token, ctx.chat_id, i18n.REQUEST_EXTEND_CUSTOM_TEXT)
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                i18n.REQUEST_OPEN_IN_PANEL.format(request_id=request_id),
            )
            await _tg_answer(ctx.bot_token, callback_id)
            return True
        else:
            return True
    except AlreadyDecided:
        if message_id is not None:
            await edit_message_reply_markup(
                ctx.bot_token, ctx.chat_id, message_id, reply_markup={"inline_keyboard": []}
            )
        await _tg_answer(ctx.bot_token, callback_id, text=i18n.REQUEST_ALREADY_DECIDED, show_alert=True)
        return True
    except TelegramAlreadyBound as exc:
        # E1: администратору — чёткий admin_detail (и только ему), заявляющему — нейтральный текст.
        await _tg_answer(ctx.bot_token, callback_id, text=exc.admin_detail, show_alert=True)
        try:
            await send_message(ctx.bot_token, str(request.telegram_id), i18n.REQUEST_E1)
        except Exception:  # уведомление requester'а не ломает решение
            pass
        return True
    except ValueError as exc:
        await _tg_answer(ctx.bot_token, callback_id, text=str(exc), show_alert=True)
        return True

    # Решение зафиксировано — обновить карточки у всех админов (убрать клавиатуру).
    approved = action in ("a", "e30", "e60")
    text = (
        i18n.ADMIN_REQUEST_APPROVED.format(admin=admin.username)
        if approved
        else i18n.ADMIN_REQUEST_REJECTED.format(admin=admin.username)
    )
    await sync_admin_request_messages(db, request, text=text)
    await answer_callback_query(ctx.bot_token, callback_id)
    return True
