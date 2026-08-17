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


def _sqlite_path_from_env(env_path: Path, key: str, default: Path, backend_root: Path) -> Path:
    raw = _env_value(env_path, key, "")
    if raw.startswith("sqlite:///"):
        file_path = Path(raw.replace("sqlite:///", "", 1))
        if not file_path.is_absolute():
            file_path = backend_root / file_path
        return file_path.resolve()
    return default.resolve()


def _build_manager(install_dir: str) -> BackupManager:
    root = Path(install_dir).resolve()
    backend = root / "backend"
    env_path = backend / ".env"
    backup_root = Path(_env_value(env_path, "BACKUP_ROOT", "/var/backups/adminpanelaz"))
    return BackupManager(
        app_root=root,
        backup_root=backup_root,
        db_path=_sqlite_path_from_env(env_path, "DATABASE_URL", backend / "data" / "adminpanel.db", backend),
        cidr_db_path=_sqlite_path_from_env(
            env_path,
            "CIDR_DATABASE_URL",
            backend / "data" / "cidr" / "cidr.db",
            backend,
        ),
        env_path=env_path,
    )


def _service_name() -> str:
    return os.environ.get("SERVICE_NAME", "adminpanelaz")


def _uses_systemd(service_name: str) -> bool:
    unit = Path(f"/etc/systemd/system/{service_name}.service")
    return unit.is_file()


def _service_control(action: str, *, install_dir: str, allow_failure: bool = False) -> None:
    del install_dir  # reserved for callers; control is systemd-only
    service_name = _service_name()
    if not _uses_systemd(service_name):
        if allow_failure:
            return
        raise RuntimeError(f"systemd unit {service_name} не найден")
    if action not in {"stop", "start", "restart"}:
        return

    cmd = ["systemctl", action, service_name]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout or f"код {result.returncode}").strip()
        raise RuntimeError(f"{' '.join(cmd)}: {detail}")


def _load_config_contents(include: bool) -> dict[str, str] | None:
    if not include:
        return None
    az_root = Path(os.environ.get("ANTIZAPRET_HOME", "/root/antizapret")) / "config"
    contents: dict[str, str] = {}
    for filename in BackupManager.CONFIG_FILES:
        path = az_root / filename
        if path.is_file():
            contents[filename] = path.read_text(encoding="utf-8")
    return contents or None


def cmd_create(args: argparse.Namespace) -> int:
    install_dir = os.path.abspath(args.install_dir)
    manager = _build_manager(install_dir)
    if not args.keep_running:
        _service_control("stop", install_dir=install_dir, allow_failure=True)
    try:
        result = manager.create_backup(
            include_configs=args.include_configs,
            config_contents=_load_config_contents(args.include_configs),
        )
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
        help="Включить списки маршрутизации AntiZapret ($ANTIZAPRET_HOME/config)",
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
