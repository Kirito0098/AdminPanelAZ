"""One-shot HA group setup: apply shared domain → full push to replicas → verify.

Runs the whole bring-up as a single background task so it survives the admin
closing the browser. ``run_push_full`` already copies primary hosts to replicas
and auto-verifies, so this chain is exactly: write domain on every member, then
restore replicas from primary.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from app.models import NodeSyncGroup
from app.services.node_sync.push_full import run_push_full
from app.services.node_sync.shared_domain import apply_shared_domain_to_members

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str, str | None], None]


def _scaled_progress(
    progress_updater: ProgressCallback | None,
    low: int,
    high: int,
) -> ProgressCallback | None:
    """Remap a 0..100 sub-step progress into the [low, high] slice of the whole run."""
    if progress_updater is None:
        return None
    span = max(high - low, 1)

    def _cb(percent: int, stage: str, message: str | None = None) -> None:
        scaled = low + int(max(0, min(percent, 100)) / 100 * span)
        progress_updater(scaled, stage, message)

    return _cb


def make_group_setup_callable(group_id: int) -> Callable[..., dict[str, Any]]:
    """Background-task callable: full HA bring-up for a group in a fresh session."""
    captured_group_id = int(group_id)

    def _callable(progress_updater: ProgressCallback | None = None) -> dict[str, Any]:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            group = db.get(NodeSyncGroup, captured_group_id)
            if group is None:
                raise RuntimeError("Sync group не найдена")

            if progress_updater:
                progress_updater(2, "Запись общего домена на узлы…")
            domain_result = apply_shared_domain_to_members(
                db,
                group,
                run_apply=True,
                progress_callback=_scaled_progress(progress_updater, 2, 40),
            )

            push_result = run_push_full(
                db,
                group,
                progress_callback=_scaled_progress(progress_updater, 40, 100),
                auto_verify=True,
            )

            domain_ok = bool(domain_result.get("success"))
            push_ok = bool(push_result.get("success"))
            success = domain_ok and push_ok

            if success:
                message = "HA-группа настроена и проверена"
            elif push_ok and not domain_ok:
                message = "Синхронизация выполнена, но запись домена прошла с ошибками"
            else:
                message = "Настройка HA завершилась с ошибками"

            return {
                "message": message,
                "output": json.dumps(
                    {"shared_domain": domain_result, "push_full": push_result},
                    ensure_ascii=False,
                ),
                "success": success,
            }
        finally:
            db.close()

    return _callable
