"""Bell notification when the tracked branch has newer commits than the checkout.

The update check that the UI runs on demand works only while an admin watches it;
this worker notices a published release on its own and leaves one row per commit.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.admin_panel_notifications import write_admin_panel_notification
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.node_update import (
    ahead_count,
    fetch_remote,
    resolve_repo_root,
    resolve_update_ref,
    rev_parse,
)

logger = logging.getLogger(__name__)

UPDATE_AVAILABLE_EVENT = "panel_update_available"
NOTIFIED_REF_SETTING = "panel_update_notified_ref"

CHECK_INTERVAL_SECONDS = float(os.environ.get("PANEL_UPDATE_CHECK_SECONDS", str(6 * 3600)))
INITIAL_DELAY_SECONDS = float(os.environ.get("PANEL_UPDATE_CHECK_INITIAL_DELAY_SECONDS", "120"))


def check_panel_update(db: Session, *, repo_root: Path | None = None) -> dict | None:
    """Write one bell row per newly seen upstream commit; ``None`` when nothing is new."""
    root = repo_root or resolve_repo_root()
    if root is None:
        return None
    fetch_remote(root)
    ref, _ref_error = resolve_update_ref(root)
    if not ref:
        return None
    ahead = ahead_count(root, ref)
    if ahead <= 0:
        return None
    sha = rev_parse(root, ref)
    if not sha or _get_setting(db, NOTIFIED_REF_SETTING) == sha:
        return None
    _set_setting(db, NOTIFIED_REF_SETTING, sha)
    db.commit()
    write_admin_panel_notification(
        db,
        event_type=UPDATE_AVAILABLE_EVENT,
        title="Вышло обновление панели",
        message=(
            f"Новых коммитов: {ahead} · {ref} · {sha[:8]}\n"
            "Обновите панель: Настройки → Обновления"
        ),
        level="info",
    )
    return {"ref": ref, "sha": sha, "ahead": ahead}


def _check_once() -> None:
    with SessionLocal() as db:
        check_panel_update(db)


async def run_panel_update_check_loop() -> None:
    await asyncio.sleep(INITIAL_DELAY_SECONDS)
    while True:
        try:
            await asyncio.to_thread(_check_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — проверка обновлений не должна ронять воркер
            logger.exception("panel update check failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def check_panel_update_in_thread() -> None:
    """Run one check on a fresh thread (used by the manual «проверить» action)."""
    threading.Thread(target=_check_once, name="panel-update-check", daemon=True).start()
