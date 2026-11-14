"""CIDR routing management service."""

import ipaddress
import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException, status

from app.services.cidr.constants import IP_FILES, RESULT_FILES, ROUTE_CONFIG_FILES
from app.services.cidr.ip_manager import IpManager
from app.services.cidr.line_counts import (
    count_nonempty_lines,
    count_nonempty_lines_in_text,
    remember_line_count,
)

MAX_CIDR_CONTENT_BYTES = 8 * 1024 * 1024
MAX_VALIDATION_ERRORS = 10
ASN_PATTERN = re.compile(r"AS\d{1,10}", re.IGNORECASE)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write via a sibling temp file so a crash never leaves a truncated list."""
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _backup_file(path: Path) -> None:
    """Keep a single previous copy as ``<name>.bak`` next to the file."""
    backup = path.with_name(path.name + ".bak")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.bak.", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copy2(path, tmp_name)
        os.replace(tmp_name, backup)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _is_valid_cidr_entry(line: str) -> bool:
    value = line[1:] if line.startswith("!") else line
    if not value:
        return False
    if ASN_PATTERN.fullmatch(value):
        return True
    try:
        return ipaddress.ip_network(value, strict=False).version == 4
    except ValueError:
        return False


def _validate_cidr_content(content: str, *, filename: str) -> None:
    """Reject oversized files and broken lines before they reach parse.sh."""
    size = len(content.encode("utf-8"))
    if size > MAX_CIDR_CONTENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Слишком большой файл {filename}: {size} байт (максимум {MAX_CIDR_CONTENT_BYTES})",
        )
    errors: list[str] = []
    for lineno, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _is_valid_cidr_entry(line):
            continue
        errors.append(f"{filename}: некорректная строка {lineno}: {line[:80]}")
        if len(errors) >= MAX_VALIDATION_ERRORS:
            break
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\n".join(errors))


class CidrRoutingService:
    def __init__(self, antizapret_path: Path, list_dir: Path):
        self.antizapret_path = antizapret_path
        self.config_dir = antizapret_path / "config"
        self.result_dir = antizapret_path / "result"
        self.list_dir = list_dir
        self.ip_manager = IpManager(list_dir, self.config_dir)
        self.list_dir.mkdir(parents=True, exist_ok=True)

    def _count_lines(self, path: Path) -> int:
        return count_nonempty_lines(path)

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
                count = count_nonempty_lines_in_text(content)
                remember_line_count(ap_path, count)
            else:
                content = ""
                count = 0
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
            count = count_nonempty_lines_in_text(content)
            remember_line_count(path, count)
        return {"filename": filename, "content": content, "cidr_count": count}

    def save_provider_content(self, filename: str, content: str) -> dict:
        if filename not in IP_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер")
        _validate_cidr_content(content, filename=filename)
        path = self.list_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != content.encode("utf-8"):
            _backup_file(path)
        _atomic_write_text(path, content)
        count = count_nonempty_lines_in_text(content)
        remember_line_count(path, count)
        return {"filename": filename, "cidr_count": count}

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
        count = count_nonempty_lines_in_text(content)
        if path.exists():
            remember_line_count(path, count)
        return {"file_key": file_key, "filename": fname, "content": content, "line_count": count}

    def write_route_file(self, file_key: str, content: str) -> dict:
        if file_key not in ROUTE_CONFIG_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл недоступен для записи")
        fname = ROUTE_CONFIG_FILES[file_key]
        _validate_cidr_content(content, filename=fname)
        path = self.config_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _backup_file(path)
        _atomic_write_text(path, content)
        count = count_nonempty_lines_in_text(content)
        remember_line_count(path, count)
        return {"file_key": file_key, "filename": fname, "line_count": count}

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

    def get_result_content(self, key: str) -> dict:
        if key not in RESULT_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный файл результата")
        fname = RESULT_FILES[key]
        path = self.result_dir / fname
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл ещё не сгенерирован (запустите doall.sh)")
        content = path.read_text(encoding="utf-8", errors="replace")
        count = count_nonempty_lines_in_text(content)
        remember_line_count(path, count)
        return {"key": key, "filename": fname, "content": content, "line_count": count}
