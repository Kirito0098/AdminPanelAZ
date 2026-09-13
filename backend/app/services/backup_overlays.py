from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from app.services.awg2 import Awg2NotInstalledError, Awg2Service
from app.services.backup_manager import BackupManager
from app.services.node_manager import get_active_adapter

logger = logging.getLogger(__name__)


def apply_backup_overlays(
    payload: dict,
    *,
    mode: Literal["adapter", "local"],
    db=None,
    config_root: Path | None = None,
) -> None:
    if mode == "local":
        _apply_local(payload, config_root=config_root)
        return
    if mode == "adapter":
        if db is None:
            raise ValueError("adapter mode requires db")
        _apply_adapter(payload, db=db)
        return
    raise ValueError(f"unknown overlay mode: {mode}")


def _apply_local(payload: dict, *, config_root: Path | None) -> None:
    root = config_root or (Path(os.environ.get("ANTIZAPRET_PATH", "/root/antizapret")) / "config")
    configs = payload.get("configs") or {}
    try:
        root.mkdir(parents=True, exist_ok=True)
        for filename, content in configs.items():
            if filename not in BackupManager.CONFIG_FILES:
                continue
            (root / filename).write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not restore AntiZapret routing lists: %s", exc)

    data = (payload.get("_files") or {}).get("awg2")
    if not data:
        return
    try:
        service = Awg2Service()
        service.import_narrow_backup(data)
        runtime = service.apply_runtime()
        if runtime.get("success") is False:
            logger.warning(
                "AZ-AWG2 runtime apply after panel restore failed: %s",
                runtime.get("errors") or [],
            )
    except Awg2NotInstalledError as exc:
        logger.warning("AZ-AWG2 overlay skipped (not installed): %s", exc)
    except Exception as exc:
        logger.warning("Could not restore AZ-AWG2 overlay from panel backup: %s", exc)


def _apply_adapter(payload: dict, *, db) -> None:
    configs = payload.get("configs") or {}
    if configs:
        try:
            adapter = get_active_adapter(db)
            for filename, content in configs.items():
                adapter.write_config_file(filename, content)
        except Exception as exc:
            logger.warning("Could not restore AntiZapret routing lists: %s", exc)

    data = (payload.get("_files") or {}).get("awg2")
    if not data:
        return
    try:
        adapter = get_active_adapter(db)
        runtime = adapter.restore_awg2_backup(data)
        if runtime.get("success") is False:
            logger.warning(
                "AZ-AWG2 runtime apply after panel restore failed: %s",
                runtime.get("errors") or [],
            )
            return
        from app.routers.awg2 import _ha_sync_awg2_from_active

        ha = _ha_sync_awg2_from_active(db)
        if ha.get("errors"):
            logger.warning("AZ-AWG2 HA sync after panel restore: %s", ha["errors"])
    except Exception as exc:
        logger.warning("Could not restore AZ-AWG2 overlay from panel backup: %s", exc)
