#!/usr/bin/env python3
"""CLI резервного копирования панели через BackupManager."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException  # noqa: E402

from app.services.backup_manager import BackupManager  # noqa: E402


def _default_install_dir() -> str:
    return os.environ.get("INSTALL_DIR", str(ROOT))


def _env_value(env_path: Path, key: str, default: str) -> str:
    if not env_path.is_file():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() != key:
            continue
        return value.strip().strip('"').strip("'")
    return default


def _build_manager(install_dir: str) -> BackupManager:
    root = Path(install_dir).resolve()
    env_path = root / "backend" / ".env"
    backup_root = Path(_env_value(env_path, "BACKUP_ROOT", "/var/backups/adminpanelaz"))
    return BackupManager(
        app_root=root,
        backup_root=backup_root,
        db_path=root / "backend" / "data" / "adminpanel.db",
        env_path=env_path,
    )


def _service_name() -> str:
    return os.environ.get("SERVICE_NAME", "adminpanelaz")


def _uses_systemd(service_name: str) -> bool:
    unit = Path(f"/etc/systemd/system/{service_name}.service")
    return unit.is_file()


def _service_control(action: str, *, install_dir: str, allow_failure: bool = False) -> None:
    service_name = _service_name()
    if _uses_systemd(service_name):
        cmd = ["systemctl", action, service_name]
    else:
        start_sh = Path(install_dir) / "start.sh"
        if action == "stop":
            cmd = [str(start_sh), "stop"]
        elif action == "start":
            cmd = [str(start_sh), "daemon"]
        elif action == "restart":
            cmd = [str(start_sh), "restart"]
        else:
            return

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout or f"код {result.returncode}").strip()
        raise RuntimeError(f"{' '.join(cmd)}: {detail}")


def cmd_create(args: argparse.Namespace) -> int:
    install_dir = os.path.abspath(args.install_dir)
    manager = _build_manager(install_dir)
    if not args.keep_running:
        _service_control("stop", install_dir=install_dir, allow_failure=True)
    try:
        result = manager.create_backup(include_configs=args.include_configs)
        print(result.get("file_path", result.get("file_name", "")))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if not args.keep_running:
            _service_control("start", install_dir=install_dir, allow_failure=True)


def cmd_restore(args: argparse.Namespace) -> int:
    install_dir = os.path.abspath(args.install_dir)
    manager = _build_manager(install_dir)
    _service_control("stop", install_dir=install_dir, allow_failure=True)
    try:
        result = manager.restore_backup(args.backup_name)
        print(result.get("file_name", ""))
        return 0
    except HTTPException as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        _service_control("start", install_dir=install_dir, allow_failure=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Резервное копирование AdminPanelAZ")
    parser.add_argument(
        "--install-dir",
        default=_default_install_dir(),
        help="Корень установки панели",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Создать бэкап")
    create_parser.add_argument(
        "--include-configs",
        action="store_true",
        help="Включить файлы маршрутизации из data/cidr",
    )
    create_parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Не останавливать панель перед бэкапом",
    )
    create_parser.set_defaults(func=cmd_create)

    restore_parser = subparsers.add_parser("restore", help="Восстановить из бэкапа")
    restore_parser.add_argument(
        "backup_name",
        help="Имя файла или абсолютный путь к архиву .tar.gz",
    )
    restore_parser.set_defaults(func=cmd_restore)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
