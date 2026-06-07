"""Provider CIDR enable/disable and sync to AntiZapret config (ported from AdminAntizapret)."""

import shutil
from pathlib import Path

from app.services.cidr.constants import IP_FILES


class IpManager:
    def __init__(self, list_dir: Path, config_dir: Path):
        self.list_dir = list_dir
        self.config_dir = config_dir

    def _provider_prefix(self, fname: str) -> str:
        if fname.endswith("-ips.txt"):
            return fname[: -len("-ips.txt")]
        if fname.endswith(".txt"):
            return fname[: -len(".txt")]
        return fname

    def _masked_include_path(self, fname: str) -> Path:
        return self.config_dir / f"AP-{self._provider_prefix(fname)}-include-ips.txt"

    def _legacy_masked_path(self, fname: str) -> Path:
        return self.config_dir / f"{self._provider_prefix(fname)}-include-ips.txt"

    def list_ip_files(self) -> dict:
        return IP_FILES.copy()

    def get_file_states(self) -> dict[str, bool]:
        states: dict[str, bool] = {}
        for fname in self.list_ip_files():
            states[fname] = (
                self._masked_include_path(fname).exists()
                or self._legacy_masked_path(fname).exists()
            )
        return states

    def get_source_states(self) -> dict[str, bool]:
        states: dict[str, bool] = {}
        for fname in self.list_ip_files():
            states[fname] = (
                (self.list_dir / fname).exists()
                or self._masked_include_path(fname).exists()
            )
        return states

    def _count_cidrs(self, path: Path) -> int:
        if not path.exists():
            return 0
        count = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                count += 1
        return count

    def enable_file(self, fname: str) -> int:
        source = self.list_dir / fname
        if not source.exists():
            raise FileNotFoundError(fname)

        self.config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, self._masked_include_path(fname))

        legacy = self._legacy_masked_path(fname)
        if legacy.exists():
            legacy.unlink(missing_ok=True)

        return self._count_cidrs(source)

    def disable_file(self, fname: str) -> int:
        removed = 0
        masked = self._masked_include_path(fname)
        if masked.exists():
            removed = self._count_cidrs(masked)
            masked.unlink(missing_ok=True)

        legacy = self._legacy_masked_path(fname)
        if legacy.exists():
            if not removed:
                removed = self._count_cidrs(legacy)
            legacy.unlink(missing_ok=True)

        return removed

    def sync_enabled_from_list(self) -> dict:
        synced_files = 0
        updated_files = 0
        missing_sources: list[str] = []

        for fname, enabled in self.get_file_states().items():
            if not enabled:
                continue

            source = self.list_dir / fname
            if not source.exists():
                missing_sources.append(fname)
                continue

            target = self._masked_include_path(fname)
            self.config_dir.mkdir(parents=True, exist_ok=True)

            source_data = source.read_bytes()
            target_data = target.read_bytes() if target.exists() else None

            if source_data != target_data:
                shutil.copyfile(source, target)
                updated_files += 1

            legacy = self._legacy_masked_path(fname)
            if legacy.exists():
                legacy.unlink(missing_ok=True)

            synced_files += 1

        return {
            "synced_files": synced_files,
            "updated_files": updated_files,
            "missing_sources": missing_sources,
        }

    def restore_source_from_config(self) -> dict[str, bool]:
        restored: dict[str, bool] = {}
        self.list_dir.mkdir(parents=True, exist_ok=True)
        for fname in self.list_ip_files():
            list_path = self.list_dir / fname
            ap_path = self._masked_include_path(fname)
            if not list_path.exists() and ap_path.exists():
                try:
                    shutil.copyfile(ap_path, list_path)
                    restored[fname] = True
                except OSError:
                    restored[fname] = False
        return restored
