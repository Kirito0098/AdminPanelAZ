"""Multi-file AntiZapret editor (ported from AdminAntizapret file_editor.py)."""

from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()

EDITABLE_FILES: dict[str, str] = {
    "include_hosts": "include-hosts.txt",
    "exclude_hosts": "exclude-hosts.txt",
    "include_ips": "include-ips.txt",
    "exclude_ips": "exclude-ips.txt",
    "allow_ips": "allow-ips.txt",
    "drop_ips": "drop-ips.txt",
    "forward_ips": "forward-ips.txt",
    "include_adblock_hosts": "include-adblock-hosts.txt",
    "exclude_adblock_hosts": "exclude-adblock-hosts.txt",
    "remove_hosts": "remove-hosts.txt",
    "deny_ips": "deny-ips.txt",
    "include_warp_hosts": "include-warp-hosts.txt",
    "exclude_warp_hosts": "exclude-warp-hosts.txt",
    "deny_rpz": "deny-rpz.txt",
    "deny2_rpz": "deny2-rpz.txt",
    "warp_rpz": "warp-rpz.txt",
    "proxy_rpz": "proxy-rpz.txt",
    "kresd_custom": "custom.lua",
    "kresd_custom2": "custom2.lua",
}

FILE_TITLES: dict[str, str] = {
    "include_hosts": "Включить домены",
    "exclude_hosts": "Исключить домены",
    "include_ips": "Включить IP/CIDR",
    "exclude_ips": "Исключить IP/CIDR",
    "allow_ips": "Разрешённые IP",
    "drop_ips": "Блокировать IP",
    "forward_ips": "Перенаправлять IP",
    "include_adblock_hosts": "Adblock — включить",
    "exclude_adblock_hosts": "Adblock — исключить",
    "remove_hosts": "Удалить домены",
    "deny_ips": "Запретить входящие IP",
    "include_warp_hosts": "WARP — включить домены",
    "exclude_warp_hosts": "WARP — исключить домены",
    "deny_rpz": "RPZ — блокировка (AntiZapret)",
    "deny2_rpz": "RPZ — блокировка (полный VPN)",
    "warp_rpz": "RPZ — через WARP",
    "proxy_rpz": "RPZ — через AntiZapret",
    "kresd_custom": "DNS-политики (AntiZapret)",
    "kresd_custom2": "DNS-политики (полный VPN)",
}

# Knot Resolver files live in /etc/knot-resolver, not config/; kresd@1 loads custom.lua, kresd@2 custom2.lua.
KRESD_CUSTOM_UNITS: dict[str, str] = {
    "custom.lua": "kresd@1",
    "custom2.lua": "kresd@2",
}

# Node agents before 1.11.0 reject these names: their allowlist predates the files.
FILES_SINCE_AGENT_1_11: frozenset[str] = frozenset(
    {
        "include-warp-hosts.txt",
        "exclude-warp-hosts.txt",
        "deny-rpz.txt",
        "deny2-rpz.txt",
        "warp-rpz.txt",
        "proxy-rpz.txt",
        *KRESD_CUSTOM_UNITS,
    }
)


class ConfigFileUnsupportedError(HTTPException):
    """The node agent is too old to read or write this file."""

    def __init__(self, filename: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Обновите node agent панели на узле — файл {filename} поддерживается с node agent 1.11.0",
        )
        self.filename = filename


def is_kresd_custom_key(key: str) -> bool:
    return EDITABLE_FILES.get(key) in KRESD_CUSTOM_UNITS


class FileEditorService:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or settings.antizapret_path / "config"

    def list_files(self) -> list[dict]:
        return [
            {"key": key, "filename": fname, "title": FILE_TITLES.get(key, key)}
            for key, fname in EDITABLE_FILES.items()
        ]
