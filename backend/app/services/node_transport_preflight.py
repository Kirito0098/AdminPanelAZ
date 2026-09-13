"""Preflight checks before changing a remote node's transport."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node
from app.schemas import NodeTransportUpdate
from app.services.crypto import encrypt_secret
from app.services.feature_guards import module_disabled_message
from app.services.feature_toggles import is_node_ssh_transport_enabled
from app.services.node_adapter import RemoteNodeAdapter
from app.services.node_manager import get_api_key_plain, validate_node_host
from app.services.node_transport import TRANSPORT_HTTP, TRANSPORT_MTLS, TRANSPORT_SSH, resolve_transport_id
from app.services.proxy_node_adapter import ProxyNodeAdapter
from app.services.ssh_tunnel_pool import get_ssh_tunnel_pool

NODE_KIND_PROXY = "proxy"


@dataclass(frozen=True)
class TransportPreflightResult:
    ok: bool
    current: str
    wanted: str
    message: str
    hint: str | None = None
    probe_status: str | None = None
    probe_error: str | None = None
    http_status: int = 400


def _node_kind(node: Node) -> str:
    return (getattr(node, "node_kind", None) or "vpn").strip().lower()


def _normalize(value: str | None) -> str:
    return (value or "").strip()


def _probe_direct(
    node: Node,
    *,
    api_key: str,
    mtls: bool,
) -> tuple[bool, str | None, str | None]:
    """Probe agent on public node.host:node.port (not via SSH)."""
    host = str(node.host or "").strip()
    port = int(node.port or 0)
    if not host or port <= 0:
        return False, "offline", "У узла не задан host/port"
    try:
        if _node_kind(node) == NODE_KIND_PROXY:
            adapter = ProxyNodeAdapter(
                host=host,
                port=port,
                api_key=api_key,
                mtls_enabled=mtls,
            )
            try:
                adapter.health()
            finally:
                adapter.close()
        else:
            adapter = RemoteNodeAdapter(
                host=host,
                port=port,
                api_key=api_key,
                mtls_enabled=mtls,
            )
            try:
                adapter.health_check()
            finally:
                adapter.close()
        return True, "online", None
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("detail") or detail)
        else:
            message = str(detail)
        return False, "offline", message
    except Exception as exc:  # noqa: BLE001 — probe must never raise to callers
        return False, "offline", str(exc)


def _build_ssh_probe_node(node: Node, body: NodeTransportUpdate) -> Any:
    settings = get_settings()
    updates = body.model_dump(exclude_unset=True)

    ssh_host = _normalize(body.ssh_host if "ssh_host" in updates else getattr(node, "ssh_host", None))
    if not ssh_host:
        ssh_host = _normalize(getattr(node, "host", None))
    ssh_host = validate_node_host(ssh_host)

    ssh_username = _normalize(
        body.ssh_username if "ssh_username" in updates else getattr(node, "ssh_username", None)
    )
    ssh_port = int(
        (body.ssh_port if "ssh_port" in updates else getattr(node, "ssh_port", None)) or 22
    )
    remote_host = _normalize(
        body.ssh_remote_agent_host
        if "ssh_remote_agent_host" in updates
        else getattr(node, "ssh_remote_agent_host", None)
    ) or "127.0.0.1"
    remote_port = int(
        (
            body.ssh_remote_agent_port
            if "ssh_remote_agent_port" in updates
            else getattr(node, "ssh_remote_agent_port", None)
        )
        or node.port
        or 0
    )

    if "ssh_private_key" in updates:
        key_plain = _normalize(body.ssh_private_key)
        if not key_plain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для SSH transport нужен приватный ключ",
            )
        key_enc = encrypt_secret(key_plain, settings.secret_key)
    else:
        key_enc = str(getattr(node, "ssh_private_key_encrypted", "") or "").strip()
        if not key_enc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для SSH transport сначала задайте приватный ключ",
            )

    if "ssh_passphrase" in updates:
        phrase = _normalize(body.ssh_passphrase)
        phrase_enc = encrypt_secret(phrase, settings.secret_key) if phrase else ""
    else:
        phrase_enc = str(getattr(node, "ssh_passphrase_encrypted", "") or "")

    if not ssh_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ssh_username обязателен для SSH transport",
        )
    if remote_port <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ssh_remote_agent_port обязателен для SSH transport",
        )

    # Negative id keeps preflight tunnels out of the live node session map.
    return SimpleNamespace(
        id=-abs(int(node.id)),
        port=int(node.port or 0),
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_username=ssh_username,
        ssh_private_key_encrypted=key_enc,
        ssh_passphrase_encrypted=phrase_enc,
        ssh_remote_agent_host=remote_host,
        ssh_remote_agent_port=remote_port,
        ssh_host_key=getattr(node, "ssh_host_key", None) or "",
        node_metadata=getattr(node, "node_metadata", None) or "{}",
    )


def _probe_via_ssh(node: Node, body: NodeTransportUpdate, *, api_key: str) -> tuple[bool, str | None, str | None]:
    pool = get_ssh_tunnel_pool()
    probe_node = _build_ssh_probe_node(node, body)
    try:
        ensured = pool.ensure(probe_node)
        local_port = ensured.local_port if hasattr(ensured, "local_port") else int(ensured)
        try:
            if _node_kind(node) == NODE_KIND_PROXY:
                adapter = ProxyNodeAdapter(
                    host="127.0.0.1",
                    port=local_port,
                    api_key=api_key,
                    mtls_enabled=False,
                )
                try:
                    adapter.health()
                finally:
                    adapter.close()
            else:
                adapter = RemoteNodeAdapter(
                    host="127.0.0.1",
                    port=local_port,
                    api_key=api_key,
                    mtls_enabled=False,
                )
                try:
                    adapter.health_check()
                finally:
                    adapter.close()
            return True, "online", None
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                message = str(detail.get("message") or detail.get("detail") or detail)
            else:
                message = str(detail)
            return False, "offline", message
        except Exception as exc:  # noqa: BLE001
            return False, "offline", str(exc)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        return False, "offline", str(exc)
    finally:
        try:
            pool.drop(int(probe_node.id))
        except Exception:
            pass


def preflight_transport_switch(
    db: Session,
    node: Node,
    body: NodeTransportUpdate,
) -> TransportPreflightResult:
    if node.is_local:
        return TransportPreflightResult(
            ok=False,
            current=TRANSPORT_HTTP,
            wanted=_normalize(body.transport).lower(),
            message="Способ связи не применим к локальному узлу",
        )

    wanted = _normalize(body.transport).lower()
    if wanted not in (TRANSPORT_HTTP, TRANSPORT_MTLS, TRANSPORT_SSH):
        return TransportPreflightResult(
            ok=False,
            current=resolve_transport_id(node),
            wanted=wanted or "?",
            message=f"Неизвестный transport: {body.transport}",
        )

    current = resolve_transport_id(node)
    if current == wanted and wanted != TRANSPORT_SSH:
        return TransportPreflightResult(
            ok=True,
            current=current,
            wanted=wanted,
            message="Узел уже на этом способе связи",
        )

    if wanted == TRANSPORT_SSH and not is_node_ssh_transport_enabled(db):
        return TransportPreflightResult(
            ok=False,
            current=current,
            wanted=wanted,
            message=module_disabled_message("node_ssh_transport"),
            hint="Включите модуль «SSH transport узлов» в Настройки → Модули.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    if current == TRANSPORT_SSH and wanted == TRANSPORT_MTLS:
        return TransportPreflightResult(
            ok=False,
            current=current,
            wanted=wanted,
            message="Нельзя включить mTLS напрямую с SSH",
            hint="Сначала переключите на HTTP (публичный host:port), затем на HTTPS + mTLS.",
        )

    if wanted == TRANSPORT_SSH:
        updates = body.model_dump(exclude_unset=True)
        has_key = bool(_normalize(body.ssh_private_key)) if "ssh_private_key" in updates else bool(
            str(getattr(node, "ssh_private_key_encrypted", "") or "").strip()
        )
        if not has_key:
            return TransportPreflightResult(
                ok=False,
                current=current,
                wanted=wanted,
                message="Для SSH transport сначала задайте приватный ключ",
            )
        username = _normalize(
            body.ssh_username if "ssh_username" in updates else getattr(node, "ssh_username", None)
        )
        if not username:
            return TransportPreflightResult(
                ok=False,
                current=current,
                wanted=wanted,
                message="ssh_username обязателен для SSH transport",
            )

    api_key = get_api_key_plain(node)
    if not api_key:
        return TransportPreflightResult(
            ok=False,
            current=current,
            wanted=wanted,
            message="API-ключ узла недоступен",
            hint="Задайте API-ключ узла и повторите проверку.",
        )

    # Proxy mTLS is flag-only — no live provision probe.
    if wanted == TRANSPORT_MTLS and _node_kind(node) == NODE_KIND_PROXY:
        return TransportPreflightResult(
            ok=True,
            current=current,
            wanted=wanted,
            message="Можно отметить mTLS для proxy_agent (сертификаты настраиваются вручную)",
        )

    if wanted == TRANSPORT_HTTP:
        ok, probe_status, probe_error = _probe_direct(node, api_key=api_key, mtls=False)
        if ok:
            return TransportPreflightResult(
                ok=True,
                current=current,
                wanted=wanted,
                message="Агент отвечает по HTTP на публичном host:port — переключение возможно",
                probe_status=probe_status,
            )
        return TransportPreflightResult(
            ok=False,
            current=current,
            wanted=wanted,
            message="Агент не отвечает по HTTP на публичном host:port",
            hint=(
                "Убедитесь, что node agent слушает не только 127.0.0.1 и что firewall пропускает порт. "
                "Если агент ещё на mTLS — сначала переведите его на обычный HTTP."
            ),
            probe_status=probe_status,
            probe_error=probe_error,
        )

    if wanted == TRANSPORT_MTLS:
        ok, probe_status, probe_error = _probe_direct(node, api_key=api_key, mtls=False)
        if ok:
            return TransportPreflightResult(
                ok=True,
                current=current,
                wanted=wanted,
                message="Агент доступен по HTTP — можно выдавать mTLS-сертификаты",
                probe_status=probe_status,
            )
        return TransportPreflightResult(
            ok=False,
            current=current,
            wanted=wanted,
            message="Для включения mTLS агент должен быть доступен по HTTP",
            hint="Проверьте host:port и API-ключ. Provision идёт напрямую, не через SSH.",
            probe_status=probe_status,
            probe_error=probe_error,
        )

    # wanted == SSH
    try:
        ok, probe_status, probe_error = _probe_via_ssh(node, body, api_key=api_key)
    except HTTPException as exc:
        detail = str(exc.detail)
        return TransportPreflightResult(
            ok=False,
            current=current,
            wanted=wanted,
            message=detail,
            hint="Проверьте SSH-хост, пользователя и приватный ключ.",
        )
    if ok:
        return TransportPreflightResult(
            ok=True,
            current=current,
            wanted=wanted,
            message="SSH-туннель и HTTP к агенту на 127.0.0.1 работают — переключение возможно",
            probe_status=probe_status,
        )
    return TransportPreflightResult(
        ok=False,
        current=current,
        wanted=wanted,
        message="Не удалось достучаться до агента через SSH-туннель",
        hint=(
            "Проверьте SSH-доступ и что агент слушает HTTP на 127.0.0.1 (порт узла). "
            "Если агент на mTLS — сначала переведите его на обычный HTTP."
        ),
        probe_status=probe_status,
        probe_error=probe_error,
    )
