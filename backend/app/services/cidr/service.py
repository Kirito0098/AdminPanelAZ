"""CIDR routing management service."""

import re
from pathlib import Path

from fastapi import HTTPException, status

from app.services.cidr.constants import (
    BUILTIN_CIDR_PRESETS,
    IP_FILES,
    RESULT_FILES,
    ROUTE_CONFIG_FILES,
)
from app.services.cidr.ip_manager import IpManager

CIDR_PATTERN = re.compile(
    r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}/(?:[0-9]|[12][0-9]|3[0-2])\b"
)


class CidrRoutingService:
    def __init__(self, antizapret_path: Path, list_dir: Path):
        self.antizapret_path = antizapret_path
        self.config_dir = antizapret_path / "config"
        self.result_dir = antizapret_path / "result"
        self.list_dir = list_dir
        self.ip_manager = IpManager(list_dir, self.config_dir)
        self.list_dir.mkdir(parents=True, exist_ok=True)

    def _count_lines(self, path: Path) -> int:
        if not path.exists():
            return 0
        return sum(
            1
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    def _count_config_routes(self) -> dict:
        total = 0
        per_file: dict[str, int] = {}
        for path in self.config_dir.glob("*include-ips.txt"):
            count = self._count_lines(path)
            per_file[path.name] = count
            total += count
        return {"total": total, "per_file": per_file}

    def get_overview(self) -> dict:
        file_states = self.ip_manager.get_file_states()
        source_states = self.ip_manager.get_source_states()
        providers = []
        for fname, meta in IP_FILES.items():
            list_path = self.list_dir / fname
            ap_path = self.ip_manager._masked_include_path(fname)
            providers.append({
                "filename": fname,
                "name": meta["name"],
                "description": meta.get("description", ""),
                "category": meta.get("category", ""),
                "enabled": file_states.get(fname, False),
                "has_source": source_states.get(fname, False),
                "cidr_count": self._count_lines(ap_path if file_states.get(fname) else list_path),
            })

        route_stats = self._count_config_routes()
        result_route = self.result_dir / RESULT_FILES["route_ips"]
        return {
            "providers": providers,
            "presets": BUILTIN_CIDR_PRESETS,
            "route_stats": {
                "config_include_total": route_stats["total"],
                "config_include_per_file": route_stats["per_file"],
                "result_route_ips_count": self._count_lines(result_route),
                "result_route_ips_exists": result_route.exists(),
            },
            "list_dir": str(self.list_dir),
            "config_dir": str(self.config_dir),
        }

    def get_provider_content(self, filename: str) -> dict:
        if filename not in IP_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер")
        path = self.list_dir / filename
        if not path.exists():
            ap_path = self.ip_manager._masked_include_path(filename)
            if ap_path.exists():
                content = ap_path.read_text(encoding="utf-8", errors="replace")
            else:
                content = ""
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
        return {"filename": filename, "content": content, "cidr_count": self._count_lines(path)}

    def save_provider_content(self, filename: str, content: str) -> dict:
        if filename not in IP_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер")
        path = self.list_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"filename": filename, "cidr_count": self._count_lines(path)}

    def set_provider_enabled(self, filename: str, enabled: bool) -> dict:
        if filename not in IP_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер")
        try:
            count = self.ip_manager.enable_file(filename) if enabled else self.ip_manager.disable_file(filename)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Файл списка {filename} не найден в {self.list_dir}",
            ) from exc
        return {"filename": filename, "enabled": enabled, "cidr_count": count}

    def apply_preset(self, preset_key: str) -> dict:
        preset = next((p for p in BUILTIN_CIDR_PRESETS if p["key"] == preset_key), None)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пресет не найден")

        enabled: list[str] = []
        errors: list[str] = []
        for fname in IP_FILES:
            should_enable = fname in preset["providers"]
            current = self.ip_manager.get_file_states().get(fname, False)
            if should_enable == current:
                continue
            try:
                if should_enable:
                    self.ip_manager.enable_file(fname)
                else:
                    self.ip_manager.disable_file(fname)
                enabled.append(fname)
            except FileNotFoundError:
                errors.append(fname)

        sync = self.ip_manager.sync_enabled_from_list()
        return {
            "preset": preset_key,
            "changed": enabled,
            "errors": errors,
            "sync": sync,
        }

    def sync_providers(self) -> dict:
        restored = self.ip_manager.restore_source_from_config()
        sync = self.ip_manager.sync_enabled_from_list()
        return {"restored": restored, "sync": sync}

    def read_route_file(self, file_key: str) -> dict:
        if file_key not in ROUTE_CONFIG_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный файл")
        fname = ROUTE_CONFIG_FILES[file_key]
        path = self.config_dir / fname
        content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        return {"file_key": file_key, "filename": fname, "content": content, "line_count": self._count_lines(path)}

    def write_route_file(self, file_key: str, content: str) -> dict:
        if file_key not in ROUTE_CONFIG_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл недоступен для записи")
        fname = ROUTE_CONFIG_FILES[file_key]
        path = self.config_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"file_key": file_key, "filename": fname, "line_count": self._count_lines(path)}

    def get_result_files(self) -> dict:
        files = []
        for key, fname in RESULT_FILES.items():
            path = self.result_dir / fname
            files.append({
                "key": key,
                "filename": fname,
                "exists": path.exists(),
                "line_count": self._count_lines(path),
            })
        return {"files": files}

    def get_result_file_content(self, key: str) -> dict:
        if key not in RESULT_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный файл результата")
        fname = RESULT_FILES[key]
        path = self.result_dir / fname
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл ещё не сгенерирован (запустите doall.sh)")
        content = path.read_text(encoding="utf-8", errors="replace")
        return {"key": key, "filename": fname, "content": content, "line_count": self._count_lines(path)}
