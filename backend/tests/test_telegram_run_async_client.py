"""Регрессия: ``_run_async`` из bot-loop не оставлял клиент от закрытого цикла.

После уведомления админа об заявке ``_run_async`` выполнял корутину в aux-потоке
и оставлял глобальный ``httpx.AsyncClient`` привязанным к уже закрытому циклу.
Следующий вызов на bot-loop падал с «Event loop is closed» — ``sendWidget``
терял ответ Telegram, карточка-виджет не сохранялась в БД.
"""

from __future__ import annotations

import asyncio
import threading

from app.services import telegram_api
from app.services.user_access_requests import _run_async


def test_run_async_from_bot_loop_leaves_no_loop_bound_client():
    box: dict = {}

    def bot_thread() -> None:
        async def main() -> None:
            async def work() -> bool:
                telegram_api._get_bot_api_client()  # клиент живёт в aux-цикле
                return True

            box["value"] = _run_async(work())
            box["client_after"] = telegram_api._bot_api_client

        asyncio.run(main())

    thread = threading.Thread(target=bot_thread, daemon=True)
    thread.start()
    thread.join(timeout=10)

    assert box["value"] is True
    assert box["client_after"] is None
