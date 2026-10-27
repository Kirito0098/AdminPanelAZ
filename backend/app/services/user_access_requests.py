"""Access requests: submit + anti-abuse (D8), approve/reject race, approval→delivery (D12).

Подача заявок, защита от злоупотреблений, rozw争议 حل через условие
pending→approved и единая доставка «Доступ одобрен» в личный чат requester'а.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from html import escape
from time import monotonic
from typing import Any

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.models import (
    ProvisioningPreset,
    TelegramRequestBan,
    TelegramUserArchive,
    User,
    UserAccessRequest,
    UserNodeAssignment,
    UserRole,
    VpnType,
)
from app.services.admin_panel_notifications import write_admin_panel_notification
from app.services.app_setting_store import _get_setting, _set_setting
from app.auth import get_password_hash
from app.services.feature_guards import get_feature_service
from app.services.client_portal import get_or_create_user_portal_token, user_link_response
from app.services.rate_limit.backends import MemoryRateLimitBackend
from app.services.rate_limit.sliding_window import SlidingWindowLimiter
from app.services.telegram import send_tg_message
from app.services import telegram_api
from app.services.telegram_api import edit_message_text, send_message
from app.services.user_provisioning import enqueue_user_provision, validate_plan_nodes

logger = logging.getLogger(__name__)

REQUEST_TYPE_NEW_USER = "new_user"
REQUEST_TYPE_ADD_CONFIG = "add_config"
REQUEST_TYPE_EXTEND = "extend_access"

REQUEST_TYPES = (REQUEST_TYPE_NEW_USER, REQUEST_TYPE_ADD_CONFIG, REQUEST_TYPE_EXTEND)

REQUEST_TYPE_LABELS: dict[str, str] = {
    REQUEST_TYPE_NEW_USER: "новый пользователь",
    REQUEST_TYPE_ADD_CONFIG: "дополнительный конфиг",
    REQUEST_TYPE_EXTEND: "продление доступа",
}

SETTING_ACCEPT_REQUESTS = "telegram_accept_access_requests"
SETTING_PENDING_CAP = "telegram_new_user_request_pending_cap"
SETTING_BOT_TOKEN = "telegram_bot_token"

COOLDOWN_HOURS = 24
TELEGRAM_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{5,32}$")

# Приём чеков (Task 11): фото только, лимит 5 шт на 600 с.
_RECEIPT_LIMIT = 5
_RECEIPT_WINDOW_SECONDS = 600
_receipt_rate_limit = SlidingWindowLimiter(MemoryRateLimitBackend())


class RequestError(Exception):
    """Базовая доменная ошибка заявки."""


class RequestsClosed(RequestError):
    """Приём заявок закрыт (настройкой, лимитом или блокировкой)."""


class AlreadyPending(RequestError):
    """У requester'а уже есть pending-заявка этого типа."""


class AlreadyHasAccess(RequestError):
    """Telegram уже привязан к аккаунту: заявка new_user не нужна (устаревшая кнопка)."""


class CooldownActive(RequestError):
    """После отказа можно подать заново не ранее чем через 24 ч."""


class Banned(RequestError):
    """telegram_id заблокирован админом."""


class NotBound(RequestError):
    """Telegram не привязан к пользователю (требуется для add_config / extend_access)."""


class AlreadyDecided(RequestError):
    """Заявка уже одобрена или отклонена (проигравшая сторона гонки)."""


class TelegramAlreadyBound(RequestError):
    """telegram_id уже привязан к другому пользователю (admin-only текст)."""

    def __init__(self, admin_detail: str, user_id: int, username: str):
        super().__init__(admin_detail)
        self.admin_detail = admin_detail
        self.user_id = user_id
        self.username = username


class ReceiptMustBePhoto(RequestError):
    """Пользователь прислал не фото (документ/файл) вместо чека."""


def _accept_requests(db: Session) -> bool:
    return _get_setting(db, SETTING_ACCEPT_REQUESTS, "false").strip().lower() == "true"


def _pending_cap(db: Session) -> int:
    raw = _get_setting(db, SETTING_PENDING_CAP, "50").strip()
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 50


def _is_bound(db: Session, telegram_id: str) -> User | None:
    return (
        db.query(User)
        .filter(User.telegram_id == telegram_id, User.provision_state != "pending_deletion")
        .first()
    )


def _login_is_free(db: Session, username: str) -> bool:
    return (
        db.query(User)
        .filter(User.username == username, User.provision_state != "pending_deletion")
        .first()
        is None
    )


def _propose_login(db: Session, telegram_username: str | None, telegram_id: str) -> str:
    if telegram_username and TELEGRAM_USERNAME_RE.fullmatch(telegram_username) and _login_is_free(db, telegram_username):
        return telegram_username
    return f"tg{telegram_id}"


def _requester_label(
    telegram_name: str | None,
    telegram_username: str | None,
    telegram_id: str,
) -> str:
    """«Иван · @ivan · ID 123» для ленты уведомлений (без HTML)."""
    parts: list[str] = []
    if telegram_name:
        parts.append(telegram_name.strip())
    if telegram_username:
        parts.append(f"@{telegram_username.strip()}")
    parts.append(f"ID {telegram_id}")
    return " · ".join(parts)


def submit_access_request(
    db: Session,
    *,
    request_type: str,
    telegram_id: str,
    telegram_username: str | None = None,
    telegram_name: str | None = None,
    user_id: int | None = None,
    requested_count: int = 1,
    user_note: str | None = None,
    receipt_file_id: str | None = None,
) -> UserAccessRequest:
    """Создать заявку на доступ с защитой от злоупотреблений (D8).

    Raises: RequestsClosed, AlreadyPending, CooldownActive, Banned, NotBound.
    """
    if request_type not in REQUEST_TYPES:
        raise ValueError(f"Неизвестный тип заявки: {request_type}")
    telegram_id = str(telegram_id).strip()
    # Профиль из Telegram: подрезаем под размеры колонок (64 / 128).
    telegram_username = (telegram_username or "").strip().lstrip("@")[:64] or None
    telegram_name = (telegram_name or "").strip()[:128] or None

    if request_type == REQUEST_TYPE_NEW_USER:
        # Telegram уже привязан к активному абоненту — доступ есть. Так бывает, когда
        # после одобрения в чате осталась старая клавиатура «Запросить доступ»:
        # повторная заявка не создаётся, пользователю возвращается меню абонента.
        bound = _is_bound(db, telegram_id)
        if bound is not None and bound.is_active:
            raise AlreadyHasAccess(
                "У вас уже есть доступ. Нужно ещё устройство — нажмите «Запросить ещё конфиг»."
            )
        # Новые пользователи из Telegram по умолчанию не принимаются.
        if not _accept_requests(db):
            raise RequestsClosed("Приём заявок временно закрыт")
        # Баннные получают тот же нейтральный ответ, что и лимит.
        ban = (
            db.query(TelegramRequestBan)
            .filter(TelegramRequestBan.telegram_id == telegram_id)
            .first()
        )
        if ban is not None:
            raise Banned("Приём заявок временно закрыт")
        # Глобальный лимит pending new_user заявок.
        pending_count = (
            db.query(UserAccessRequest)
            .filter(
                UserAccessRequest.request_type == REQUEST_TYPE_NEW_USER,
                UserAccessRequest.status == "pending",
            )
            .count()
        )
        if pending_count >= _pending_cap(db):
            raise RequestsClosed("Приём заявок временно закрыт")

    # Один pending на (telegram_id, request_type) — частичный уникальный индекс.
    existing = (
        db.query(UserAccessRequest)
        .filter(
            UserAccessRequest.telegram_id == telegram_id,
            UserAccessRequest.request_type == request_type,
            UserAccessRequest.status == "pending",
        )
        .first()
    )
    if existing is not None:
        raise AlreadyPending("У вас уже есть заявка в ожидании рассмотрения")

    # Кулдаун 24 ч после отказа того же типа.
    last_rejected = (
        db.query(UserAccessRequest)
        .filter(
            UserAccessRequest.telegram_id == telegram_id,
            UserAccessRequest.request_type == request_type,
            UserAccessRequest.status == "rejected",
            UserAccessRequest.reviewed_at.isnot(None),
        )
        .order_by(UserAccessRequest.reviewed_at.desc())
        .first()
    )
    if last_rejected is not None and last_rejected.reviewed_at is not None:
        if datetime.utcnow() - last_rejected.reviewed_at < timedelta(hours=COOLDOWN_HOURS):
            raise CooldownActive(
                "Подать заявку повторно можно не ранее чем через 24 часа после отказа"
            )

    # add_config / extend_access только от привязанного Telegram-аккаунта.
    if request_type in (REQUEST_TYPE_ADD_CONFIG, REQUEST_TYPE_EXTEND):
        user = db.get(User, user_id) if user_id is not None else None
        if user is None or (user.telegram_id or "").strip() != telegram_id:
            raise NotBound("Telegram не привязан к этому пользователю")

    row = UserAccessRequest(
        request_type=request_type,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        telegram_name=telegram_name,
        user_id=user_id,
        requested_count=requested_count,
        user_note=user_note,
        receipt_file_id=receipt_file_id,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Колокол в панели (всегда пишется, даже когда Telegram выключен).
    write_admin_panel_notification(
        db,
        event_type=f"access_request_{request_type}",
        title=f"Новая заявка на доступ: {REQUEST_TYPE_LABELS[request_type]}",
        message=_requester_label(telegram_name, telegram_username, telegram_id),
        action_payload={"request_id": row.id, "request_type": request_type},
    )
    # Админы — только в личные чаты (telegram_id), никогда не в telegram_chat_id (группа).
    _notify_admins_new_request(db, row)
    return row


def _bot_token(db: Session) -> str:
    return _get_setting(db, SETTING_BOT_TOKEN, "").strip()


def _default_preset_id(db: Session) -> int | None:
    preset = (
        db.query(ProvisioningPreset)
        .filter(ProvisioningPreset.is_default.is_(True))
        .first()
    )
    return preset.id if preset is not None else None


def _admin_request_keyboard(db: Session, request: UserAccessRequest) -> dict[str, Any] | None:
    """Клавиатура под карточкой заявки для админа. Только callback_data id — без ссылок в кнопках."""
    from app.services import telegram_bot_i18n as i18n
    from app.services.telegram_bot_handlers.base import inline_button, inline_keyboard

    rid = request.id
    rows: list[list[dict[str, str]]] = []
    if request.request_type == REQUEST_TYPE_NEW_USER:
        # «Одобрить» одним кликом возможно только с шаблоном по умолчанию.
        # Без шаблона всё равно показываем кнопку («Настроить»), иначе админу
        # остаётся только «Отклонить» и заявку негде принять.
        label = (
            i18n.BTN_REQUEST_APPROVE
            if _default_preset_id(db) is not None
            else i18n.BTN_REQUEST_CONFIGURE
        )
        rows.append([inline_button(label, callback_data=f"ar:a:{rid}")])
        rows.append([inline_button(i18n.BTN_REQUEST_REJECT, callback_data=f"ar:r:{rid}")])
    elif request.request_type == REQUEST_TYPE_ADD_CONFIG:
        rows.append([inline_button(i18n.BTN_REQUEST_APPROVE_MORE, callback_data=f"ar:a:{rid}")])
        rows.append([inline_button(i18n.BTN_REQUEST_REJECT, callback_data=f"ar:r:{rid}")])
    elif request.request_type == REQUEST_TYPE_EXTEND:
        rows.append(
            [
                inline_button(i18n.BTN_REQUEST_EXTEND_30, callback_data=f"ar:e30:{rid}"),
                inline_button(i18n.BTN_REQUEST_EXTEND_60, callback_data=f"ar:e60:{rid}"),
            ]
        )
        rows.append([inline_button(i18n.BTN_REQUEST_EXTEND_CUSTOM, callback_data=f"ar:ec:{rid}")])
        rows.append([inline_button(i18n.BTN_REQUEST_REJECT, callback_data=f"ar:r:{rid}")])
    if not rows:
        return None
    return inline_keyboard(rows)


def _run_async(coro) -> Any:
    """Запустить корутину синхронно, не блокируя рабочий цикл бота."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Синхронный endpoint (FastAPI threadpool): у каждого asyncio.run свой
        # event loop, поэтому общий HTTP-клиент нельзя переиспользовать между
        # вызовами — сбрасываем его до и после.
        telegram_api.reset_bot_api_client_for_tests()
        try:
            return asyncio.run(coro)
        finally:
            telegram_api.reset_bot_api_client_for_tests()
    # В потоке бота цикл уже крутится — выполняем в auxiliar-потоке со своим циклом,
    # чтобы общий HTTP-клиент не привязался к чужому event loop.
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            telegram_api.reset_bot_api_client_for_tests()
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # нет права падать при уведомлении
            box["exc"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=30)
    if "exc" in box:
        raise box["exc"]
    return box.get("value")


def _admin_request_text(db: Session, request: UserAccessRequest) -> str:
    """Текст карточки заявки для админа (HTML). Общий для отправки и обновления."""
    history = format_requester_history(db, request.telegram_id)
    type_label = REQUEST_TYPE_LABELS.get(request.request_type, request.request_type)
    lines = [f"<b>Заявка на доступ</b>: {escape(type_label, quote=False)}"]
    if request.user_id:
        bound = db.get(User, request.user_id)
        if bound is not None:
            lines.append(f"Абонент: <code>{escape(bound.username, quote=False)}</code>")
    if request.telegram_name:
        lines.append(f"Имя: {escape(request.telegram_name, quote=False)}")
    if request.telegram_username:
        lines.append(f"Ник: @{escape(request.telegram_username, quote=False)}")
    lines.append(f"Telegram ID: <code>{escape(request.telegram_id, quote=False)}</code>")
    if request.user_note:
        lines.append(f"Комментарий: {escape(request.user_note, quote=False)}")
    if history:
        lines.append(f"История: {escape(history, quote=False)}")
    return "\n".join(lines)


def _notify_admins_new_request(db: Session, request: UserAccessRequest) -> None:
    bot_token = _bot_token(db)
    if not bot_token or not get_feature_service().is_enabled("telegram"):
        return
    admins = (
        db.query(User)
        .filter(User.role == UserRole.admin, User.is_active.is_(True), User.telegram_id.isnot(None))
        .all()
    )
    if not admins:
        return
    text = _admin_request_text(db, request)
    keyboard = _admin_request_keyboard(db, request)
    refs: list[dict[str, Any]] = []
    for admin in admins:
        chat_id = str(admin.telegram_id)
        try:
            if request.receipt_file_id:
                result = _run_async(
                    telegram_api.send_photo(
                        bot_token,
                        chat_id,
                        request.receipt_file_id,
                        caption=text,
                        reply_markup=keyboard,
                    )
                )
            else:
                payload: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                }
                if keyboard is not None:
                    payload["reply_markup"] = keyboard
                result = _run_async(telegram_api.call_bot_api(bot_token, "sendMessage", payload=payload))
        except Exception as exc:  # никогда не блокирует подачу
            logger.warning("new request card to admin %s failed: %s", admin.id, exc)
            continue
        if isinstance(result, dict) and result.get("message_id") is not None:
            refs.append({"chat_id": chat_id, "message_id": int(result["message_id"])})
    if refs:
        request.admin_message_refs = json.dumps(refs, ensure_ascii=False)
        db.add(request)
        db.commit()


async def refresh_admin_request_card(db: Session, request: UserAccessRequest) -> None:
    """Обновить текст уже отправленных админам карточек (сохранив кнопки заявки)."""
    token = _bot_token(db)
    if not token:
        return
    refs = json.loads(request.admin_message_refs or "[]")
    if not refs:
        return
    text = _admin_request_text(db, request)
    keyboard = _admin_request_keyboard(db, request)
    for ref in refs:
        try:
            if request.receipt_file_id:
                await telegram_api.call_bot_api(
                    token,
                    "editMessageCaption",
                    payload={
                        "chat_id": str(ref["chat_id"]),
                        "message_id": int(ref["message_id"]),
                        "caption": text,
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    },
                )
            else:
                await edit_message_text(
                    token,
                    str(ref["chat_id"]),
                    int(ref["message_id"]),
                    text,
                    reply_markup=keyboard,
                )
        except Exception as exc:
            logger.warning("refresh request card %s failed: %s", ref, exc)


# Не чаще одного запроса getChat на telegram_id в 10 минут: старые заявки
# дозаполняются при первом открытии списка, неудачи не долбят Bot API.
_PROFILE_BACKFILL_TTL_SECONDS = 600
_profile_backfill_attempted: dict[str, float] = {}


def _profile_from_chat(info: dict[str, Any]) -> tuple[str | None, str | None]:
    username = str(info.get("username") or "").strip().lstrip("@")[:64] or None
    name = " ".join(
        str(part).strip()
        for part in (info.get("first_name"), info.get("last_name"))
        if part
    ).strip()[:128] or None
    return username, name


def backfill_request_profile(db: Session, request: UserAccessRequest) -> bool:
    """Дозаполнить имя/@ник заявки через Telegram ``getChat`` (старые записи).

    Нужно для заявок, созданных до того, как бот начал сохранять профиль:
    в БД у них только ``telegram_id``. Любая ошибка Telegram не ломает список.
    """
    if request.telegram_name or request.telegram_username:
        return False
    token = _bot_token(db)
    if not token or not get_feature_service().is_enabled("telegram"):
        return False
    telegram_id = str(request.telegram_id).strip()
    if not telegram_id:
        return False
    last_attempt = _profile_backfill_attempted.get(telegram_id)
    now = monotonic()
    if last_attempt is not None and now - last_attempt < _PROFILE_BACKFILL_TTL_SECONDS:
        return False
    _profile_backfill_attempted[telegram_id] = now
    try:
        info = _run_async(
            telegram_api.call_bot_api(token, "getChat", payload={"chat_id": telegram_id})
        )
    except Exception as exc:
        logger.info("telegram getChat for request %s failed: %s", request.id, exc)
        return False
    if not isinstance(info, dict):
        return False
    username, name = _profile_from_chat(info)
    if not username and not name:
        return False
    if username:
        request.telegram_username = request.telegram_username or username
    if name:
        request.telegram_name = request.telegram_name or name
    db.add(request)
    db.commit()
    db.refresh(request)
    _profile_backfill_attempted.pop(telegram_id, None)
    if request.status == "pending":
        try:
            _run_async(refresh_admin_request_card(db, request))
        except Exception as exc:
            logger.info("refresh request card %s failed: %s", request.id, exc)
    return True


def backfill_missing_request_profiles(
    db: Session,
    requests: list[UserAccessRequest],
    *,
    limit: int = 5,
) -> int:
    """Дозаполнить профили у нескольких заявок; вернуть число обновлённых."""
    updated = 0
    for request in requests:
        if updated >= limit:
            break
        if request.telegram_name or request.telegram_username:
            continue
        if backfill_request_profile(db, request):
            updated += 1
    return updated



def attach_receipt_from_update(
    db: Session,
    *,
    request_id: int,
    message: dict[str, Any],
    telegram_id: str,
) -> UserAccessRequest:
    """Прикрепить чек-фото к pending-заявке requester'а (только фото, largest file_id)."""
    photo = message.get("photo") if isinstance(message, dict) else None
    if not photo:
        raise ReceiptMustBePhoto("Пришлите чек фотографией (не файлом)")
    telegram_id = str(telegram_id).strip()
    _receipt_rate_limit.consume(
        f"tg-receipt:{telegram_id}", _RECEIPT_LIMIT, _RECEIPT_WINDOW_SECONDS,
        detail="Слишком много попыток прислать чек. Повторите позже.",
    )
    req = db.get(UserAccessRequest, int(request_id))
    if req is None:
        raise ValueError("Заявка не найдена")
    if str(req.telegram_id) != telegram_id:
        raise ValueError("Заявка не найдена")
    if req.status != "pending":
        raise ValueError("Заявка уже обработана")
    req.receipt_file_id = str(photo[-1]["file_id"])
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def format_requester_history(db: Session, telegram_id: str) -> str:
    """Админ-only сводка о telegram_id: архивные пользователи + история заявок."""
    parts: list[str] = []
    archives = (
        db.query(TelegramUserArchive)
        .filter(TelegramUserArchive.telegram_id == telegram_id)
        .order_by(TelegramUserArchive.deleted_at.desc())
        .all()
    )
    for archive in archives:
        when = ""
        if archive.created_at and archive.deleted_at:
            when = f"{archive.created_at:%d.%m}–{archive.deleted_at:%d.%m}"
        term = f" (последний срок {archive.last_term_days} дн.)" if archive.last_term_days else ""
        parts.append(f"Уже был пользователем {archive.username}{when}{term}")
    requests = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.telegram_id == telegram_id)
        .all()
    )
    approved = sum(1 for r in requests if r.status == "approved")
    rejected = sum(1 for r in requests if r.status == "rejected")
    stats: list[str] = []
    if approved:
        stats.append(f"одобрен {approved} раз(а)")
    if rejected:
        stats.append(f"отклонён {rejected} раз(а)")
    if stats:
        parts.append(" · ".join(stats))
    return " · ".join(parts)


def _resolve_plan(
    db: Session,
    request: UserAccessRequest,
    *,
    preset_id: int | None,
    ad_hoc: dict[str, Any] | None,
) -> dict[str, Any]:
    """Разрешить план заявки: из шаблона или ad-hoc параметров."""
    if request.request_type == REQUEST_TYPE_NEW_USER:
        if preset_id is not None:
            preset = db.get(ProvisioningPreset, preset_id)
            if preset is None:
                raise ValueError("Шаблон не найден")
            try:
                node_ids = json.loads(preset.node_ids or "[]")
                protocols = json.loads(preset.protocols or "[]")
            except (ValueError, TypeError):
                node_ids, protocols = [], []
            plan = {
                "node_ids": [int(n) for n in node_ids],
                "protocols": [str(p) for p in protocols],
                "config_count": preset.config_count or 1,
                "access_days": preset.access_days,
                "traffic_limit_bytes": preset.traffic_limit_bytes,
                "username": None,
            }
            # Логин/срок из формы панели поверх шаблона.
            if ad_hoc:
                if ad_hoc.get("username"):
                    plan["username"] = ad_hoc["username"]
                if ad_hoc.get("access_until") is not None:
                    plan["access_until"] = ad_hoc["access_until"]
                    plan["access_days"] = None
            return plan
        if not ad_hoc:
            raise ValueError("Укажите preset_id или параметры плана")
        node_ids = list(ad_hoc.get("node_ids") or [])
        protocols = list(ad_hoc.get("protocols") or [])
        return {
            "node_ids": [int(n) for n in node_ids],
            "protocols": [str(p) for p in protocols],
            "config_count": int(ad_hoc.get("config_count") or 1),
            "access_until": ad_hoc.get("access_until"),
            "traffic_limit_bytes": ad_hoc.get("traffic_limit_bytes"),
            "username": ad_hoc.get("username"),
        }
    if request.request_type == REQUEST_TYPE_ADD_CONFIG:
        count = int((ad_hoc or {}).get("count") or 1)
        return {"count": count}
    if request.request_type == REQUEST_TYPE_EXTEND:
        days = int((ad_hoc or {}).get("days") or 30)
        return {"days": days}
    raise ValueError(f"Неизвестный тип заявки: {request.request_type}")


def _create_user_for_request(
    db: Session,
    request: UserAccessRequest,
    plan: dict[str, Any],
    *,
    actor_username: str,
) -> User:
    """Создать пользователя по заявке new_user (вход в панель выключен, пароль случайный)."""
    username = plan.get("username") or _propose_login(db, request.telegram_username, request.telegram_id)
    if not _login_is_free(db, username):
        username = f"tg{request.telegram_id}"
        if not _login_is_free(db, username):
            username = f"tg{request.telegram_id}_{secrets.token_hex(4)}"
    config_count = int(plan.get("config_count") or 1)
    protocols = list(plan.get("protocols") or [])
    access_days = plan.get("access_days")
    access_until = plan.get("access_until")
    if access_until is None and access_days:
        access_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=int(access_days))
    traffic_limit = plan.get("traffic_limit_bytes")
    if traffic_limit is not None:
        try:
            traffic_limit = int(traffic_limit)
        except (TypeError, ValueError):
            traffic_limit = None
        if traffic_limit is not None and traffic_limit <= 0:
            traffic_limit = None
    user = User(
        username=username,
        password_hash=get_password_hash(secrets.token_urlsafe(32)),
        role=UserRole.user,
        panel_login_enabled=False,
        can_create_configs=False,
        telegram_id=request.telegram_id,
        client_base_name=username,
        plan_config_indexes=json.dumps(list(range(1, config_count + 1)), ensure_ascii=False),
        desired_protocols=json.dumps(protocols, ensure_ascii=False),
        access_until=access_until,
        provision_state="unmanaged",
        traffic_limit_bytes=traffic_limit,
        traffic_counter_reset_at=datetime.utcnow() if traffic_limit is not None else None,
    )
    db.add(user)
    db.flush()
    nodes = validate_plan_nodes(db, plan["node_ids"])
    for node in nodes:
        db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
    db.commit()
    db.refresh(user)
    return user


def approve_request(
    db: Session,
    *,
    request_id: int,
    admin: User,
    preset_id: int | None = None,
    ad_hoc: dict[str, Any] | None = None,
) -> UserAccessRequest | None:
    """Одобрить заявку.

    Сначала условный claim pending→approved (гонка → AlreadyDecided), затем
    побочные эффекты. Для new_user: привязка Telegram → TelegramAlreadyBound;
    после создания пользователя пишется ``request.user_id`` (нужно для
    ``maybe_send_delivery_after_task``).
    """
    request = db.get(UserAccessRequest, request_id)
    if request is None:
        return None
    if request.status != "pending":
        raise AlreadyDecided("Заявка уже обработана")

    plan: dict[str, Any] | None = None
    user: User | None = None

    # Pre-checks without mutating plan/user (so a lost race leaves no orphans).
    if request.request_type == REQUEST_TYPE_NEW_USER:
        bound = _is_bound(db, request.telegram_id)
        if bound is not None:
            raise TelegramAlreadyBound(
                admin_detail=f"Этот Telegram уже привязан к {bound.username}",
                user_id=bound.id,
                username=bound.username,
            )
        plan = _resolve_plan(db, request, preset_id=preset_id, ad_hoc=ad_hoc)
        if not plan["node_ids"] or not plan["protocols"]:
            raise ValueError("Укажите узлы и протоколы плана")
        try:
            validate_plan_nodes(db, plan["node_ids"])
        except HTTPException as exc:
            raise ValueError(exc.detail if isinstance(exc.detail, str) else "Неверные узлы плана") from exc
    elif request.request_type == REQUEST_TYPE_ADD_CONFIG:
        plan = _resolve_plan(db, request, preset_id=None, ad_hoc=ad_hoc)
        user = db.get(User, request.user_id) if request.user_id else None
        if user is None:
            raise ValueError("Пользователь заявки не найден")
    elif request.request_type == REQUEST_TYPE_EXTEND:
        plan = _resolve_plan(db, request, preset_id=None, ad_hoc=ad_hoc)
        user = db.get(User, request.user_id) if request.user_id else None
        if user is None:
            raise ValueError("Пользователь заявки не найден")

    updated = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.id == request_id, UserAccessRequest.status == "pending")
        .update(
            {
                UserAccessRequest.status: "approved",
                UserAccessRequest.reviewed_by_id: admin.id,
                UserAccessRequest.reviewed_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if updated == 0:
        raise AlreadyDecided("Заявка уже обработана")
    db.refresh(request)

    if request.request_type == REQUEST_TYPE_NEW_USER:
        assert plan is not None
        user = _create_user_for_request(db, request, plan, actor_username=admin.username)
        request.user_id = user.id
        db.add(request)
        db.commit()
        db.refresh(request)
    elif request.request_type == REQUEST_TYPE_ADD_CONFIG:
        assert user is not None and plan is not None
        from app.services.user_provisioning import plan_add_index

        for _ in range(max(1, int(plan["count"]))):
            plan_add_index(db, user)
        db.commit()
        db.refresh(user)
    elif request.request_type == REQUEST_TYPE_EXTEND:
        assert user is not None and plan is not None
        from app.services.user_subscription import set_user_access_until

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        new_until = max(now_naive, user.access_until or now_naive) + timedelta(days=int(plan["days"]))
        set_user_access_until(db, user, new_until, actor=admin.username, sync_clients=False, commit=True)

    if request.request_type in (REQUEST_TYPE_NEW_USER, REQUEST_TYPE_ADD_CONFIG):
        assert user is not None
        deliver_approved_request(db, request=request, user=user, plan=plan, actor=admin)
    return request


def reject_request(
    db: Session,
    *,
    request_id: int,
    admin: User,
    reason: str | None = None,
    ban: bool = False,
) -> UserAccessRequest | None:
    """Отклонить заявку. Опционально забанить telegram_id.

    Условный claim pending→rejected (как у approve) — гонка → AlreadyDecided.
    """
    request = db.get(UserAccessRequest, request_id)
    if request is None:
        return None
    if request.status != "pending":
        raise AlreadyDecided("Заявка уже обработана")

    updated = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.id == request_id, UserAccessRequest.status == "pending")
        .update(
            {
                UserAccessRequest.status: "rejected",
                UserAccessRequest.reviewed_by_id: admin.id,
                UserAccessRequest.reviewed_at: datetime.utcnow(),
                UserAccessRequest.reject_reason: reason,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if updated == 0:
        raise AlreadyDecided("Заявка уже обработана")
    db.refresh(request)

    if ban:
        ban_row = (
            db.query(TelegramRequestBan)
            .filter(TelegramRequestBan.telegram_id == request.telegram_id)
            .first()
        )
        if ban_row is None:
            db.add(TelegramRequestBan(telegram_id=request.telegram_id, banned_by_id=admin.id, note=reason))
            db.commit()

    # Requester learns only the neutral fact (E1 — reason stays admin-only).
    bot_token = _bot_token(db)
    if bot_token and request.telegram_id:
        try:
            _run_async(
                send_message(bot_token, str(request.telegram_id), "Вашу заявку рассмотрели администратором.")
            )
        except Exception as exc:  # уведомление не ломает решение
            logger.warning("requester reject notify to %s failed: %s", request.telegram_id, exc)
    return request


# ---------------------------------------------------------------------------
# Task 9: Approval → delivery (D12)
# ---------------------------------------------------------------------------


def send_message_sync_or_async(token: str, chat_id: str, text: str, **kwargs: Any) -> bool:
    """Отправить сообщение в личный чат requester'а (только его telegram_id).

    ``link_preview_options`` отключён внутри ``send_message`` (E2).
    Возвращает ``True`` только при успешной доставке в Telegram API.
    """
    if not token:
        return False
    try:
        return bool(_run_async(send_message(token, chat_id, text, **kwargs)))
    except Exception as exc:  # никогда не ломает доставку
        logger.warning("delivery DM to %s failed: %s", chat_id, exc)
        return False


def _linked_reply_keyboard(user: User) -> dict[str, Any] | None:
    """Reply-клавиатура абонента: после одобрения убирает кнопку «Запросить доступ»."""
    try:
        from app.services.telegram_bot_handlers.menu import build_linked_reply_keyboard

        return build_linked_reply_keyboard(is_admin=user.role == UserRole.admin)
    except Exception as exc:  # клавиатура не должна ломать доставку
        logger.warning("delivery keyboard build failed for user_id=%s: %s", user.id, exc)
        return None


def _delivery_text(portal_url: str, traffic_limit_bytes: int | None) -> str:
    lines = [
        "Доступ одобрен",
        "",
        f"Ваша ссылка на портал: {portal_url}",
        "",
        "Один конфиг WireGuard/AmneziaWG = одно устройство онлайн. "
        "Нужно ещё устройство — нажмите «Запросить ещё конфиг».",
    ]
    if traffic_limit_bytes:
        gb = traffic_limit_bytes / (1024 * 1024 * 1024)
        lines.append(f"Лимит трафика: {gb:g} ГБ.")
    return "\n".join(lines)


def deliver_approved_request(
    db: Session,
    *,
    request: UserAccessRequest,
    user: User,
    plan: dict[str, Any] | None = None,
    actor: User | None = None,
) -> tuple[User, Any]:
    """Оформление одобренной заявки: портал + задача provision (new_user/add_config).

    Вызывается после смены статуса в approved. Создаёт пользователя (если новый),
    issuing портал-ссылку и ставит задачу user_provision.
    """
    if request.request_type == REQUEST_TYPE_NEW_USER:
        user.panel_login_enabled = False
        user.can_create_configs = False
        db.add(user)
        db.commit()
        db.refresh(user)

    _ = get_or_create_user_portal_token(
        db, user_id=user.id, creator=actor if actor is not None else None
    )
    task = enqueue_user_provision(
        db,
        user_id=user.id,
        actor_username=(actor.username if actor is not None else "system"),
        confirm_deletions=False,
    )
    db.refresh(user)
    return user, task


def maybe_send_delivery_after_task(db: Session, *, user_id: int, created_count: int) -> None:
    """После завершения задачи provision: отправить «Доступ одобрен» один раз.

    Сообщение только в личный чат requester'а; портал-ссылка не логируется.
    ``delivered_at`` ставится только после успешной отправки — иначе можно повторить.
    Если конфигов не создано / Telegram не принял — админ получает колокол.
    """
    user = db.get(User, user_id)
    if user is None:
        return
    req = (
        db.query(UserAccessRequest)
        .filter(
            UserAccessRequest.user_id == user_id,
            UserAccessRequest.status == "approved",
            UserAccessRequest.delivered_at.is_(None),
        )
        .order_by(UserAccessRequest.id.desc())
        .first()
    )
    if req is None:
        return
    if created_count <= 0:
        write_admin_panel_notification(
            db,
            event_type="access_request_delivery_failed",
            title=f"{user.username}: заявка одобрена, но конфиги не созданы",
            message="Все узлы провалились при создании конфигов",
            action_payload={"request_id": req.id, "user_id": user_id},
            level="warning",
        )
        return
    bot_token = _get_setting(db, SETTING_BOT_TOKEN, "").strip()
    if not bot_token or not user.telegram_id:
        write_admin_panel_notification(
            db,
            event_type="access_request_delivery_failed",
            title=f"{user.username}: не удалось написать в Telegram",
            message="Нет токена бота или у пользователя нет telegram_id",
            action_payload={"request_id": req.id, "user_id": user_id},
            level="warning",
        )
        return
    portal = user_link_response(db, get_or_create_user_portal_token(db, user_id=user_id))
    text = _delivery_text(portal["url"], user.traffic_limit_bytes)
    if not send_message_sync_or_async(
        bot_token,
        str(user.telegram_id),
        text,
        reply_markup=_linked_reply_keyboard(user),
    ):
        write_admin_panel_notification(
            db,
            event_type="access_request_delivery_failed",
            title=f"{user.username}: Telegram не принял сообщение",
            message="Проверьте, что пользователь нажал /start у бота и не заблокировал его",
            action_payload={"request_id": req.id, "user_id": user_id},
            level="warning",
        )
        return
    updated = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.id == req.id, UserAccessRequest.delivered_at.is_(None))
        .update({UserAccessRequest.delivered_at: datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
    if not updated:
        # Гонка: другой воркер уже пометил — сообщение могло уйти дважды, это редкость.
        logger.info("delivery already marked for request_id=%s user_id=%s", req.id, user_id)


async def sync_admin_request_messages(db: Session, req: UserAccessRequest, *, text: str) -> None:
    """Отредактировать все карточки админов (убрать клавиатуру) после решения по заявке.

    Писать в чужие чаты нельзя — только chat_id из admin_message_refs (личные чаты админов).
    """
    token = _bot_token(db)
    if not token:
        return
    refs = json.loads(req.admin_message_refs or "[]")
    for ref in refs:
        try:
            await edit_message_text(
                token,
                str(ref["chat_id"]),
                int(ref["message_id"]),
                text,
                reply_markup={"inline_keyboard": []},
            )
        except Exception as exc:
            logger.warning("sync request message %s failed: %s", ref, exc)


def delete_user_write_archive(db: Session, user: User) -> None:
    """Перед удалением пользователя написать строку в telegram_user_archive."""
    if not user.telegram_id:
        return
    existing = (
        db.query(TelegramUserArchive)
        .filter(TelegramUserArchive.telegram_id == user.telegram_id)
        .order_by(TelegramUserArchive.id.desc())
        .first()
    )
    if existing is not None and existing.username == user.username:
        return
    db.add(
        TelegramUserArchive(
            telegram_id=user.telegram_id,
            username=user.username,
            created_at=user.created_at,
            deleted_at=datetime.utcnow(),
            last_access_until=user.access_until,
            last_term_days=None,
        )
    )
    db.flush()
