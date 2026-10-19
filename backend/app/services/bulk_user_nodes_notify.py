"""Тексты уведомлений о массовых операциях с серверами (Stage 4).

Здесь только тексты: они нужны предпросмотру (Task 2) и диалогу.
Отправка в Telegram с троттлингом — Task 6, баннер портала — Task 7.
"""

from __future__ import annotations

from typing import Literal

BulkNodesAction = Literal["add", "remove", "replace"]

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
