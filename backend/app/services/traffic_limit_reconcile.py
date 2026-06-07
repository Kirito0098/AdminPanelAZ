"""Reconcile traffic-limit policies after traffic sync (ported from AdminAntizapret 1.9.0)."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node
from app.services.access_policy import AccessPolicyService
from app.services.node_manager import get_adapter_for_node, node_metadata_dict

logger = logging.getLogger(__name__)
settings = get_settings()


def reconcile_traffic_limit_policies(db: Session, *, node_id: int | None = None) -> dict:
    if node_id is not None:
        node = db.query(Node).filter(Node.id == node_id).first()
        if node:
            meta = node_metadata_dict(node)
            antizapret_path = Path(str(meta.get("antizapret_path") or settings.antizapret_path))
            svc = AccessPolicyService(
                db,
                antizapret_path=antizapret_path,
                node_id=node.id,
                adapter=get_adapter_for_node(node),
            )
            return svc.reconcile_all_traffic_limits(node_id=node_id)

    svc = AccessPolicyService(db, antizapret_path=settings.antizapret_path)
    return svc.reconcile_all_traffic_limits(node_id=node_id)


def reconcile_traffic_limit_policies_safe(db: Session, *, node_id: int | None = None) -> dict:
    try:
        return reconcile_traffic_limit_policies(db, node_id=node_id)
    except Exception as exc:
        logger.warning("Traffic limit reconcile failed: %s", exc)
        return {"traffic_limit_reconcile": "error", "error": str(exc)}
