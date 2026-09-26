"""Read/write .env values (ported from AdminAntizapret env_file.py)."""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.services.atomic_file import atomic_write_text


class EnvFileService:
    def __init__(self, env_file_path: Path | str):
        self.env_file_path = Path(env_file_path)

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Serialize read-modify-write across workers so concurrent saves don't drop each other's keys."""
        target = self.env_file_path.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target.with_name(f"{target.name}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def set_env_value(self, key: str, value: str) -> None:
        with self._exclusive():
            self._set_env_value(key, value)

    def _set_env_value(self, key: str, value: str) -> None:
        env_path = self.env_file_path
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)

        updated = False
        new_lines: list[str] = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                updated = True
            else:
                new_lines.append(line if line.endswith("\n") else line + "\n")

        if not updated:
            new_lines.append(f"{key}={value}\n")

        atomic_write_text(env_path, "".join(new_lines))

    def remove_env_key(self, key: str) -> None:
        """Drop ``KEY=…`` lines from ``.env`` (no-op if file/key missing)."""
        with self._exclusive():
            self._remove_env_key(key)

    def _remove_env_key(self, key: str) -> None:
        env_path = self.env_file_path
        if not env_path.exists():
            return
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        new_lines = [line for line in lines if not line.startswith(f"{key}=")]
        if len(new_lines) == len(lines):
            return
        atomic_write_text(env_path, "".join(new_lines))

    def get_env_value(self, key: str, default: str = "") -> str:
        env_path = self.env_file_path
        if env_path.exists():
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip()
        return os.getenv(key, default)

    def env_key_defined_in_file(self, key: str) -> bool:
        env_path = self.env_file_path
        if not env_path.exists():
            return False
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(f"{key}="):
                return True
        return False

    def ensure_env_default(self, key: str, value: str) -> None:
        if self.get_env_value(key, "__missing__") == "__missing__":
            self.set_env_value(key, value)
