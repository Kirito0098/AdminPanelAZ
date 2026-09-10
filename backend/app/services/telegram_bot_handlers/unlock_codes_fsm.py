"""In-memory FSM for Telegram unlock-code creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

UnlockCodeStep = Literal["grant_days", "protocols", "mode"]

_pending: dict[str, "PendingUnlockCode"] = {}


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
    _pending[str(telegram_user_id)] = PendingUnlockCode(
        step=step,
        grant_days=grant_days,
        protocols=protocols,
    )


def get_pending(telegram_user_id: str) -> PendingUnlockCode | None:
    return _pending.get(str(telegram_user_id))


def clear_pending(telegram_user_id: str) -> None:
    _pending.pop(str(telegram_user_id), None)


def clear_all() -> None:
    """Test helper."""
    _pending.clear()
