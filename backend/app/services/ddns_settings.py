"""Read/write /etc/adminpanelaz/ddns.env and drive scripts/ddns-update.sh."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DDNS_CONFIG = Path("/etc/adminpanelaz/ddns.env")
TIMER_NAME = "adminpanelaz-ddns.timer"
SERVICE_NAME = "adminpanelaz-ddns.service"

_SECRET_KEYS = frozenset({"DDNS_TOKEN", "DDNS_PASSWORD"})
_SHELL_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class DdnsConfig:
    provider: str = "none"
    domain: str = ""
    subdomain: str = ""
    token: str = ""
    hostname: str = ""
    username: str = ""
    password: str = ""

    @property
    def configured(self) -> bool:
        return self.provider in {"duckdns", "noip"}


def ddns_config_path() -> Path:
    override = (os.environ.get("DDNS_CONFIG") or "").strip()
    return Path(override) if override else DEFAULT_DDNS_CONFIG


def ddns_script_path(repo_root: Path | None = None) -> Path:
    root = repo_root or PROJECT_ROOT
    return root / "scripts" / "ddns-update.sh"


def _unquote_shell_value(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    try:
        parts = shlex.split(value, posix=True)
    except ValueError:
        return value.strip("'\"")
    if len(parts) == 1:
        return parts[0]
    return value.strip("'\"")


def parse_ddns_env_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SHELL_ASSIGN.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        result[key] = _unquote_shell_value(value)
    return result


def load_ddns_config(path: Path | None = None) -> DdnsConfig:
    config_path = path or ddns_config_path()
    if not config_path.is_file():
        return DdnsConfig()
    try:
        data = parse_ddns_env_text(config_path.read_text(encoding="utf-8"))
    except OSError:
        return DdnsConfig()

    provider = (data.get("DDNS_PROVIDER") or "none").strip().lower() or "none"
    if provider not in {"none", "duckdns", "noip"}:
        provider = "none"
    return DdnsConfig(
        provider=provider,
        domain=(data.get("DDNS_DOMAIN") or "").strip(),
        subdomain=(data.get("DDNS_SUBDOMAIN") or "").strip(),
        token=(data.get("DDNS_TOKEN") or "").strip(),
        hostname=(data.get("DDNS_HOSTNAME") or "").strip(),
        username=(data.get("DDNS_USERNAME") or "").strip(),
        password=(data.get("DDNS_PASSWORD") or "").strip(),
    )


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def resolve_ddns_domain(
    provider: str,
    *,
    subdomain: str = "",
    hostname: str = "",
    domain: str = "",
) -> str:
    if provider == "duckdns":
        sub = subdomain.strip().lower()
        if sub.endswith(".duckdns.org"):
            sub = sub[: -len(".duckdns.org")]
        return f"{sub}.duckdns.org" if sub else ""
    if provider == "noip":
        return (hostname or domain).strip()
    return (domain or "").strip()


def build_ddns_env_text(
    provider: str,
    *,
    subdomain: str = "",
    token: str = "",
    hostname: str = "",
    username: str = "",
    password: str = "",
    domain: str = "",
) -> str:
    provider = (provider or "none").strip().lower()
    if provider not in {"duckdns", "noip"}:
        raise ValueError("provider должен быть duckdns или noip")

    resolved = resolve_ddns_domain(
        provider, subdomain=subdomain, hostname=hostname, domain=domain
    )
    if not resolved:
        raise ValueError("Не удалось определить домен DDNS")

    lines = [
        "# AdminPanelAZ DDNS (создан панелью)",
        f"DDNS_PROVIDER={_shell_quote(provider)}",
        f"DDNS_DOMAIN={_shell_quote(resolved)}",
    ]
    if provider == "duckdns":
        sub = subdomain.strip().lower()
        if sub.endswith(".duckdns.org"):
            sub = sub[: -len(".duckdns.org")]
        if not sub or not token.strip():
            raise ValueError("DuckDNS: укажите поддомен и token")
        lines.append(f"DDNS_SUBDOMAIN={_shell_quote(sub)}")
        lines.append(f"DDNS_TOKEN={_shell_quote(token.strip())}")
    else:
        host = (hostname or domain).strip()
        if not host or not username.strip() or not password.strip():
            raise ValueError("No-IP: укажите hostname, логин и пароль")
        lines.append(f"DDNS_HOSTNAME={_shell_quote(host)}")
        lines.append(f"DDNS_USERNAME={_shell_quote(username.strip())}")
        lines.append(f"DDNS_PASSWORD={_shell_quote(password.strip())}")
    return "\n".join(lines) + "\n"


def write_ddns_config(
    provider: str,
    *,
    subdomain: str = "",
    token: str = "",
    hostname: str = "",
    username: str = "",
    password: str = "",
    domain: str = "",
    path: Path | None = None,
) -> DdnsConfig:
    config_path = path or ddns_config_path()
    text = build_ddns_env_text(
        provider,
        subdomain=subdomain,
        token=token,
        hostname=hostname,
        username=username,
        password=password,
        domain=domain,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(config_path.parent, 0o700)
    except OSError:
        pass
    config_path.write_text(text, encoding="utf-8")
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass
    return load_ddns_config(config_path)


def clear_ddns_config(path: Path | None = None) -> None:
    config_path = path or ddns_config_path()
    try:
        if config_path.is_file():
            config_path.unlink()
    except OSError as exc:
        raise RuntimeError(f"Не удалось удалить {config_path}: {exc}") from exc


def snapshot_ddns_config(path: Path | None = None) -> bytes | None:
    """Return previous ddns.env bytes, or None if the file did not exist."""
    config_path = path or ddns_config_path()
    if not config_path.is_file():
        return None
    try:
        return config_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Не удалось прочитать {config_path}: {exc}") from exc


def restore_ddns_config_snapshot(snapshot: bytes | None, path: Path | None = None) -> None:
    """Restore ddns.env from snapshot_ddns_config(); None means delete the file."""
    config_path = path or ddns_config_path()
    if snapshot is None:
        clear_ddns_config(config_path)
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(config_path.parent, 0o700)
    except OSError:
        pass
    config_path.write_bytes(snapshot)
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass


def merge_secret_fields(
    provider: str,
    existing: DdnsConfig,
    *,
    token: str | None = None,
    password: str | None = None,
) -> tuple[str, str]:
    """Keep existing secrets when the client sends empty / masked values."""
    resolved_token = (token or "").strip()
    resolved_password = (password or "").strip()
    if provider == "duckdns":
        if not resolved_token or resolved_token in {"****", "••••", "***"}:
            resolved_token = existing.token
        return resolved_token, existing.password
    if provider == "noip":
        if not resolved_password or resolved_password in {"****", "••••", "***"}:
            resolved_password = existing.password
        return existing.token, resolved_password
    return "", ""


def timer_status() -> dict[str, bool | str]:
    enabled = False
    active = False
    detail = "не установлен"
    try:
        en = subprocess.run(
            ["systemctl", "is-enabled", TIMER_NAME],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        enabled = en.returncode == 0 and (en.stdout or "").strip() == "enabled"
        ac = subprocess.run(
            ["systemctl", "is-active", TIMER_NAME],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        active = ac.returncode == 0 and (ac.stdout or "").strip() == "active"
        if enabled and active:
            detail = "активен (каждые 5 мин)"
        elif enabled:
            detail = "включён"
        elif (en.stdout or en.stderr or "").strip():
            detail = (en.stdout or en.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        detail = "systemctl недоступен"
    return {"timer_enabled": enabled, "timer_active": active, "timer_detail": detail}


def _run_ddns_script(
    command: str,
    *,
    repo_root: Path | None = None,
    timeout: int = 60,
) -> tuple[str, str]:
    script = ddns_script_path(repo_root)
    if not script.is_file():
        raise RuntimeError(f"Скрипт не найден: {script}")
    result = subprocess.run(
        ["bash", str(script), command],
        cwd=str(script.parent.parent),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=os.environ.copy(),
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(
            f"ddns-update.sh {command} завершился с кодом {result.returncode}. "
            f"{stderr or stdout or 'без вывода'}"
        )
    return stdout, stderr


def run_ddns_update(*, repo_root: Path | None = None) -> str:
    stdout, stderr = _run_ddns_script("update", repo_root=repo_root, timeout=45)
    return "\n".join(part for part in (stdout, stderr) if part)


def set_ddns_timer(enabled: bool, *, repo_root: Path | None = None) -> str:
    command = "install-timer" if enabled else "remove-timer"
    stdout, stderr = _run_ddns_script(command, repo_root=repo_root, timeout=30)
    return "\n".join(part for part in (stdout, stderr) if part)


def public_ddns_status(config: DdnsConfig | None = None) -> dict:
    cfg = config or load_ddns_config()
    timer = timer_status()
    token_set = bool(cfg.token)
    password_set = bool(cfg.password)
    return {
        "provider": cfg.provider if cfg.configured else "none",
        "domain": cfg.domain,
        "subdomain": cfg.subdomain if cfg.provider == "duckdns" else "",
        "hostname": (cfg.hostname or cfg.domain) if cfg.provider == "noip" else "",
        "username": cfg.username if cfg.provider == "noip" else "",
        "token_configured": token_set,
        "password_configured": password_set,
        "token_masked": "****" if token_set else "",
        "password_masked": "****" if password_set else "",
        "timer_enabled": bool(timer["timer_enabled"]),
        "timer_active": bool(timer["timer_active"]),
        "timer_detail": str(timer["timer_detail"]),
        "config_path": str(ddns_config_path()),
        "configured": cfg.configured,
    }


# Re-export for tests / clarity
__all__ = [
    "DdnsConfig",
    "DEFAULT_DDNS_CONFIG",
    "SERVICE_NAME",
    "TIMER_NAME",
    "_SECRET_KEYS",
    "build_ddns_env_text",
    "clear_ddns_config",
    "ddns_config_path",
    "ddns_script_path",
    "load_ddns_config",
    "merge_secret_fields",
    "parse_ddns_env_text",
    "public_ddns_status",
    "resolve_ddns_domain",
    "restore_ddns_config_snapshot",
    "run_ddns_update",
    "set_ddns_timer",
    "snapshot_ddns_config",
    "timer_status",
    "write_ddns_config",
]
