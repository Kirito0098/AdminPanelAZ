"""Multi-file AntiZapret editor (ported from AdminAntizapret file_editor.py)."""

from pathlib import Path

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
}


class FileEditorService:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or settings.antizapret_path / "config"

    def list_files(self) -> list[dict]:
        return [
            {"key": key, "filename": fname, "title": FILE_TITLES.get(key, key)}
            for key, fname in EDITABLE_FILES.items()
        ]

    def read_file(self, key: str) -> str:
        fname = EDITABLE_FILES.get(key)
        if not fname:
            raise ValueError("Неизвестный файл")
        path = self.config_dir / fname
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, key: str, content: str) -> None:
        fname = EDITABLE_FILES.get(key)
        if not fname:
            raise ValueError("Неизвестный файл")
        path = self.config_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_all(self) -> dict[str, str]:
        return {key: self.read_file(key) for key in EDITABLE_FILES}
