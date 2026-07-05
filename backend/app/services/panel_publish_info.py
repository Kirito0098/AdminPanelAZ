"""Panel publish summary (port, HTTPS, Nginx / reverse proxy) for AdminPanelAZ."""

from __future__ import annotations

import os
from typing import Callable
from urllib.parse import urlparse

from fastapi import Request

from app.config import Settings

PublishModeKey = str
GetEnvValue = Callable[[str, str], str]

WHITELIST_PORT_FIREWALL_MODES = frozenset({"direct_http"})


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback_bind(bind: str) -> bool:
    return bind in {"127.0.0.1", "localhost", "::1"}


def resolve_panel_publish_mode(
    *,
    behind_nginx: bool,
    backend_host: str,
) -> PublishModeKey:
    """Publish mode key: reverse_proxy, direct_http, or local_http."""
    host = (backend_host or "127.0.0.1").strip() or "127.0.0.1"
    if behind_nginx:
        return "reverse_proxy"
    if _is_loopback_bind(host):
        return "local_http"
    return "direct_http"


def is_whitelist_port_firewall_applicable(*, get_env_value: GetEnvValue | None = None) -> bool:
    """iptables whitelist on BACKEND_PORT: direct HTTP on 0.0.0.0, not behind Nginx."""

    def gv(key: str, default: str = "") -> str:
        if get_env_value is not None:
            return str(get_env_value(key, default) or default or "").strip()
        return str(os.getenv(key, default) or default or "").strip()

    behind = _parse_bool(gv("BEHIND_NGINX", "false"))
    host = gv("BACKEND_HOST", "127.0.0.1") or "127.0.0.1"
    mode = resolve_panel_publish_mode(behind_nginx=behind, backend_host=host)
    return mode in WHITELIST_PORT_FIREWALL_MODES


def _host_has_explicit_port(host: str) -> bool:
    if host.startswith("["):
        return "]:" in host
    if ":" not in host:
        return False
    return host.rsplit(":", 1)[-1].isdigit()


def _append_public_https_port(host: str, *, proto: str, https_public_port: int) -> str:
    if _host_has_explicit_port(host):
        return host
    default_port = 443 if proto == "https" else 80
    if https_public_port == default_port:
        return host
    return f"{host}:{https_public_port}"


def resolve_request_url_root(
    request: Request,
    *,
    behind_nginx: bool,
    https_public_port: int | None = None,
) -> str:
    """Current browser URL root, honoring reverse-proxy forwarded headers."""
    if https_public_port is None:
        from app.config import get_settings

        https_public_port = get_settings().https_public_port

    if behind_nginx:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
        host = (
            request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or request.url.netloc
            or ""
        ).split(",")[0].strip()
        if proto and host:
            if proto == "https":
                host = _append_public_https_port(host, proto=proto, https_public_port=https_public_port)
            return f"{proto}://{host}/"
    return str(request.base_url)


def resolve_public_base_url(request: Request) -> str:
    """Public panel origin without trailing slash (for one-time download links, webhooks, etc.)."""
    from app.config import get_settings

    settings = get_settings()
    return resolve_request_url_root(
        request,
        behind_nginx=settings.behind_nginx,
        https_public_port=settings.https_public_port,
    ).rstrip("/")


def build_panel_publish_context(
    *,
    get_env_value: GetEnvValue,
    request_url: str | None,
    settings: Settings,
) -> dict:
    """Build VPN network tab context from .env and runtime settings."""

    def gv(key: str, default: str = "") -> str:
        return str(get_env_value(key, default) or default or "").strip()

    backend_host = gv("BACKEND_HOST", "127.0.0.1") or "127.0.0.1"
    backend_port = gv("BACKEND_PORT", "8000") or "8000"
    behind_nginx = _parse_bool(gv("BEHIND_NGINX", "false")) or settings.behind_nginx
    domain = gv("DOMAIN", "") or settings.domain
    trusted = gv("TRUSTED_PROXY_IPS", "") or settings.trusted_proxy_ips
    forwarded = gv("FORWARDED_ALLOW_IPS", "") or settings.forwarded_allow_ips
    enforce_https = _parse_bool(gv("ENFORCE_HTTPS", ""), default=settings.enforce_https)
    cookie_secure = _parse_bool(
        gv("REFRESH_TOKEN_COOKIE_SECURE", ""),
        default=settings.refresh_token_cookie_secure,
    )

    mode_key = resolve_panel_publish_mode(
        behind_nginx=behind_nginx,
        backend_host=backend_host,
    )

    internal_url = f"http://{backend_host}:{backend_port}/"

    parsed = urlparse(request_url or "")
    current_url = ""
    if parsed.scheme and parsed.netloc:
        current_url = f"{parsed.scheme}://{parsed.netloc}/"

    primary_urls: list[dict[str, str]] = []
    if current_url:
        primary_urls.append({"label": "Текущий адрес в браузере", "url": current_url.rstrip("/") + "/"})

    bullet_points: list[str] = []

    if mode_key == "reverse_proxy":
        mode_title = "За reverse proxy (Nginx + HTTPS)"
        bullet_points.append(
            "Uvicorn слушает loopback — снаружи доступ через Nginx или другой прокси с TLS."
        )
        bullet_points.append(
            f"Внутренний upstream: http://{backend_host}:{backend_port}/ (proxy_pass к BACKEND_PORT)."
        )
        if domain:
            guess = f"https://{domain}/"
            primary_urls.append(
                {"label": "Типичный публичный URL (HTTPS на nginx, порты 80/443)", "url": guess}
            )
            bullet_points.append(
                f"В .env указан DOMAIN — ожидаемый внешний адрес: {guess} "
                "(если nginx на стандартном 443, порт в URL не указывается)."
            )
        else:
            bullet_points.append(
                "DOMAIN в .env пуст — внешний URL зависит от конфига nginx; "
                "ориентируйтесь на адрес, по которому заходите сейчас."
            )
        if cookie_secure:
            bullet_points.append(
                "REFRESH_TOKEN_COOKIE_SECURE=true — типично для схемы «HTTPS снаружи, HTTP внутри»."
            )
        if trusted:
            bullet_points.append(f"Доверенные прокси (TRUSTED_PROXY_IPS): {trusted}.")
        bullet_points.append(
            "Смена режима HTTPS/Nginx: sudo ./scripts/nginx-setup.sh на сервере."
        )
    elif mode_key == "local_http":
        mode_title = "HTTP только на localhost"
        bullet_points.append(
            f"Панель слушает {internal_url} — доступ только с этого сервера (BACKEND_HOST loopback)."
        )
        bullet_points.append(
            "Для публикации в интернет используйте scripts/nginx-setup.sh или установщик."
        )
    else:
        mode_title = "Прямой HTTP к приложению"
        bullet_points.append(
            f"Панель слушает {internal_url} без TLS на этом уровне (BACKEND_HOST не loopback)."
        )
        bullet_points.append(
            "Не используйте в интернете без firewall. Для HTTPS настройте Nginx через nginx-setup.sh."
        )
        if enforce_https:
            bullet_points.append("ENFORCE_HTTPS=true — middleware перенаправляет HTTP на HTTPS.")

    env_rows = [
        {"label": "BACKEND_PORT (порт uvicorn)", "value": backend_port, "mono": True},
        {"label": "BACKEND_HOST", "value": backend_host, "mono": True},
        {"label": "BEHIND_NGINX", "value": "да" if behind_nginx else "нет", "mono": False},
        {"label": "DOMAIN (для nginx / подсказок)", "value": domain or "—", "mono": bool(domain)},
        {"label": "ENFORCE_HTTPS", "value": "да" if enforce_https else "нет", "mono": False},
        {"label": "REFRESH_TOKEN_COOKIE_SECURE", "value": "да" if cookie_secure else "нет", "mono": False},
        {"label": "TRUSTED_PROXY_IPS", "value": trusted or "—", "mono": True},
        {"label": "FORWARDED_ALLOW_IPS", "value": forwarded or "—", "mono": True},
    ]

    dedup_urls: list[dict[str, str]] = []
    seen_url: set[str] = set()
    for entry in primary_urls:
        url = entry.get("url") or ""
        if not url or url in seen_url:
            continue
        seen_url.add(url)
        dedup_urls.append(entry)

    return {
        "mode_key": mode_key,
        "mode_title": mode_title,
        "bullet_points": bullet_points,
        "primary_urls": dedup_urls,
        "internal_url": internal_url,
        "env_rows": env_rows,
        "backend_port": backend_port,
    }


def build_vpn_network_publish_modes() -> list[dict[str, str | bool | None]]:
    """Publish modes available from the settings wizard."""
    return [
        {
            "key": "nginx_le",
            "title": "Nginx + Let's Encrypt",
            "description": "Рекомендуемый режим: TLS на Nginx, uvicorn на loopback.",
            "requires_domain": True,
            "requires_email": False,
            "warning": None,
        },
        {
            "key": "nginx_selfsigned",
            "title": "Nginx + самоподписанный SSL",
            "description": "HTTPS через Nginx с локальным сертификатом (для тестов или LAN).",
            "requires_domain": False,
            "requires_email": False,
            "warning": None,
        },
        {
            "key": "http_direct",
            "title": "Прямой HTTP (без Nginx)",
            "description": "Uvicorn слушает 0.0.0.0 — только для LAN/тестов.",
            "requires_domain": False,
            "requires_email": False,
            "warning": "Не используйте в интернете без firewall. Включите блок на порту панели в разделе «Безопасность».",
        },
    ]
