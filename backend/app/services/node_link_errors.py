"""Classify panel↔node_agent / proxy_agent link failures into stable codes."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

CODE_AUTH = "node_auth"
CODE_TLS_MISMATCH = "node_tls_mismatch"
CODE_UNREACHABLE = "node_unreachable"
CODE_TIMEOUT = "node_timeout"
CODE_ERROR = "node_error"
CODE_SSH_AUTH = "node_ssh_auth"
CODE_SSH_UNREACHABLE = "node_ssh_unreachable"
CODE_SSH_TUNNEL = "node_ssh_tunnel"

_HINTS = {
    CODE_AUTH: "Проверьте API-ключ узла (X-Node-Key) и NODE_AGENT_ALLOWED_IPS.",
    CODE_TLS_MISMATCH: "Проверьте mTLS: схема HTTP/HTTPS панели должна совпадать с агентом.",
    CODE_UNREACHABLE: "Проверьте host:port, firewall и что агент запущен.",
    CODE_TIMEOUT: "Проверьте сеть и доступность порта агента.",
    CODE_ERROR: "Смотрите сообщение агента; при повторе — логи node agent.",
    CODE_SSH_AUTH: "Проверьте SSH username, private key и passphrase для узла.",
    CODE_SSH_UNREACHABLE: "Проверьте SSH host:port, firewall и доступность узла по SSH.",
    CODE_SSH_TUNNEL: "Проверьте SSH tunnel и remote agent host:port на узле.",
}


def link_error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "hint": _HINTS.get(code, _HINTS[CODE_ERROR])}


def http_status_for_code(code: str) -> int:
    if code == CODE_TIMEOUT:
        return status.HTTP_504_GATEWAY_TIMEOUT
    return status.HTTP_502_BAD_GATEWAY


def raise_link_error(code: str, message: str) -> None:
    raise HTTPException(
        status_code=http_status_for_code(code),
        detail=link_error_detail(code, message),
    )


def classify_request_error(exc: httpx.RequestError, *, mtls_enabled: bool) -> tuple[str, str]:
    msg = str(exc).lower()
    if isinstance(exc, httpx.TimeoutException):
        return CODE_TIMEOUT, "Таймаут подключения к агенту узла — проверьте firewall и порт"
    ssl_msg = _ssl_message(msg, mtls_enabled=mtls_enabled)
    if ssl_msg:
        return CODE_TLS_MISMATCH, ssl_msg
    if isinstance(exc, httpx.ConnectError):
        return CODE_UNREACHABLE, f"Не удалось подключиться к агенту узла: {exc}"
    if isinstance(exc, httpx.RemoteProtocolError) or "disconnected without sending a response" in msg:
        if not mtls_enabled:
            return (
                CODE_TLS_MISMATCH,
                "Сервер закрыл соединение без ответа. Вероятно, на узле включён mTLS (HTTPS), "
                "а панель обращается по HTTP. Включите mTLS для узла на странице «Узлы».",
            )
        return (
            CODE_TLS_MISMATCH,
            "Сервер закрыл соединение без ответа. Проверьте mTLS-сертификаты панели.",
        )
    return CODE_UNREACHABLE, f"Узел недоступен: {exc}"


def classify_http_status(status_code: int, detail: Any, *, mtls_enabled: bool) -> tuple[str, str]:
    text = _detail_to_text(detail)
    if status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        if status_code == status.HTTP_401_UNAUTHORIZED:
            return CODE_AUTH, "Неверный API-ключ узла (заголовок X-Node-Key)"
        return CODE_AUTH, text or "Доступ запрещён — проверьте NODE_AGENT_ALLOWED_IPS на узле"
    lower = text.lower()
    ssl_msg = _ssl_message(lower, mtls_enabled=mtls_enabled)
    if ssl_msg:
        return CODE_TLS_MISMATCH, ssl_msg
    return CODE_ERROR, text or f"Ошибка агента HTTP {status_code}"


def parse_link_error_from_http_detail(detail: Any) -> dict[str, str] | None:
    if isinstance(detail, dict) and detail.get("code") and detail.get("message"):
        return {
            "code": str(detail["code"]),
            "message": str(detail["message"]),
            "hint": str(detail.get("hint") or _HINTS.get(str(detail["code"]), "")),
        }
    return None


def classify_ssh_error(exc: Exception) -> tuple[str, str] | None:
    code = str(getattr(exc, "code", "") or "").strip()
    if code in {CODE_SSH_AUTH, CODE_SSH_UNREACHABLE, CODE_SSH_TUNNEL}:
        message = str(exc).strip() or "SSH transport error"
        return code, message
    return None


def _detail_to_text(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        if "message" in detail:
            return str(detail.get("message") or "")
        if "detail" in detail:
            return _detail_to_text(detail.get("detail"))
        return str(detail)
    if isinstance(detail, list) and detail:
        return _detail_to_text(detail[0])
    return str(detail or "")


def _ssl_message(msg: str, *, mtls_enabled: bool) -> str | None:
    if "wrong version number" in msg or "wrong_version_number" in msg:
        if mtls_enabled:
            return (
                "Ошибка SSL (WRONG_VERSION_NUMBER): узел, вероятно, отвечает по HTTP, "
                "а панель подключается по HTTPS. Отключите mTLS для узла или настройте HTTPS на агенте."
            )
        return (
            "Ошибка SSL (WRONG_VERSION_NUMBER): узел, вероятно, отвечает по HTTPS (mTLS), "
            "а панель подключается по HTTP. Включите mTLS для узла на странице «Узлы»."
        )
    if "certificate verify failed" in msg or "certificate_verify_failed" in msg:
        return (
            "Ошибка проверки сертификата агента. Проверьте CA и клиентский сертификат панели "
            "или повторно включите mTLS для узла."
        )
    if "certificate has expired" in msg or "certificate expired" in msg or "certificate_expired" in msg:
        return "Сертификат mTLS истёк. Повторно включите mTLS для узла на странице «Узлы»."
    if "self signed certificate" in msg or "self-signed certificate" in msg:
        return (
            "Агент использует самоподписанный или неизвестный сертификат. "
            "Убедитесь, что CA панели совпадает с CA на узле."
        )
    if "unknown ca" in msg or "tlsv1_alert_unknown_ca" in msg:
        return (
            "Агент не доверяет клиентскому сертификату панели (unknown CA). "
            "Повторно включите mTLS для узла."
        )
    if (
        "handshake failure" in msg
        or "sslv3_alert_handshake_failure" in msg
        or "alert handshake failure" in msg
    ):
        if mtls_enabled:
            return (
                "Ошибка TLS handshake с агентом. Проверьте mTLS на узле, общий CA и доступность порта."
            )
        return "Ошибка TLS handshake: узел, вероятно, ожидает mTLS. Включите mTLS на странице «Узлы»."
    if "ssl" in msg or "tls" in msg:
        if mtls_enabled:
            return "Ошибка SSL/mTLS при подключении к агенту. Проверьте сертификаты и HTTPS на узле."
        return (
            "Ошибка SSL при подключении по HTTP — узел, вероятно, отвечает по HTTPS (mTLS). "
            "Включите mTLS для узла на странице «Узлы»."
        )
    return None
