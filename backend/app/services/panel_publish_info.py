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
    use_https: bool = False,
) -> PublishModeKey:
    """Publish mode key: reverse_proxy, direct_https, direct_http, or local_http."""
    host = (backend_host or "127.0.0.1").strip() or "127.0.0.1"
    if behind_nginx:
        return "reverse_proxy"
    if use_https and not _is_loopback_bind(host):
        return "direct_https"
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
    use_https = _parse_bool(gv("USE_HTTPS", "false"))
    host = gv("BACKEND_HOST", "127.0.0.1") or "127.0.0.1"
    mode = resolve_panel_publish_mode(behind_nginx=behind, backend_host=host, use_https=use_https)
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
    behind_env = gv("BEHIND_NGINX", "")
    if behind_env:
        behind_nginx = _parse_bool(behind_env)
    else:
        behind_nginx = settings.behind_nginx
    domain = gv("DOMAIN", "") or settings.domain
    trusted = gv("TRUSTED_PROXY_IPS", "") or settings.trusted_proxy_ips
    forwarded = gv("FORWARDED_ALLOW_IPS", "") or settings.forwarded_allow_ips
    enforce_https = _parse_bool(gv("ENFORCE_HTTPS", ""), default=settings.enforce_https)
    use_https = _parse_bool(gv("USE_HTTPS", "false"))
    ssl_cert = gv("SSL_CERT", "")
    ssl_key = gv("SSL_KEY", "")
    cookie_secure = _parse_bool(
        gv("REFRESH_TOKEN_COOKIE_SECURE", ""),
        default=settings.refresh_token_cookie_secure,
    )
    https_public_port_raw = gv("HTTPS_PUBLIC_PORT", "") or str(settings.https_public_port)
    try:
        https_public_port = int(https_public_port_raw)
    except ValueError:
        https_public_port = settings.https_public_port

    mode_key = resolve_panel_publish_mode(
        behind_nginx=behind_nginx,
        backend_host=backend_host,
        use_https=use_https,
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
    elif mode_key == "direct_https":
        mode_title = "HTTPS напрямую на uvicorn (без Nginx)"
        bullet_points.append(
            f"Uvicorn слушает TLS на {internal_url.replace('http://', 'https://')} — cert на приложении."
        )
        if domain:
            port_suffix = "" if https_public_port == 443 else f":{https_public_port}"
            guess = f"https://{domain}{port_suffix}/"
            primary_urls.append(
                {"label": "Публичный URL (HTTPS на uvicorn)", "url": guess}
            )
            bullet_points.append(f"DOMAIN={domain}; HTTPS_PUBLIC_PORT={https_public_port}.")
        if ssl_cert:
            bullet_points.append(f"SSL_CERT: {ssl_cert}")
        bullet_points.append(
            "После обновления cert (certbot и т.п.) перезапустите панель: systemctl restart adminpanelaz"
        )
        bullet_points.append(
            "Смена режима: sudo ./scripts/nginx-setup.sh (uvicorn-custom / uvicorn-le)."
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
        {"label": "USE_HTTPS (TLS на uvicorn)", "value": "да" if use_https else "нет", "mono": False},
        {"label": "DOMAIN (для nginx / подсказок)", "value": domain or "—", "mono": bool(domain)},
        {"label": "HTTPS_PUBLIC_PORT", "value": str(https_public_port), "mono": True},
        {"label": "ENFORCE_HTTPS", "value": "да" if enforce_https else "нет", "mono": False},
        {"label": "REFRESH_TOKEN_COOKIE_SECURE", "value": "да" if cookie_secure else "нет", "mono": False},
        {"label": "TRUSTED_PROXY_IPS", "value": trusted or "—", "mono": True},
        {"label": "FORWARDED_ALLOW_IPS", "value": forwarded or "—", "mono": True},
    ]
    if ssl_cert:
        env_rows.insert(7, {"label": "SSL_CERT", "value": ssl_cert, "mono": True})
    if ssl_key:
        insert_at = 8 if ssl_cert else 7
        env_rows.insert(insert_at, {"label": "SSL_KEY", "value": ssl_key, "mono": True})

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
        "active_publish_mode": resolve_active_publish_mode_key(
            mode_key=mode_key,
            ssl_cert=ssl_cert,
        ),
    }


def resolve_active_publish_mode_key(*, mode_key: str, ssl_cert: str) -> str | None:
    """Best-effort mapping of runtime mode to publish wizard key."""
    if mode_key == "direct_http":
        return "http_direct"
    if mode_key == "local_http":
        return None
    if mode_key == "direct_https":
        cert = ssl_cert.lower()
        if "/etc/letsencrypt/" in cert:
            return "uvicorn_le"
        if "adminpanelaz" in cert:
            return "uvicorn_selfsigned"
        if ssl_cert:
            return "uvicorn_custom"
        return "uvicorn_selfsigned"
    if mode_key == "reverse_proxy":
        if ssl_cert and "letsencrypt" not in ssl_cert.lower() and "adminpanelaz" not in ssl_cert.lower():
            return "nginx_custom"
        return "nginx_le"
    return None


def build_vpn_network_publish_modes() -> list[dict[str, str | bool | None]]:
    """Publish modes available from the settings wizard."""
    return [
        {
            "key": "nginx_le",
            "title": "Nginx + Let's Encrypt",
            "description": "Рекомендуемый режим: TLS на Nginx, uvicorn на loopback.",
            "requires_domain": True,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": True,
            "uses_uvicorn_https_port": False,
            "warning": None,
        },
        {
            "key": "nginx_selfsigned",
            "title": "Nginx + самоподписанный SSL",
            "description": "HTTPS через Nginx с локальным сертификатом (для тестов или LAN).",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": True,
            "uses_uvicorn_https_port": False,
            "warning": None,
        },
        {
            "key": "nginx_custom",
            "title": "Nginx + собственные сертификаты",
            "description": "TLS на Nginx с вашими cert/key (certbot или свои файлы).",
            "requires_domain": True,
            "requires_email": False,
            "requires_ssl_cert": True,
            "uses_nginx_ports": True,
            "uses_uvicorn_https_port": False,
            "warning": None,
        },
        {
            "key": "uvicorn_le",
            "title": "HTTPS на uvicorn + Let's Encrypt",
            "description": "TLS на приложении, standalone certbot, без Nginx.",
            "requires_domain": True,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": False,
            "uses_uvicorn_https_port": True,
            "warning": None,
        },
        {
            "key": "uvicorn_custom",
            "title": "HTTPS на uvicorn + свои сертификаты",
            "description": "TLS на приложении без Nginx — укажите пути к cert/key (certbot или свои файлы).",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": True,
            "uses_nginx_ports": False,
            "uses_uvicorn_https_port": True,
            "warning": None,
        },
        {
            "key": "uvicorn_selfsigned",
            "title": "HTTPS на uvicorn + самоподписанный",
            "description": "TLS на приложении с локальным сертификатом (тесты / LAN).",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": False,
            "uses_uvicorn_https_port": True,
            "warning": "Telegram Mini App не работает с самоподписанным сертификатом.",
        },
        {
            "key": "http_direct",
            "title": "Прямой HTTP (без Nginx)",
            "description": "Uvicorn слушает 0.0.0.0 — только для LAN/тестов.",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": False,
            "uses_uvicorn_https_port": False,
            "warning": "Не используйте в интернете без firewall. Включите блок на порту панели в разделе «Безопасность».",
        },
    ]
