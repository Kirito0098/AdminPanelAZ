"""Config catalog and delivery endpoints for Telegram Mini App."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.auth import get_tg_mini_user
from app.database import get_db
from app.models import User, VpnConfig, VpnType
from app.schemas import MessageResponse
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.vpn_profile_visibility import (
    EMPTY_CATALOG_MESSAGE,
    filter_profile_files,
    profile_file_allowed,
    resolve_effective_visible_vpn_profiles,
)

from .helpers import SendConfigV2Request, _get_accessible_config, _qr_download_service, _send_config_file

router = APIRouter()


@router.get("/configs")
def mini_configs(current_user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)):
    from app.services.config_access import list_accessible_configs

    node = get_active_node(db)
    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id).options(joinedload(VpnConfig.owner))
    rows = list_accessible_configs(db, current_user, query)
    return {
        "configs": [
            {
                "id": c.id,
                "client_name": c.client_name,
                "vpn_type": c.vpn_type.value,
                "owner_username": c.owner.username if c.owner else None,
                "is_mine": c.owner_id == current_user.id,
                "owner_telegram_linked": bool((c.owner.telegram_id or "").strip()) if c.owner else False,
            }
            for c in rows
        ]
    }


@router.get("/configs/{config_id}/files")
def mini_config_files(
    config_id: int,
    current_user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, config_id, current_user)
    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    files = filter_profile_files(files, policy)
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=EMPTY_CATALOG_MESSAGE)
    return {"files": enrich_profile_files(config.client_name, files)}


@router.post("/configs/{config_id}/send", response_model=MessageResponse)
def mini_send_config(
    config_id: int,
    payload: SendConfigV2Request,
    current_user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, config_id, current_user)
    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    match = next((item for item in files if item.get("path") == payload.path), None)
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    if match is None or not profile_file_allowed(
        policy,
        protocol=match.get("protocol", ""),
        variant=match.get("variant", ""),
        path=match.get("path", ""),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=EMPTY_CATALOG_MESSAGE)
    return _send_config_file(
        db,
        config,
        current_user,
        path=payload.path,
        destination=payload.destination,
        install_platform=payload.platform,
    )


@router.get("/qr-link")
def mini_qr_link(
    request: Request,
    config_id: int = Query(...),
    path: str = Query(...),
    current_user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, config_id, current_user)
    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    match = next((item for item in files if item.get("path") == path), None)
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    if match is None or not profile_file_allowed(
        policy,
        protocol=match.get("protocol", ""),
        variant=match.get("variant", ""),
        path=match.get("path", ""),
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    return _qr_download_service(db, request).create_token(
        file_path=path,
        config_type=config.vpn_type.value,
        config_name=build_profile_download_filename(config.client_name, path=path),
        creator_id=current_user.id,
        creator_username=current_user.username,
        remote_addr=request.client.host if request.client else None,
    )
