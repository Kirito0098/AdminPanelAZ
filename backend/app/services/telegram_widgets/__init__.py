"""Интерактивные карточки-виджеты Telegram (Bot API 10.4)."""

from app.services.telegram_widgets.access_request import (
    refresh_access_request_cards,
    refresh_access_request_cards_sync,
    send_access_request_card,
)
from app.services.telegram_widgets.dispatch import handle_widget_query
from app.services.telegram_widgets.hub import send_hub

__all__ = [
    "handle_widget_query",
    "refresh_access_request_cards",
    "refresh_access_request_cards_sync",
    "send_access_request_card",
    "send_hub",
]
