"""Read/write .env values (ported from AdminAntizapret env_file.py)."""

import os
from pathlib import Path


class EnvFileService:
    def __init__(self, env_file_path: Path | str):
        self.env_file_path = Path(env_file_path)

    def set_env_value(self, key: str, value: str) -> None:
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

        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("".join(new_lines), encoding="utf-8")

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

    def ensure_env_default(self, key: str, value: str) -> None:
        if self.get_env_value(key, "__missing__") == "__missing__":
            self.set_env_value(key, value)
