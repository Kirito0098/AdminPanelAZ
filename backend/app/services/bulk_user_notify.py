"""Массовое уведомление абонентов в Telegram (D5).

Отправка — в личный чат, не чаще ~20 сообщений/с (TelegramBulkThrottle).
Пользователи без telegram_id в отчёт попадают как no_telegram и не получают
сообщение. 403 (бот заблокирован) — undelivered, без повтора.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from app.database import SessionLocal
from app.models import User
from app.services.background_tasks import _submit_in_current_context, background_task_service
from app.services.bulk_user_nodes_notify import TelegramBulkThrottle, send_bulk_user_notify

logger = logging.getLogger(__name__)

BULK_NOTIFY_TASK_TYPE = "bulk_user_notify"
BULK_NOTIFY_SUBJECT = "bulk_notify"

ProgressUpdater = Callable[[int, str], None]


def _run_bulk_notify(
    users: list[User],
    text: str,
    bot_token: str,
    updater: ProgressUpdater,
) -> dict[str, Any]:
    """Отправить текст каждому пользователю. Без БД и сети — тестируется напрямую."""
    body = (text or "").strip()
    # Абонент должен понимать, от кого сообщение: подпись добавляем один раз.
    if body and "Уведомление от администратора" not in body:
        body = f"📢 Уведомление от администратора\n\n{body}"

    throttle = TelegramBulkThrottle()
    stats: dict[str, Any] = {
        "total": len(users),
        "delivered": 0,
        "undelivered": 0,
        "no_telegram": 0,
        "errors": [],
    }
    total = max(len(users), 1)
    for index, user in enumerate(users, start=1):
        telegram_id = (user.telegram_id or "").strip()
        if not telegram_id:
            stats["no_telegram"] += 1
        else:
            status = throttle.send(
                lambda telegram_id=telegram_id: send_bulk_user_notify(
                    bot_token=bot_token,
                    telegram_id=telegram_id,
                    text=body,
                )
            )
            if status == "sent":
                stats["delivered"] += 1
            elif status == "undelivered":
                stats["undelivered"] += 1
            else:
                stats["errors"].append(
                    {"user_id": user.id, "username": user.username, "error": "send failed"}
                )
        updater(int(index * 100 / total), f"Отправлено: {index} / {len(users)}")
    summary = (
        f"Доставлено {stats['delivered']}, не доставлено {stats['undelivered']}, "
        f"без Telegram {stats['no_telegram']}"
    )
    return {"summary": summary, **stats, "output": json.dumps(stats, ensure_ascii=False)}


def start_bulk_user_notify(
    *,
    user_ids: list[int],
    text: str,
    bot_token: str,
    actor_username: str | None,
) -> str:
    """Поставить фоновую задачу и вернуть её id."""
    task_id = background_task_service.create_queued_task(
        BULK_NOTIFY_TASK_TYPE,
        f"Уведомление: {len(user_ids)} абонентов",
        created_by_username=actor_username,
        subject_key=BULK_NOTIFY_SUBJECT,
        input=json.dumps({"user_ids": user_ids, "text": text}, ensure_ascii=False),
    )

    def worker(progress_updater: Callable[[int, str, str | None], None]) -> dict[str, Any]:
        db = SessionLocal()
        try:
            users = (
                db.query(User)
                .filter(User.id.in_(user_ids))
                .order_by(User.id)
                .all()
            )
            return _run_bulk_notify(
                users,
                text,
                bot_token,
                lambda percent, stage: progress_updater(percent, stage, None),
            )
        finally:
            db.close()

    _submit_in_current_context(background_task_service.run_background_task, task_id, worker)
    return task_id
