from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User, VpnConfig
from app.schemas import ConfigTagCreate, ConfigTagResponse, ConfigTagsAssignRequest, ConfigTagUpdate, MessageResponse
from app.services.config_tags import (
    assign_tags,
    create_tag,
    delete_tag,
    get_tag,
    get_tags_for_configs,
    list_tags,
    update_tag,
)
from app.services.node_manager import get_active_node

router = APIRouter(prefix="/config-tags", tags=["config-tags"])


def _active_node_id(db: Session) -> int:
    return get_active_node(db).id


def _tag_response(tag, config_count: int = 0) -> ConfigTagResponse:
    return ConfigTagResponse(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        config_count=config_count,
    )


@router.get("", response_model=list[ConfigTagResponse])
def list_config_tags(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node_id = _active_node_id(db)
    return [_tag_response(tag, count) for tag, count in list_tags(db, node_id)]


@router.post("", response_model=ConfigTagResponse, status_code=status.HTTP_201_CREATED)
def create_config_tag(
    payload: ConfigTagCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        tag = create_tag(db, _active_node_id(db), name=payload.name, color=payload.color)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _tag_response(tag, 0)


@router.patch("/{tag_id}", response_model=ConfigTagResponse)
def update_config_tag(
    tag_id: int,
    payload: ConfigTagUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tag = get_tag(db, _active_node_id(db), tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тег не найден")
    try:
        tag = update_tag(
            db,
            tag,
            name=payload.name,
            color=payload.color,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    from app.services.config_tags import list_tags

    count = next((c for t, c in list_tags(db, tag.node_id) if t.id == tag.id), 0)
    return _tag_response(tag, count)


@router.delete("/{tag_id}", response_model=MessageResponse)
def delete_config_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    tag = get_tag(db, _active_node_id(db), tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тег не найден")
    delete_tag(db, tag)
    return MessageResponse(message="Тег удалён")


@router.put("/configs/{config_id}/tags", response_model=list[ConfigTagResponse])
def set_config_tags(
    config_id: int,
    payload: ConfigTagsAssignRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    node_id = _active_node_id(db)
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id, VpnConfig.node_id == node_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    try:
        tags = assign_tags(db, config, payload.tag_ids, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [_tag_response(t) for t in tags]
