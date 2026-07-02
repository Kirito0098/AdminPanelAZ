"""Sequential rolling node updates via background task."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Node, NodeStatus
from app.services.background_tasks import background_task_service
from app.services.node_manager import check_node_health, get_adapter_for_node, update_node_from_health

logger = logging.getLogger(__name__)


def _update_single_node(node_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        node = db.query(Node).filter(Node.id == node_id).first()
        if not node:
            return {"node_id": node_id, "ok": False, "error": "узел не найден"}

        if node.status == NodeStatus.offline:
            health = check_node_health(node)
            update_node_from_health(node, health, db)
            db.commit()
            db.refresh(node)
            if node.status == NodeStatus.offline:
                return {"node_id": node_id, "node_name": node.name, "ok": False, "error": "узел недоступен"}

        adapter = get_adapter_for_node(node)
        result = adapter.apply_update()
        success = bool(result.get("success"))
        if success and not result.get("restarting"):
            health = check_node_health(node)
            update_node_from_health(node, health, db)
            db.commit()

        return {
            "node_id": node.id,
            "node_name": node.name,
            "ok": success,
            "message": result.get("message"),
            "restarting": bool(result.get("restarting")),
            "errors": result.get("errors") or [],
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Rolling update failed for node %s: %s", node_id, exc)
        return {"node_id": node_id, "ok": False, "error": str(exc)}
    finally:
        db.close()


def run_node_update_roll(
    *,
    node_ids: list[int],
    progress_updater: Callable[[int, str, str | None], None] | None = None,
) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(node_ids))
    total = len(unique_ids)
    if not total:
        return {
            "message": "Нет узлов для обновления",
            "output": json.dumps({"succeeded": [], "failed": [], "node_ids": []}, ensure_ascii=False),
        }

    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for idx, node_id in enumerate(unique_ids, start=1):
        result = _update_single_node(node_id)
        if result.get("ok"):
            succeeded.append(result)
        else:
            failed.append(result)
        if progress_updater:
            label = result.get("node_name") or str(node_id)
            pct = int(idx * 100 / total)
            progress_updater(pct, f"{label} ({idx}/{total})")

    summary = {
        "node_ids": unique_ids,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
    }
    msg = f"Обновление узлов: {len(succeeded)}/{total}, ошибок: {len(failed)}"
    return {
        "message": msg,
        "output": json.dumps(summary, ensure_ascii=False),
    }


def enqueue_node_update_roll(
    db: Session,
    *,
    node_ids: list[int],
    actor_username: str,
) -> str:
    unique_ids = list(dict.fromkeys(node_ids))
    if not unique_ids:
        raise ValueError("Укажите хотя бы один узел")

    missing = [nid for nid in unique_ids if db.query(Node).filter(Node.id == nid).first() is None]
    if missing:
        raise ValueError(f"Узлы не найдены: {', '.join(str(x) for x in missing)}")

    def task_callable(progress_updater=None):
        return run_node_update_roll(node_ids=unique_ids, progress_updater=progress_updater)

    task = background_task_service.enqueue_background_task(
        "node_update_roll",
        task_callable,
        created_by_username=actor_username,
        queued_message=f"Rolling update: {len(unique_ids)} узл(ов)",
    )
    return task.id
