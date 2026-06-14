"""In-memory FSM for bot settings text input (single uvicorn worker)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FieldKind = Literal[
    "token", "user", "chat", "age", "an_tgid",
    "mon_cpu", "mon_ram", "mon_int", "mon_cd",
    "bk_days", "bk_ret",
    "sec_allow_ip", "sec_tmp_ip",
]

_pending: dict[str, "PendingInput"] = {}


@dataclass
class PendingInput:
    field: FieldKind
    value: str = ""


def set_pending(telegram_user_id: str, field: FieldKind) -> None:
    _pending[str(telegram_user_id)] = PendingInput(field=field)


def set_pending_value(telegram_user_id: str, value: str) -> None:
    key = str(telegram_user_id)
    pending = _pending.get(key)
    if pending:
        pending.value = value


def get_pending(telegram_user_id: str) -> PendingInput | None:
    return _pending.get(str(telegram_user_id))


def clear_pending(telegram_user_id: str) -> None:
    _pending.pop(str(telegram_user_id), None)


def clear_all() -> None:
    """Test helper."""
    _pending.clear()
