"""Reconcile traffic-limit policies after traffic sync (ported from AdminAntizapret 1.9.0)."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node
from app.services.access_policy import AccessPolicyService
from app.services.node_manager import get_adapter_for_node, node_metadata_dict
from app.services.traffic_limit_notify import traffic_limit_notify_service

logger = logging.getLogger(__name__)
settings = get_settings()


def reconcile_traffic_limit_policies(db: Session, *, node_id: int | None = None) -> dict:
    if node_id is None:
        total_changed = 0
        for node in db.query(Node).all():
            result = _reconcile_for_node(db, node)
            total_changed += int(result.get("changed") or 0)
        return {"traffic_limit_reconcile": "ok", "changed": total_changed, "node_id": None}

    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return {"traffic_limit_reconcile": "skipped", "changed": 0, "node_id": node_id}
    return _reconcile_for_node(db, node)


def _reconcile_for_node(db: Session, node: Node) -> dict:
    meta = node_metadata_dict(node)
    antizapret_path = Path(str(meta.get("antizapret_path") or settings.antizapret_path))
    svc = AccessPolicyService(
        db,
        antizapret_path=antizapret_path,
        node_id=node.id,
        adapter=get_adapter_for_node(node),
    )
    result = svc.reconcile_all_traffic_limits(node_id=node.id)
    try:
        traffic_limit_notify_service.process_node(db, node, svc)
    except Exception as exc:
        logger.warning("Traffic limit notify failed for node %s: %s", node.id, exc)
    return {
        **result,
        "wg_runtime_calls": svc.wg_runtime_calls,
        "clients_changed": int(result.get("changed") or 0),
    }


def reconcile_traffic_limit_policies_safe(db: Session, *, node_id: int | None = None) -> dict:
    try:
        return reconcile_traffic_limit_policies(db, node_id=node_id)
    except Exception as exc:
        logger.warning("Traffic limit reconcile failed: %s", exc)
        return {"traffic_limit_reconcile": "error", "error": str(exc)}
