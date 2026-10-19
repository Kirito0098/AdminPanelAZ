"""Уведомления о массовых операциях с серверами (Stage 4).

Тексты сообщений, троттлинг отправки (≈20 сообщений/с — ниже лимита
Telegram) и правила доставки: только в личный чат пользователя
(``user.telegram_id``), без превью ссылок. Пользователям без Telegram тот же
текст показывается баннером в портале (Task 7).
"""

from __future__ import annotations

import html
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy.orm import Session

from app.models import User
from app.services.telegram import send_tg_message_result

if TYPE_CHECKING:  # pragma: no cover — только типы, без циклического импорта
    from app.services.bulk_user_nodes import BulkUserNodeResult

BulkNodesAction = Literal["add", "remove", "replace"]

# Не чаще ~20 сообщений в секунду — Telegram такие темпы принимает.
TELEGRAM_BULK_RATE_PER_SEC = 20

# Заголовки для сводки админа (Task 8) и подписи прогресса.
ACTION_TITLES: dict[str, str] = {
    "add": "Добавлен",
    "remove": "Отключён",
    "replace": "Заменён",
}


def render_bulk_notify_text(
    action: BulkNodesAction,
    *,
    node_label: str,
    to_node_label: str | None = None,
    note: str | None = None,
    remaining_labels: list[str] | None = None,
    other_servers_hint: bool = False,
) -> str:
    """Текст сообщения пользователю о массовой операции (спека §10).

    ``remaining_labels`` — серверы пользователя, конфиги с которых остаются
    рабочими; ``other_servers_hint`` — обобщённая подсказка для предпросмотра,
    где точный список серверов пользователя ещё не известен.
    """
    if action == "add":
        text = (
            f"Добавлен новый сервер {node_label}. "
            "Скачайте конфиг для него в портале или Mini App."
        )
    elif action == "remove":
        text = f"Сервер {node_label} отключён, конфиги для него больше не работают."
        if remaining_labels:
            text += f" Используйте конфиг для {remaining_labels[0]}."
        elif other_servers_hint:
            text += " Остальные ваши серверы продолжают работать."
    else:
        target = to_node_label or node_label
        text = (
            f"Сервер {node_label} заменён на {target}. "
            "Скачайте новый конфиг и удалите старый с устройств."
        )
    note_text = (note or "").strip()
    if note_text:
        text += f"\n\n{note_text}"
    return text


class TelegramBulkThrottle:
    """Ограничитель частоты отправки: не чаще ``rate`` сообщений в секунду."""

    def __init__(self, rate: float = TELEGRAM_BULK_RATE_PER_SEC) -> None:
        self._min_interval = 1.0 / float(rate or TELEGRAM_BULK_RATE_PER_SEC)
        self._last: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._last is None:
            time.sleep(self._min_interval)
        else:
            delay = self._min_interval - (now - self._last)
            if delay > 0:
                time.sleep(delay)
        self._last = time.monotonic()

    def send(self, sender: Callable[[], str]) -> str:
        """Подождать место в очереди и отправить сообщение."""
        self.wait()
        return sender()


def set_portal_banner(db: Session, user: User, text: str) -> None:
    """Показать пользователю текст уведомления баннером в портале.

    Запасной канал для пользователей без привязанного Telegram (спека §10).
    """
    user.portal_banner_text = (text or "").strip() or None
    user.portal_banner_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(user)
    db.commit()


def clear_portal_banner(db: Session, user: User) -> None:
    """Убрать баннер портала (пользователь его закрыл)."""
    if not user.portal_banner_text and user.portal_banner_at is None:
        return
    user.portal_banner_text = None
    user.portal_banner_at = None
    db.add(user)
    db.commit()


def send_bulk_user_notify(
    *,
    bot_token: str,
    telegram_id: int | str,
    text: str,
    portal_url: str | None = None,
) -> Literal["sent", "undelivered", "error"]:
    """Отправить сообщение пользователю — только в его личный чат.

    403 от Telegram (бот заблокирован) — ``undelivered``: сообщение помечается
    в отчёте и не повторяется. Остальные сбои — ``error``.
    """
    if not bot_token:
        return "error"
    message = f"{text}\n\n{portal_url}" if portal_url else text
    ok, error_code = send_tg_message_result(
        bot_token, str(telegram_id), html.escape(message, quote=False)
    )
    if ok:
        return "sent"
    if error_code == 403:
        return "undelivered"
    return "error"


def maybe_notify_after_user(
    *,
    enabled: bool,
    user: User,
    result: BulkUserNodeResult,
    action: BulkNodesAction,
    node_label: str,
    to_node_label: str | None = None,
    note: str | None = None,
    remaining_labels: list[str] | None = None,
    bot_token: str = "",
    portal_url: str | None = None,
    throttle: TelegramBulkThrottle | None = None,
    db: Session | None = None,
) -> str:
    """Уведомить пользователя о результате его части операции.

    Возвращает статус доставки: ``disabled`` / ``skipped_status`` /
    ``skipped_no_create`` / ``no_telegram`` / ``sent`` / ``undelivered`` / ``error``.
    """
    if not enabled:
        return "disabled"
    if result.status != "ok":
        return "skipped_status"
    # Спека §10: уведомляем только когда пользователю есть что скачать —
    # для «добавить» создан хотя бы один конфиг на новом сервере.
    if action == "add" and result.created < 1:
        return "skipped_no_create"
    if action == "replace" and not result.replaced and result.created < 1:
        return "skipped_no_create"

    text = render_bulk_notify_text(
        action,
        node_label=node_label,
        to_node_label=to_node_label,
        note=note,
        remaining_labels=remaining_labels,
    )
    telegram_id = (user.telegram_id or "").strip()
    if not telegram_id:
        # Telegram не привязан — тот же текст показываем баннером в портале.
        if db is not None:
            set_portal_banner(db, user, text)
        return "no_telegram"
    if not bot_token:
        return "error"

    throttle = throttle or TelegramBulkThrottle()
    return throttle.send(
        lambda: send_bulk_user_notify(
            bot_token=bot_token,
            telegram_id=telegram_id,
            text=text,
            portal_url=portal_url,
        )
    )
