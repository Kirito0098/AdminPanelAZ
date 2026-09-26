"""Reject writes aimed at a node other than the one the admin sees in the UI.

The active node is a single panel-wide setting: another tab, another admin, the Telegram bot
or the Mini App can switch it between the moment a page loads and the moment it saves.
"""

from __future__ import annotations

from contextvars import ContextVar

from fastapi import HTTPException, status

from app.models import Node

EXPECTED_NODE_HEADER = "X-Expected-Node-Id"
ACTIVE_NODE_CHANGED_CODE = "active_node_changed"

_HEADER_KEY = EXPECTED_NODE_HEADER.lower().encode("latin-1")
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_MAX_ID_DIGITS = 18

_expected_node_id: ContextVar[int | None] = ContextVar("expected_node_id", default=None)


def parse_expected_node_header(raw: str | None) -> int | None:
    value = (raw or "").strip()
    if not value.isascii() or not value.isdigit() or len(value) > _MAX_ID_DIGITS:
        return None
    node_id = int(value)
    return node_id if node_id > 0 else None


def forget_expected_node() -> None:
    """The request switched the active node itself; later lookups in it follow the new node."""
    _expected_node_id.set(None)


def ensure_expected_node(node: Node) -> None:
    expected = _expected_node_id.get()
    if expected is None or expected == node.id:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": ACTIVE_NODE_CHANGED_CODE,
            "message": (
                f"Активный узел сменился на «{node.name}» — в другой вкладке, в Telegram-боте "
                "или другим администратором. Действие не выполнено: проверьте узел и повторите."
            ),
            "active_node_id": node.id,
        },
    )


class ExpectedNodeMiddleware:
    """Binds ``X-Expected-Node-Id`` of a write request for :func:`ensure_expected_node`."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        # lifespan and websocket scopes carry no method and pass through as reads.
        if str(scope.get("method", "GET")).upper() in _READ_METHODS:
            await self.app(scope, receive, send)
            return
        raw = next(
            (value.decode("latin-1") for key, value in scope.get("headers") or [] if key.lower() == _HEADER_KEY),
            None,
        )
        token = _expected_node_id.set(parse_expected_node_header(raw))
        try:
            await self.app(scope, receive, send)
        finally:
            _expected_node_id.reset(token)
