"""FSM for Telegram unlock-code creation, shared by uvicorn workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from app.services.shared_state import clear_states, delete_state, get_state, put_state

UnlockCodeStep = Literal["grant_days", "protocols", "mode"]

NAMESPACE = "tg_unlock_code"
PENDING_TTL = timedelta(hours=1)


@dataclass
class PendingUnlockCode:
    step: UnlockCodeStep
    grant_days: int | None = None
    protocols: tuple[str, ...] = ()


def set_pending(
    telegram_user_id: str,
    *,
    step: UnlockCodeStep,
    grant_days: int | None = None,
    protocols: tuple[str, ...] = (),
) -> None:
    put_state(
        NAMESPACE,
        str(telegram_user_id),
        {"step": step, "grant_days": grant_days, "protocols": list(protocols)},
        ttl=PENDING_TTL,
    )


def get_pending(telegram_user_id: str) -> PendingUnlockCode | None:
    data = get_state(NAMESPACE, str(telegram_user_id))
    if data is None:
        return None
    return PendingUnlockCode(step=data["step"], grant_days=data["grant_days"], protocols=tuple(data["protocols"]))


def clear_pending(telegram_user_id: str) -> None:
    delete_state(NAMESPACE, str(telegram_user_id))


def clear_all() -> None:
    """Test helper."""
    clear_states(NAMESPACE)
