"""AntiZapret full backup/restore via client.sh 8 (ported from AdminAntizapret)."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

from app.services.node_sync.fingerprints import collect_antizapret_fingerprints


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

    def restore_backup(self, archive_path: str | Path) -> dict[str, str]:
        """Restore AntiZapret state from client.sh 8 archive (setup.sh-compatible flow)."""
        archive = Path(archive_path).resolve()
        self._verify_archive(str(archive))

        extract_root = Path("/root")
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(path=str(extract_root))

        self._copy_tree(extract_root / "easyrsa3", Path("/etc/openvpn/easyrsa3"))
        self._copy_files(extract_root / "wireguard", Path("/etc/wireguard"))
        self._copy_files(extract_root / "config", self.install_dir / "config")
        self._copy_files(extract_root / "knot-resolver", Path("/etc/knot-resolver"))
        custom_src = extract_root / "custom"
        if custom_src.is_dir():
            for item in custom_src.iterdir():
                if item.is_file():
                    shutil.copy2(item, self.install_dir / item.name)

        self._cleanup_extract_artifacts(extract_root, archive.name)

        client_sh = self.install_dir / "client.sh"
        recreate = subprocess.run(
            [str(client_sh), "7"],
            cwd=str(self.install_dir),
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if recreate.returncode != 0:
            detail = (recreate.stderr or recreate.stdout or "").strip()
            raise RuntimeError(f"client.sh 7 после restore завершился с ошибкой: {detail}")

        doall_sh = self.install_dir / "doall.sh"
        apply_detail = ""
        if doall_sh.is_file():
            apply = subprocess.run(
                [str(doall_sh)],
                cwd=str(self.install_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
            apply_detail = (apply.stdout or apply.stderr or "").strip()
            if apply.returncode != 0:
                raise RuntimeError(f"doall.sh после restore завершился с ошибкой: {apply_detail}")

        for service in ("openvpn", "wg-quick@wg0"):
            subprocess.run(
                ["systemctl", "restart", service],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

        return {
            "archive_path": str(archive),
            "archive_name": archive.name,
            "detail": apply_detail[:500] if apply_detail else "restore completed",
        }

    def get_fingerprints(self) -> dict[str, str]:
        return collect_antizapret_fingerprints(self.install_dir)

    def _copy_tree(self, src: Path, dst: Path) -> None:
        if not src.is_dir():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            target = dst / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(item, target)
            elif item.is_file():
                shutil.copy2(item, target)

    def _copy_files(self, src: Path, dst: Path) -> None:
        if not src.is_dir():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.is_file():
                shutil.copy2(item, dst / item.name)

    def _cleanup_extract_artifacts(self, extract_root: Path, archive_name: str) -> None:
        for name in ("easyrsa3", "wireguard", "config", "knot-resolver", "custom"):
            path = extract_root / name
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
        for pattern in ("backup*.tar.gz", archive_name):
            for path in glob.glob(str(extract_root / pattern)):
                try:
                    os.remove(path)
                except OSError:
                    pass

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
