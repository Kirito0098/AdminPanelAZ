"""Short-lived state shared by uvicorn workers: Telegram bot dialogs, OIDC login state.

A webhook update or an OAuth callback can reach any worker, so state kept in one worker's
memory is lost for the next step. The panel stores it in the ``shared_state`` table; the
lifespan switches to it. Without that (tests, scripts) the state lives in process memory.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import SharedState

_session_factory: Callable[[], Session] | None = None
_memory: dict[tuple[str, str], tuple[datetime, dict[str, Any]]] = {}
_memory_lock = threading.Lock()


def _now() -> datetime:
    return datetime.utcnow()


def configure_shared_state(session_factory: Callable[[], Session] | None) -> None:
    global _session_factory
    _session_factory = session_factory


def put_state(namespace: str, key: str, value: dict[str, Any], *, ttl: timedelta) -> None:
    now = _now()
    if _session_factory is None:
        with _memory_lock:
            _memory[(namespace, key)] = (now + ttl, value)
        return
    with _session_factory() as db:
        db.execute(delete(SharedState).where(SharedState.namespace == namespace, SharedState.expires_at <= now))
        payload = json.dumps(value)
        db.execute(
            sqlite_insert(SharedState)
            .values(namespace=namespace, key=key, payload=payload, expires_at=now + ttl)
            .on_conflict_do_update(
                index_elements=[SharedState.namespace, SharedState.key],
                set_={"payload": payload, "expires_at": now + ttl},
            )
        )
        db.commit()


def get_state(namespace: str, key: str) -> dict[str, Any] | None:
    now = _now()
    if _session_factory is None:
        with _memory_lock:
            entry = _memory.get((namespace, key))
        return entry[1] if entry is not None and entry[0] > now else None
    with _session_factory() as db:
        payload = db.scalar(
            select(SharedState.payload).where(
                SharedState.namespace == namespace, SharedState.key == key, SharedState.expires_at > now
            )
        )
    return json.loads(payload) if payload is not None else None


def _db_pop(db: Session, namespace: str, key: str) -> dict[str, Any] | None:
    payload = db.scalar(
        delete(SharedState)
        .where(SharedState.namespace == namespace, SharedState.key == key, SharedState.expires_at > _now())
        .returning(SharedState.payload)
    )
    db.commit()
    return json.loads(payload) if payload is not None else None


def pop_state(namespace: str, key: str) -> dict[str, Any] | None:
    """Return and remove the state; of concurrent callers only one gets it."""
    if _session_factory is None:
        with _memory_lock:
            entry = _memory.pop((namespace, key), None)
        return entry[1] if entry is not None and entry[0] > _now() else None
    with _session_factory() as db:
        return _db_pop(db, namespace, key)


def delete_state(namespace: str, key: str) -> None:
    if _session_factory is None:
        with _memory_lock:
            _memory.pop((namespace, key), None)
        return
    with _session_factory() as db:
        db.execute(delete(SharedState).where(SharedState.namespace == namespace, SharedState.key == key))
        db.commit()


def clear_states(namespace: str) -> None:
    if _session_factory is None:
        with _memory_lock:
            for entry_key in [k for k in _memory if k[0] == namespace]:
                del _memory[entry_key]
        return
    with _session_factory() as db:
        db.execute(delete(SharedState).where(SharedState.namespace == namespace))
        db.commit()
