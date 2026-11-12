"""Node management endpoints for Telegram Mini App."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_tg_mini_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.action_log import log_action
from app.services.node_manager import (
    check_node_health,
    get_active_node_id,
    is_vpn_node,
    set_active_node_id,
    sync_local_node,
    update_node_from_health,
)
from app.services.node_sync.groups import require_ha_primary_for_node_activation

from .helpers import _get_tg_node_or_404, _serialize_tg_node

router = APIRouter()


@router.get("/nodes")
def mini_list_nodes(db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)):
    from app.models import Node

    sync_local_node(db)
    active_id = get_active_node_id(db)
    nodes = db.query(Node).order_by(Node.is_local.desc(), Node.name).all()
    return {
        "active_node_id": active_id,
        "nodes": [_serialize_tg_node(node, active_id=active_id, db=db) for node in nodes],
    }


@router.post("/nodes/{node_id}/activate")
def mini_activate_node(
    node_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_tg_mini_admin),
):
    node = _get_tg_node_or_404(node_id, db)
    if not is_vpn_node(node):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Прокси-узел нельзя сделать активным для VPN",
        )
    require_ha_primary_for_node_activation(db, node=node)
    set_active_node_id(db, node.id)
    db.commit()
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.commit()
    db.refresh(node)
    if get_settings().audit_log_enabled:
        log_action(
            db,
            action="node_activate",
            user_id=admin.id,
            username=admin.username,
            remote_addr="tg-mini",
            details=f"name={node.name}, id={node.id}",
        )
    active_id = get_active_node_id(db)
    return {
        "node": _serialize_tg_node(node, active_id=active_id, db=db),
        "health": health,
    }
