"""Notify delivery hook point — register backends via plugin_registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.plugin_registry import hook_registry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import User

NOTIFY_SEND_HOOK = "notify_backends.send"


def register_notify_backend(name: str, handler) -> None:
    hook_registry.register(NOTIFY_SEND_HOOK, name, handler)


def list_notify_backends() -> list[str]:
    return hook_registry.list_handlers(NOTIFY_SEND_HOOK)


def dispatch_admin_notify(
    db: Session,
    *,
    event_type: str,
    text: str,
    recipients: list[User],
    bot_token: str,
) -> None:
    hook_registry.call(
        NOTIFY_SEND_HOOK,
        db=db,
        event_type=event_type,
        text=text,
        recipients=recipients,
        bot_token=bot_token,
    )
