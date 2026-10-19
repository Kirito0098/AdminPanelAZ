"""Mini App «Мои конфиги»: каталог владельца по всем узлам + файлы/отправка/QR с узла конфига.

В отличие от админского ``/tg-mini/configs`` (активный узел), маршруты ``/me/configs``
показывают только собственные конфиги текущего пользователя на всех его узлах,
HA-тени (``ha_primary_config_id IS NOT NULL``) скрыты из списка.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import get_tg_mini_user
from app.database import get_db
from app.models import Node, User, VpnConfig
from app.schemas import MessageResponse
from app.services.node_manager import get_adapter_for_node
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.vpn_profile_visibility import (
    EMPTY_CATALOG_MESSAGE,
    filter_profile_files,
    profile_file_allowed,
    resolve_effective_visible_vpn_profiles,
)

from .helpers import SendConfigV2Request, _qr_download_service, _send_config_file

router = APIRouter()


def _owned_primary_config_or_404(db: Session, config_id: int, user: User) -> VpnConfig:
    """Собственный не-теневой конфиг; иначе 404 с текстом «не найдено» (без утечки)."""
    config = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.id == config_id,
            VpnConfig.owner_id == user.id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .first()
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена"
        )
    return config


def _node_for_config(db: Session, config: VpnConfig) -> Node:
    node = db.get(Node, config.node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена"
        )
    return node


@router.get("/me/configs")
def me_configs(
    current_user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)
):
    """Собственные конфиги пользователя по всем узлам, сгруппированные по имени."""
    rows = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.owner_id == current_user.id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    node_ids = {config.node_id for config in rows}
    nodes = {
        node.id: node
        for node in (db.query(Node).filter(Node.id.in_(node_ids)).all() if node_ids else [])
    }

    by_name: dict[str, list[dict]] = defaultdict(list)
    for config in rows:
        node = nodes.get(config.node_id)
        by_name[config.client_name or ""].append(
            {
                "node_id": config.node_id,
                "node_label": node.name if node else str(config.node_id),
                "vpn_type": config.vpn_type.value,
                "config_id": config.id,
            }
        )

    configs_out = [
        {
            "name": name,
            "nodes": sorted(entries, key=lambda entry: (entry["node_label"], entry["vpn_type"])),
        }
        for name, entries in sorted(by_name.items())
    ]
    from app.services.user_closed_access import closed_access_payload

    return {
        "configs": configs_out,
        "closed_access": closed_access_payload(db, current_user),
    }


@router.get("/me/configs/{config_id}/files")
def me_config_files(
    config_id: int,
    current_user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    """Файлы профиля с узла конфига (не активного узла)."""
    config = _owned_primary_config_or_404(db, config_id, current_user)
    node = _node_for_config(db, config)
    adapter = get_adapter_for_node(node)
    files = adapter.get_profile_files(config.client_name, config.vpn_type)
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    files = filter_profile_files(files, policy)
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=EMPTY_CATALOG_MESSAGE)
    return {"files": enrich_profile_files(config.client_name, files)}


@router.post("/me/configs/{config_id}/send", response_model=MessageResponse)
def me_send_config(
    config_id: int,
    payload: SendConfigV2Request,
    current_user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    config = _owned_primary_config_or_404(db, config_id, current_user)
    node = _node_for_config(db, config)
    adapter = get_adapter_for_node(node)
    files = adapter.get_profile_files(config.client_name, config.vpn_type)
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
def me_qr_link(
    request: Request,
    config_id: int = Query(...),
    path: str = Query(...),
    current_user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    """Одноразовая ссылка на скачивание файла с узла конфига (не активного узла)."""
    config = _owned_primary_config_or_404(db, config_id, current_user)
    node = _node_for_config(db, config)
    adapter = get_adapter_for_node(node)
    files = adapter.get_profile_files(config.client_name, config.vpn_type)
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
        node_id=config.node_id,
        creator_id=current_user.id,
        creator_username=current_user.username,
        remote_addr=request.client.host if request.client else None,
    )
