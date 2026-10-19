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
from datetime import datetime, timedelta, timezone
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
from app.services.client_portal import get_or_create_user_portal_token, user_link_response
from app.services.telegram import send_tg_message
from app.services.telegram_api import send_message
from app.services.user_provisioning import enqueue_user_provision, validate_plan_nodes

logger = logging.getLogger(__name__)

REQUEST_TYPE_NEW_USER = "new_user"
REQUEST_TYPE_ADD_CONFIG = "add_config"
REQUEST_TYPE_EXTEND = "extend_access"

REQUEST_TYPES = (REQUEST_TYPE_NEW_USER, REQUEST_TYPE_ADD_CONFIG, REQUEST_TYPE_EXTEND)

SETTING_ACCEPT_REQUESTS = "telegram_accept_access_requests"
SETTING_PENDING_CAP = "telegram_new_user_request_pending_cap"
SETTING_BOT_TOKEN = "telegram_bot_token"

COOLDOWN_HOURS = 24
TELEGRAM_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{5,32}$")


class RequestError(Exception):
    """Базовая доменная ошибка заявки."""


class RequestsClosed(RequestError):
    """Приём заявок закрыт (настройкой, лимитом или блокировкой)."""


class AlreadyPending(RequestError):
    """У requester'а уже есть pending-заявка этого типа."""


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


def _accept_requests(db: Session) -> bool:
    return _get_setting(db, SETTING_ACCEPT_REQUESTS, "false").strip().lower() == "true"


def _pending_cap(db: Session) -> int:
    raw = _get_setting(db, SETTING_PENDING_CAP, "50").strip()
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 50


def _is_bound(db: Session, telegram_id: str) -> User | None:
    return db.query(User).filter(User.telegram_id == telegram_id).first()


def _login_is_free(db: Session, username: str) -> bool:
    return db.query(User).filter(User.username == username).first() is None


def _propose_login(db: Session, telegram_username: str | None, telegram_id: str) -> str:
    if telegram_username and TELEGRAM_USERNAME_RE.fullmatch(telegram_username) and _login_is_free(db, telegram_username):
        return telegram_username
    return f"tg{telegram_id}"


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

    if request_type == REQUEST_TYPE_NEW_USER:
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
        title=f"Новая заявка на доступ: {request_type}",
        message=f"Telegram ID {telegram_id}" + (f" ({telegram_name})" if telegram_name else ""),
        action_payload={"request_id": row.id, "request_type": request_type},
    )
    # Админы — только в личные чаты (telegram_id), никогда не в telegram_chat_id (группа).
    _notify_admins_new_request(db, row)
    return row


def _notify_admins_new_request(db: Session, request: UserAccessRequest) -> None:
    bot_token = _get_setting(db, SETTING_BOT_TOKEN, "").strip()
    if not bot_token:
        return
    admins = (
        db.query(User)
        .filter(User.role == UserRole.admin, User.is_active.is_(True), User.telegram_id.isnot(None))
        .all()
    )
    if not admins:
        return
    lines = [
        f"Новая заявка на доступ: {request.request_type}",
        f"Telegram: {request.telegram_name or request.telegram_id}",
    ]
    if request.telegram_username:
        lines.append(f"Ник: @{request.telegram_username}")
    if request.user_note:
        lines.append(f"Комментарий: {request.user_note}")
    text = "\n".join(lines)
    for admin in admins:
        try:
            send_tg_message(bot_token, str(admin.telegram_id), text, run_async=False)
        except Exception as exc:  #never blocks submit
            logger.warning("new request notify to admin %s failed: %s", admin.id, exc)


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
            return {
                "node_ids": [int(n) for n in node_ids],
                "protocols": [str(p) for p in protocols],
                "config_count": preset.config_count or 1,
                "access_days": preset.access_days,
                "traffic_limit_bytes": preset.traffic_limit_bytes,
                "username": None,
            }
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

    Условное обновление pending→approved; при проигрыше гонки — AlreadyDecided.
    Для new_user перепроверяет привязку Telegram → TelegramAlreadyBound.
    Вызывает deliver_approved_request после смены статуса.
    """
    request = db.get(UserAccessRequest, request_id)
    if request is None:
        return None
    if request.status != "pending":
        raise AlreadyDecided("Заявка уже обработана")

    plan: dict[str, Any] | None = None
    user: User | None = None
    if request.request_type == REQUEST_TYPE_NEW_USER:
        # Перепроверка привязки Telegram на момент одобрения.
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
        user = _create_user_for_request(db, request, plan, actor_username=admin.username)
    elif request.request_type == REQUEST_TYPE_ADD_CONFIG:
        plan = _resolve_plan(db, request, preset_id=None, ad_hoc=ad_hoc)
        user = db.get(User, request.user_id) if request.user_id else None
        if user is None:
            raise ValueError("Пользователь заявки не найден")
        # Добавляем запрошенное число имён в план пользователя.
        from app.services.user_provisioning import plan_add_index

        for _ in range(max(1, int(plan["count"]))):
            plan_add_index(db, user)
        db.commit()
        db.refresh(user)
    elif request.request_type == REQUEST_TYPE_EXTEND:
        plan = _resolve_plan(db, request, preset_id=None, ad_hoc=ad_hoc)
        user = db.get(User, request.user_id) if request.user_id else None
        if user is None:
            raise ValueError("Пользователь заявки не найден")
        from app.services.user_subscription import set_user_access_until

        new_until = max(datetime.now(timezone.utc).replace(tzinfo=None), user.access_until or datetime.now(timezone.utc).replace(tzinfo=None)) + timedelta(
            days=int(plan["days"])
        )
        set_user_access_until(db, user, new_until, actor=admin.username, sync_clients=False, commit=True)

    # Условный переход pending → approved (защита от двойного одобрения).
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

    # Доставка (Task 9): new_user/add_config создают пользователя и ставят задачу provision.
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
    """Отклонить заявку. Опционально забанить telegram_id."""
    request = db.get(UserAccessRequest, request_id)
    if request is None:
        return None
    if request.status != "pending":
        raise AlreadyDecided("Заявка уже обработана")
    request.status = "rejected"
    request.reviewed_by_id = admin.id
    request.reviewed_at = datetime.utcnow()
    request.reject_reason = reason
    if ban:
        ban_row = (
            db.query(TelegramRequestBan)
            .filter(TelegramRequestBan.telegram_id == request.telegram_id)
            .first()
        )
        if ban_row is None:
            db.add(TelegramRequestBan(telegram_id=request.telegram_id, banned_by_id=admin.id, note=reason))
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


# ---------------------------------------------------------------------------
# Task 9: Approval → delivery (D12)
# ---------------------------------------------------------------------------


def send_message_sync_or_async(token: str, chat_id: str, text: str, **_kwargs: Any) -> None:
    """Отправить сообщение в личный чат requester'а (только его telegram_id).

    ``link_preview_options`` отключён внутри ``send_message`` (E2).
    """
    if not token:
        return
    try:
        asyncio.run(send_message(token, chat_id, text))
    except Exception as exc:  # никогда не ломает доставку
        logger.warning("delivery DM to %s failed: %s", chat_id, exc)


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
    Если конфигов не создано — админ получает колокол access_request_delivery_failed.
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
    updated = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.id == req.id, UserAccessRequest.delivered_at.is_(None))
        .update({UserAccessRequest.delivered_at: datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
    if not updated:
        return
    bot_token = _get_setting(db, SETTING_BOT_TOKEN, "").strip()
    if not bot_token or not user.telegram_id:
        return
    portal = user_link_response(db, get_or_create_user_portal_token(db, user_id=user_id))
    text = _delivery_text(portal["url"], None)
    send_message_sync_or_async(bot_token, str(user.telegram_id), text)


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
