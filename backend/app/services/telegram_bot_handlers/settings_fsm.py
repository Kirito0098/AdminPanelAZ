"""FSM for bot settings text input, shared by uvicorn workers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Literal

from app.services.shared_state import clear_states, delete_state, get_state, put_state

FieldKind = Literal[
    "token", "user", "chat", "age", "an_tgid",
    "mon_cpu", "mon_ram", "mon_int", "mon_cd",
    "bk_days", "bk_ret",
    "sec_allow_ip", "sec_tmp_ip",
]

NAMESPACE = "tg_settings_input"
PENDING_TTL = timedelta(hours=1)


@dataclass
class PendingInput:
    field: FieldKind
    value: str = ""


def _save(telegram_user_id: str, pending: PendingInput) -> None:
    put_state(NAMESPACE, str(telegram_user_id), asdict(pending), ttl=PENDING_TTL)


def set_pending(telegram_user_id: str, field: FieldKind) -> None:
    _save(telegram_user_id, PendingInput(field=field))


def set_pending_value(telegram_user_id: str, value: str) -> None:
    pending = get_pending(telegram_user_id)
    if pending:
        pending.value = value
        _save(telegram_user_id, pending)


def get_pending(telegram_user_id: str) -> PendingInput | None:
    data = get_state(NAMESPACE, str(telegram_user_id))
    return PendingInput(**data) if data is not None else None


def clear_pending(telegram_user_id: str) -> None:
    delete_state(NAMESPACE, str(telegram_user_id))


def clear_all() -> None:
    """Test helper."""
    clear_states(NAMESPACE)
