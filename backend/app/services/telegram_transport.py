"""One path to the Telegram Bot API: direct, or through the relay nodes chosen in settings, in order."""

from __future__ import annotations

import asyncio
import base64
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.services import telegram_api

RELAY_NODES_SETTING = "telegram_relay_node_ids"
FAILED_NODE_COOLDOWN_SECONDS = 120

_failed_until: dict[int, float] = {}
_failed_lock = threading.Lock()
_last_node_name = ""


class TelegramRelayError(RuntimeError):
    pass


def relay_node_ineligible_reason(node) -> str | None:
    from app.services.node_transport import TRANSPORT_SSH, resolve_transport_id

    if node.is_local:
        return "Нужен удалённый узел: этот сервер и есть панель"
    if (node.node_kind or "vpn") != "vpn":
        return "Прокси-узел стоит в РФ и не поможет достучаться до Telegram"
    if not node.mtls_enabled and resolve_transport_id(node) != TRANSPORT_SSH:
        return "Канал до узла не шифруется: включите mTLS или SSH-транспорт на странице «Узлы»"
    return None


def parse_relay_node_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.split(",") if part.strip()]


def current_relay_setting() -> str:
    """Relay node ids as stored ("3,1,5"), or "" when Telegram is reached directly."""
    from app.database import SessionLocal
    from app.services.app_setting_store import _get_setting

    with SessionLocal() as db:
        return _get_setting(db, RELAY_NODES_SETTING).strip()


def relay_node_ids() -> list[int]:
    return parse_relay_node_ids(current_relay_setting())


def last_relay_node_name() -> str:
    return _last_node_name


def mark_relay_node_failed(node_id: int) -> None:
    with _failed_lock:
        _failed_until[node_id] = time.monotonic() + FAILED_NODE_COOLDOWN_SECONDS


def _relay_adapter_for(node_id: int):
    from app.database import SessionLocal
    from app.models import Node
    from app.services.node_manager import get_adapter_for_node

    with SessionLocal() as db:
        node = db.get(Node, node_id)
        if node is None:
            raise TelegramRelayError(f"Узел #{node_id} удалён — уберите его из списка в настройках Telegram")
        reason = relay_node_ineligible_reason(node)
        if reason:
            raise TelegramRelayError(f"Узел «{node.name}»: {reason}")
        adapter = get_adapter_for_node(node)
        adapter.node_name = node.name
        return adapter


def _encode(
    token: str,
    method: str,
    *,
    json: Any = None,
    data: Any = None,
    files: Any = None,
    timeout: httpx.Timeout | float | None = None,
) -> httpx.Request:
    if json is None and not data and not files:
        json = {}
    request = httpx.Request(
        "POST",
        telegram_api.bot_api_url(token, method),
        json=json,
        data=data,
        files=files,
        extensions={"timeout": httpx.Timeout(timeout if timeout is not None else telegram_api._TIMEOUT).as_dict()},
    )
    request.read()
    return request


def _relay_envelope(adapter, call: Callable[[Any], dict]) -> dict:
    try:
        return call(adapter)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise TelegramRelayError(
                f"Агент узла «{adapter.node_name}» не умеет пересылать запросы Telegram — обновите агент до 1.13.0"
            ) from exc
        detail = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
        raise TelegramRelayError(f"Узел «{adapter.node_name}»: {detail}") from exc
    finally:
        adapter.close()


def call_via_node(node_id: int, call: Callable[[Any], dict]) -> tuple[dict, str]:
    adapter = _relay_adapter_for(node_id)
    return _relay_envelope(adapter, call), adapter.node_name


def _attempt_order(node_ids: list[int]) -> list[int]:
    now = time.monotonic()
    with _failed_lock:
        cooling = {node_id for node_id in node_ids if _failed_until.get(node_id, 0.0) > now}
    return [n for n in node_ids if n not in cooling] + [n for n in node_ids if n in cooling]


def _call_relay_chain(node_ids: list[int], call: Callable[[Any], dict]) -> dict:
    global _last_node_name
    errors: list[str] = []
    for node_id in _attempt_order(node_ids):
        try:
            envelope, name = call_via_node(node_id, call)
        except TelegramRelayError as exc:
            mark_relay_node_failed(node_id)
            errors.append(str(exc))
            continue
        with _failed_lock:
            _failed_until.pop(node_id, None)
        _last_node_name = name
        return envelope
    raise TelegramRelayError("; ".join(errors))


def _bot_api_call(token: str, method: str, request: httpx.Request) -> Callable[[Any], dict]:
    return lambda adapter: adapter.telegram_bot_api(token, method, request.content, request.headers["content-type"])


def bot_api_post_sync(
    token: str,
    method: str,
    *,
    json: Any = None,
    data: Any = None,
    files: Any = None,
    timeout: httpx.Timeout | float | None = None,
) -> dict:
    request = _encode(token, method, json=json, data=data, files=files, timeout=timeout)
    node_ids = relay_node_ids()
    if node_ids:
        return _call_relay_chain(node_ids, _bot_api_call(token, method, request))["body"]
    return telegram_api._get_bot_api_sync_client().send(request).json()


async def bot_api_post(
    token: str,
    method: str,
    *,
    json: Any = None,
    timeout: httpx.Timeout | float | None = None,
) -> dict:
    request = _encode(token, method, json=json, timeout=timeout)
    node_ids = await asyncio.to_thread(relay_node_ids)
    if node_ids:
        envelope = await asyncio.to_thread(_call_relay_chain, node_ids, _bot_api_call(token, method, request))
        return envelope["body"]
    response = await telegram_api._get_bot_api_client().send(request)
    return response.json()


def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"error": response.text.strip() or response.reason_phrase}


def oidc_token_exchange_sync(form: dict[str, str], *, client_id: str, client_secret: str) -> tuple[int, Any]:
    """POST the OIDC token form to oauth.telegram.org; returns (HTTP status, parsed body)."""
    from app.services.telegram_relay import OIDC_TOKEN_URL

    node_ids = relay_node_ids()
    if node_ids:
        body = urlencode(form).encode()
        authorization = "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        envelope = _call_relay_chain(node_ids, lambda a: a.telegram_oidc_token(body, authorization))
        return envelope["status"], envelope["body"]
    response = httpx.post(OIDC_TOKEN_URL, data=form, auth=(client_id, client_secret), timeout=15.0)
    return response.status_code, _json_or_text(response)


def oidc_jwks_sync() -> dict:
    from app.services.telegram_relay import OIDC_JWKS_URL

    node_ids = relay_node_ids()
    if node_ids:
        envelope = _call_relay_chain(node_ids, lambda a: a.telegram_oidc_jwks())
        if envelope["status"] >= 400:
            raise TelegramRelayError(f"oauth.telegram.org вернул HTTP {envelope['status']} на запрос ключей")
        return envelope["body"]
    response = httpx.get(OIDC_JWKS_URL, timeout=10.0)
    response.raise_for_status()
    return response.json()
