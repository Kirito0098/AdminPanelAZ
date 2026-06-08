"""AntiZapret full backup via client.sh 8 (ported from AdminAntizapret)."""

from __future__ import annotations

import glob
import os
import re
import subprocess
import tarfile
from pathlib import Path


class AntizapretBackupService:
    _BACKUP_STDOUT_RE = re.compile(
        r"recreated at\s+(\S+\.tar\.gz)",
        re.IGNORECASE,
    )

    def __init__(self, *, install_dir: str | Path = "/root/antizapret", timeout_seconds: int = 600):
        self.install_dir = Path(install_dir or "/root/antizapret").resolve()
        self.timeout_seconds = max(30, int(timeout_seconds or 600))

    def create_backup(self) -> dict[str, str]:
        client_sh = self.install_dir / "client.sh"
        if not client_sh.is_file():
            raise FileNotFoundError(f"client.sh не найден: {client_sh}")
        if not os.access(client_sh, os.X_OK):
            raise PermissionError(f"client.sh не исполняемый: {client_sh}")

        result = subprocess.run(
            [str(client_sh), "8"],
            cwd=str(self.install_dir),
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"код выхода {result.returncode}"
            raise RuntimeError(f"client.sh 8 завершился с ошибкой: {detail}")

        archive_path = self._resolve_archive_path(result.stdout or "")
        self._verify_archive(archive_path)
        return {
            "archive_path": archive_path,
            "archive_name": os.path.basename(archive_path),
        }

    def _resolve_archive_path(self, stdout: str) -> str:
        for line in (stdout or "").splitlines():
            match = self._BACKUP_STDOUT_RE.search(line)
            if match:
                candidate = match.group(1).strip()
                if os.path.isabs(candidate) and os.path.isfile(candidate):
                    return os.path.abspath(candidate)
                joined = self.install_dir / os.path.basename(candidate)
                if joined.is_file():
                    return str(joined.resolve())

        pattern = str(self.install_dir / "backup-*.tar.gz")
        candidates = [p for p in glob.glob(pattern) if os.path.isfile(p)]
        if not candidates:
            raise FileNotFoundError(
                f"Архив AntiZapret не найден после client.sh 8 (ожидался {pattern})"
            )
        return os.path.abspath(max(candidates, key=os.path.getmtime))

    def _verify_archive(self, archive_path: str) -> None:
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"Файл бэкапа не найден: {archive_path}")
        with tarfile.open(archive_path, "r:gz"):
            pass
