"""Admin API for permanent client portal links."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, UserRole, VpnConfig
from app.services.client_portal import (
    get_or_create_portal_token,
    link_response,
    revoke_portal_token,
    rotate_portal_token,
    resolve_portal_base_url,
)
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.node_manager import get_active_node
from app.services.node_sync.groups import find_sync_group_containing_node
from app.services.config_access import can_view_config

router = APIRouter(prefix="/portal", tags=["portal"])


def _require_portal_enabled() -> None:
    service = get_feature_service()
    if not service.is_enabled("client_portal"):
        raise HTTPException(status_code=403, detail=module_disabled_message("client_portal"))


def _require_portal_domain(db: Session) -> str:
    base = resolve_portal_base_url(db)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Клиентский портал ещё не готов. Задайте поддомен и нажмите "
                "«Настроить под текущую публикацию» в разделе Подписка."
            ),
        )
    return base


def _configs_for_client(db: Session, client_name: str) -> list[VpnConfig]:
    name = (client_name or "").strip()
    active = get_active_node(db)
    group, _ = find_sync_group_containing_node(db, active.id)
    node_id = group.primary_node_id if group else active.id
    return (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == name,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )


def _assert_can_manage_client(user: User, db: Session, client_name: str) -> None:
    configs = _configs_for_client(db, client_name)
    if not configs:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    if user.role == UserRole.admin:
        return
    if not any(can_view_config(user, c, db) for c in configs):
        raise HTTPException(status_code=403, detail="Недостаточно прав")


@router.get("/clients/{client_name}/link")
def get_portal_link(
    client_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_portal_enabled()
    _require_portal_domain(db)
    _assert_can_manage_client(current_user, db, client_name)
    row = get_or_create_portal_token(db, client_name=client_name, creator=current_user)
    return link_response(db, row)


@router.post("/clients/{client_name}/link")
def create_portal_link(
    client_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_portal_enabled()
    _require_portal_domain(db)
    _assert_can_manage_client(current_user, db, client_name)
    row = get_or_create_portal_token(db, client_name=client_name, creator=current_user)
    return link_response(db, row)


@router.post("/clients/{client_name}/rotate")
def rotate_portal_link(
    client_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_portal_enabled()
    _require_portal_domain(db)
    _assert_can_manage_client(current_user, db, client_name)
    row = rotate_portal_token(db, client_name=client_name, creator=current_user)
    return link_response(db, row)


@router.post("/clients/{client_name}/revoke")
def revoke_portal_link(
    client_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_portal_enabled()
    _assert_can_manage_client(current_user, db, client_name)
    revoke_portal_token(db, client_name=client_name)
    return {"ok": True, "client_name": client_name}
