"""Panel publish summary (port, HTTPS, Nginx / reverse proxy) for AdminPanelAZ."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from fastapi import Request

from app.config import Settings

PublishModeKey = str
GetEnvValue = Callable[[str, str], str]

WHITELIST_PORT_FIREWALL_MODES = frozenset({"direct_http"})

SELF_SIGNED_CERT_PATH = Path("/etc/ssl/certs/adminpanelaz.crt")
SELF_SIGNED_KEY_PATH = Path("/etc/ssl/private/adminpanelaz.key")
LETSENCRYPT_LIVE_DIR = Path("/etc/letsencrypt/live")
PANEL_SYSTEMD_UNIT = "adminpanelaz"
PANEL_PROCESS_RE = re.compile(r"uvicorn|adminpanelaz|python.*app\.main", re.I)
NGINX_PROCESS_RE = re.compile(r"nginx", re.I)
PORT_ROLE_BACKEND = "backend"
PORT_ROLE_NGINX_HTTPS = "nginx_https"
PORT_ROLE_NGINX_HTTP = "nginx_http"


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
    access_path_value: str | None = None,
) -> str:
    """Current browser URL root, honoring reverse-proxy forwarded headers."""
    from app.config import get_settings
    from app.services.panel_paths import append_access_path_to_url_root

    if https_public_port is None or access_path_value is None:
        cfg = get_settings()
        if https_public_port is None:
            https_public_port = cfg.https_public_port
        if access_path_value is None:
            access_path_value = cfg.access_path

    class _PathSettings:
        access_path = access_path_value or ""

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
            return append_access_path_to_url_root(f"{proto}://{host}/", _PathSettings())
    base = str(request.base_url)
    return append_access_path_to_url_root(base, _PathSettings())


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

    access_path_value = gv("ACCESS_PATH", "") or settings.access_path

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
            guess = build_publish_access_url(
                publish_mode=gv("PUBLISH_MODE", "nginx_le"),
                domain=domain,
                backend_port=backend_port,
                https_public_port=https_public_port,
                behind_nginx=True,
                access_path_value=access_path_value,
            ) or f"https://{domain}/"
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
        {"label": "ACCESS_PATH (подпуть на домене)", "value": access_path_value or "—", "mono": True},
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
            publish_mode=gv("PUBLISH_MODE", ""),
        ),
        "shared_domain_foreign_vhost": nginx_is_foreign_vhost_for_domain(domain) if domain else False,
        "shared_domain_status_openvpn": nginx_is_status_openvpn_on_domain(domain) if domain else False,
    }


def resolve_active_publish_mode_key(
    *,
    mode_key: str,
    ssl_cert: str,
    publish_mode: str = "",
) -> str | None:
    """Best-effort mapping of runtime mode to publish wizard key."""
    explicit = (publish_mode or "").strip()
    if explicit:
        return explicit
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


def is_nginx_installed() -> bool:
    return shutil.which("nginx") is not None


def nginx_listens_on_443() -> bool:
    if not is_nginx_installed():
        return False
    try:
        result = subprocess.run(
            ["ss", "-tln"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return ":443 " in (result.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def nginx_has_vhost_for_domain(domain: str) -> bool:
    domain = (domain or "").strip().split(":")[0]
    if not domain or not is_nginx_installed():
        return False
    sites_dir = Path("/etc/nginx/sites-enabled")
    if not sites_dir.is_dir():
        return False
    basename = domain.replace(".", "_")
    if (sites_dir / basename).exists():
        return True
    try:
        for path in sites_dir.iterdir():
            if not path.is_file() and not path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if f"server_name {domain}" in text or f"server_name {domain};" in text:
                return True
    except OSError:
        return False
    return False


def _nginx_is_our_panel_vhost_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "AdminPanelAZ —" in text


def _nginx_iter_vhost_files_for_domain(domain: str) -> list[Path]:
    domain = (domain or "").strip().split(":")[0]
    if not domain:
        return []
    ordered: list[Path] = []
    seen: set[str] = set()
    for root in (Path("/etc/nginx/sites-enabled"), Path("/etc/nginx/sites-available")):
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir(), key=lambda p: p.name):
            if not path.is_file() and not path.is_symlink():
                continue
            key = str(path)
            if key in seen:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if f"server_name {domain}" in text or f"server_name {domain};" in text:
                seen.add(key)
                ordered.append(path)
    return ordered


def _nginx_is_status_openvpn_vhost_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    if "# Created by StatusOpenVPN" in text:
        return True
    return "location /status/" in text and "X-Script-Name /status" in text


def nginx_is_status_openvpn_on_domain(domain: str) -> bool:
    domain = (domain or "").strip().split(":")[0]
    if not domain:
        return False
    enabled = Path("/etc/nginx/sites-enabled")
    if not enabled.is_dir():
        return False
    for path in enabled.iterdir():
        if not path.is_file() and not path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if f"server_name {domain}" not in text and f"server_name {domain};" not in text:
            continue
        if _nginx_is_status_openvpn_vhost_file(path):
            return True
    return False


def nginx_list_foreign_vhosts_for_domain(domain: str) -> list[Path]:
    return [
        path
        for path in _nginx_iter_vhost_files_for_domain(domain)
        if not _nginx_is_our_panel_vhost_file(path)
    ]


def nginx_find_foreign_vhost_for_domain(domain: str) -> Path | None:
    foreign = nginx_list_foreign_vhosts_for_domain(domain)
    return foreign[0] if foreign else None


def nginx_is_foreign_vhost_for_domain(domain: str) -> bool:
    return nginx_find_foreign_vhost_for_domain(domain) is not None


def build_subpath_publish_warnings(
    *,
    domain: str,
    access_path: str,
    publish_mode: str,
) -> list[str]:
    warnings: list[str] = []
    domain_host = (domain or "").strip().split(":")[0]
    path = (access_path or "").strip()
    if not path:
        if domain_host and nginx_is_foreign_vhost_for_domain(domain_host):
            warnings.append(
                f"На домене {domain_host} уже есть другой nginx-сайт. "
                "Для совместного хостинга укажите ACCESS_PATH, например /panel."
            )
        return warnings
    if publish_mode.startswith("uvicorn_") or publish_mode == "http_direct":
        warnings.append(
            "ACCESS_PATH поддерживается только с nginx reverse proxy. "
            "Выберите режим nginx_* или настройте внешний nginx вручную."
        )
    if domain_host and nginx_is_status_openvpn_on_domain(domain_host):
        warnings.append(
            f"На домене {domain_host} обнаружен StatusOpenVPN (/status/) — "
            f"панель можно встроить по пути {path} рядом, не затрагивая /status/."
        )
        warnings.append(
            "Включите интеграцию со StatusOpenVPN в мастере публикации: "
            "будет изменён только активный vhost в sites-enabled (с бэкапом)."
        )
    elif domain_host and nginx_is_foreign_vhost_for_domain(domain_host):
        foreign = nginx_find_foreign_vhost_for_domain(domain_host)
        foreign_name = foreign.name if foreign else domain_host
        warnings.append(
            f"Домен {domain_host} уже обслуживается сайтом «{foreign_name}» — "
            f"панель будет встроена по пути {path} (рядом с другими проектами)."
        )
        warnings.append(
            "Выделенный vhost панели на этом домене будет удалён, если он есть."
        )
    warnings.append(
        "Публикация по подпути — дополнительная мера, не замена 2FA и сильного пароля."
    )
    return warnings


def build_uvicorn_publish_warnings(
    *,
    domain: str,
    backend_port: str | int,
    ssl_cert_suggestions: list[dict[str, str]] | None = None,
) -> list[str]:
    """Warnings when publishing via uvicorn HTTPS on a server that already uses nginx:443."""
    warnings: list[str] = []
    domain_host = (domain or "").strip().split(":")[0]
    try:
        port = int(backend_port)
    except (TypeError, ValueError):
        port = 8000

    has_le = letsencrypt_exists_for_domain(domain_host)
    if has_le and domain_host:
        warnings.append(
            f"Сертификат Let's Encrypt для {domain_host} уже есть — повторный выпуск не нужен."
        )

    if nginx_listens_on_443() and port != 443 and domain_host:
        if not nginx_has_vhost_for_domain(domain_host):
            warnings.append(
                f"Nginx на 443 без сайта для {domain_host} — открывайте https://{domain_host}:{port}/"
            )
        else:
            warnings.append(
                f"https://{domain_host}/ идёт в Nginx, панель — https://{domain_host}:{port}/"
            )

    return warnings


def build_publish_access_url(
    *,
    publish_mode: str,
    domain: str,
    backend_port: str | int,
    https_public_port: str | int | None = None,
    behind_nginx: bool = False,
    access_path_value: str = "",
) -> str | None:
    """Primary browser URL after applying a publish mode."""
    from app.services.panel_paths import append_access_path_to_url_root, normalize_access_path

    mode = (publish_mode or "").strip()
    domain_host = (domain or "").strip().split(":")[0]
    if not domain_host and mode != "http_direct":
        return None
    try:
        port = int(backend_port)
    except (TypeError, ValueError):
        port = 8000
    pub = int(https_public_port or (443 if behind_nginx else port))

    class _PathSettings:
        access_path = normalize_access_path(access_path_value)

    if mode.startswith("nginx_") or (behind_nginx and not mode.startswith("uvicorn_")):
        root = f"https://{domain_host}/" if pub == 443 else f"https://{domain_host}:{pub}/"
        return append_access_path_to_url_root(root, _PathSettings())
    if mode == "http_direct":
        root = f"http://{domain_host}:{port}/" if domain_host else f"http://<сервер>:{port}/"
        return append_access_path_to_url_root(root, _PathSettings())
    if mode.startswith("uvicorn_"):
        le_cert = Path(f"/etc/letsencrypt/live/{domain_host}/fullchain.pem")
        if port != 443 and le_cert.is_file():
            return append_access_path_to_url_root(f"https://{domain_host}/", _PathSettings())
        root = f"https://{domain_host}/" if port == 443 else f"https://{domain_host}:{port}/"
        return append_access_path_to_url_root(root, _PathSettings())
    return None


def panel_restart_command() -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", PANEL_SYSTEMD_UNIT],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return f"sudo systemctl restart {PANEL_SYSTEMD_UNIT}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "sudo ./start.sh restart"


def _parse_ss_listeners(ss_output: str, port: int) -> list[str]:
    port_marker = f":{port}"
    listeners: list[str] = []
    for line in ss_output.splitlines():
        if port_marker in line:
            listeners.append(line.strip())
    return listeners


def _listener_process_hint(listener: str) -> str:
    match = re.search(r'users:\(\("([^"]+)"', listener)
    if match:
        return match.group(1)
    if NGINX_PROCESS_RE.search(listener):
        return "nginx"
    if PANEL_PROCESS_RE.search(listener):
        return "панель"
    return "другой процесс"


def inspect_tcp_port(port: int, *, role: str = PORT_ROLE_BACKEND) -> dict[str, str | bool | int | None]:
    """Check whether a TCP port is listening and who owns it."""
    if port < 1 or port > 65535:
        return {
            "port": port,
            "status": "unknown",
            "in_use": False,
            "message": "Некорректный номер порта",
            "listener": None,
        }

    try:
        ss = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "port": port,
            "status": "unknown",
            "in_use": False,
            "message": f"Не удалось проверить порт: {exc}",
            "listener": None,
        }

    if ss.returncode != 0:
        return {
            "port": port,
            "status": "unknown",
            "in_use": False,
            "message": "Не удалось выполнить ss -tlnp (установите iproute2)",
            "listener": None,
        }

    listeners = _parse_ss_listeners(ss.stdout or "", port)
    if not listeners:
        return {
            "port": port,
            "status": "free",
            "in_use": False,
            "message": "Порт свободен",
            "listener": None,
        }

    listener = listeners[0][:300]
    panel_lines = [line for line in listeners if PANEL_PROCESS_RE.search(line)]
    nginx_lines = [line for line in listeners if NGINX_PROCESS_RE.search(line)]

    if panel_lines and not nginx_lines and role == PORT_ROLE_BACKEND:
        return {
            "port": port,
            "status": "panel",
            "in_use": True,
            "message": "Порт уже используется панелью (uvicorn)",
            "listener": listener,
        }

    if nginx_lines and role in {PORT_ROLE_NGINX_HTTPS, PORT_ROLE_NGINX_HTTP}:
        label = "HTTPS" if role == PORT_ROLE_NGINX_HTTPS else "HTTP (ACME / редирект)"
        return {
            "port": port,
            "status": "nginx",
            "in_use": True,
            "message": f"Порт слушает nginx — подходит для {label}",
            "listener": listener,
        }

    if nginx_lines:
        return {
            "port": port,
            "status": "nginx",
            "in_use": True,
            "message": "Порт занят nginx — выберите другой или остановите чужой сайт",
            "listener": listener,
        }

    process_hint = _listener_process_hint(listener)
    return {
        "port": port,
        "status": "other",
        "in_use": True,
        "message": f"Порт занят: {process_hint}",
        "listener": listener,
    }


def server_primary_ip() -> str | None:
    """First IPv4 of the server (for HTTP direct access hints)."""
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            parts = (result.stdout or "").strip().split()
            if parts:
                first = parts[0]
                if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", first):
                    return first
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        result = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            match = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", result.stdout or "")
            if match:
                return match.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def letsencrypt_cert_paths(domain: str) -> tuple[str, str]:
    domain_host = (domain or "").strip().split(":")[0]
    return (
        f"/etc/letsencrypt/live/{domain_host}/fullchain.pem",
        f"/etc/letsencrypt/live/{domain_host}/privkey.pem",
    )


def letsencrypt_exists_for_domain(domain: str) -> bool:
    cert, key = letsencrypt_cert_paths(domain)
    return Path(cert).is_file() and Path(key).is_file()


def _iter_letsencrypt_live_domains() -> list[str]:
    if not LETSENCRYPT_LIVE_DIR.is_dir():
        return []
    names: list[str] = []
    try:
        for entry in sorted(LETSENCRYPT_LIVE_DIR.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith("."):
                continue
            if letsencrypt_exists_for_domain(name):
                names.append(name)
    except OSError:
        pass
    return names


def discover_ssl_certificate_candidates(
    *,
    domain: str = "",
    ssl_cert: str = "",
    ssl_key: str = "",
) -> list[dict[str, str]]:
    """Known cert/key pairs on the server (for mode switching without re-entering paths)."""
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(cert: str, key: str, label: str, source: str) -> None:
        cert = (cert or "").strip()
        key = (key or "").strip()
        if not cert or not key:
            return
        pair = (cert, key)
        if pair in seen:
            return
        if Path(cert).is_file() and Path(key).is_file():
            seen.add(pair)
            candidates.append({"cert": cert, "key": key, "label": label, "source": source})

    _add(ssl_cert, ssl_key, "Текущие пути из .env", "env")
    domain_host = (domain or "").strip().split(":")[0]
    le_domains: list[str] = []
    if domain_host:
        le_domains.append(domain_host)
    for le_domain in _iter_letsencrypt_live_domains():
        if le_domain not in le_domains:
            le_domains.append(le_domain)
    for le_domain in le_domains:
        cert, key = letsencrypt_cert_paths(le_domain)
        _add(cert, key, f"Let's Encrypt ({le_domain})", "letsencrypt")
    _add(
        str(SELF_SIGNED_CERT_PATH),
        str(SELF_SIGNED_KEY_PATH),
        "Самоподписанный adminpanelaz",
        "selfsigned",
    )
    return candidates


def resolve_publish_ssl_paths(
    *,
    ssl_cert: str | None,
    ssl_key: str | None,
    domain: str | None,
    get_env_value: GetEnvValue | None = None,
) -> tuple[str, str]:
    """Pick cert/key for custom SSL modes: payload → .env → discovered candidates."""
    cert = (ssl_cert or "").strip()
    key = (ssl_key or "").strip()
    if cert and key:
        return cert, key

    env_cert = ""
    env_key = ""
    env_domain = (domain or "").strip()
    if get_env_value is not None:
        env_cert = get_env_value("SSL_CERT", "")
        env_key = get_env_value("SSL_KEY", "")
        if not env_domain:
            env_domain = get_env_value("DOMAIN", "")

    for candidate in discover_ssl_certificate_candidates(
        domain=env_domain,
        ssl_cert=env_cert,
        ssl_key=env_key,
    ):
        return candidate["cert"], candidate["key"]
    return cert, key


def build_vpn_network_publish_modes() -> list[dict[str, str | bool | None]]:
    """Publish modes available from the settings wizard."""
    return [
        {
            "key": "nginx_le",
            "title": "Let's Encrypt",
            "method": "Nginx",
            "description": "Рекомендуемый режим: TLS на Nginx, uvicorn на loopback.",
            "requires_domain": True,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": True,
            "uses_uvicorn_https_port": False,
            "warning": None,
        },
        {
            "key": "nginx_custom",
            "title": "Собственные сертификаты",
            "method": "Nginx",
            "description": "TLS на Nginx с вашими cert/key (certbot или свои файлы).",
            "requires_domain": True,
            "requires_email": False,
            "requires_ssl_cert": True,
            "uses_nginx_ports": True,
            "uses_uvicorn_https_port": False,
            "warning": None,
        },
        {
            "key": "nginx_selfsigned",
            "title": "Самоподписанный SSL",
            "method": "Nginx",
            "description": "Локальный HTTPS через Nginx. Только для тестов.",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": True,
            "uses_uvicorn_https_port": False,
            "warning": (
                "Только для тестов — браузер не доверяет сертификату.\n"
                "Nginx примет HTTPS снаружи (порты 80/443); для интернета — Let's Encrypt · Nginx."
            ),
        },
        {
            "key": "uvicorn_le",
            "title": "Let's Encrypt",
            "method": "Uvicorn",
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
            "title": "Собственные сертификаты",
            "method": "Uvicorn",
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
            "title": "Самоподписанный SSL",
            "method": "Uvicorn",
            "description": "TLS на uvicorn без Nginx. Только для тестов.",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": False,
            "uses_uvicorn_https_port": True,
            "warning": (
                "Только для тестов — браузер не доверяет сертификату, Telegram не работает.\n"
                "Домен или IP в поле ниже; без домена — IP сервера. Вход: https://адрес:порт/"
            ),
        },
        {
            "key": "http_direct",
            "title": "Прямой HTTP",
            "method": "Uvicorn",
            "description": "Uvicorn на 0.0.0.0 без шифрования. Только для тестов.",
            "requires_domain": False,
            "requires_email": False,
            "requires_ssl_cert": False,
            "uses_nginx_ports": False,
            "uses_uvicorn_https_port": False,
            "warning": (
                "Без шифрования — только для тестов.\n"
                "Вход по http://IP:порт/; в интернет включите ограничение по IP."
            ),
        },
    ]
