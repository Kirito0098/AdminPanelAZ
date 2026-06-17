from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User, UserRole
from app.schemas import (
    ClientTemplateApplyRequest,
    ClientTemplateCreate,
    ClientTemplateResponse,
    ClientTemplateUpdate,
    MessageResponse,
    VpnConfigResponse,
)
from app.services.admin_notify import admin_notify_service
from app.services.client_templates import (
    apply_template,
    create_template,
    delete_template,
    get_template,
    list_templates,
    update_template,
)
from app.services.feature_guards import get_feature_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.groups import require_ha_primary_for_client_ops
from app.services.self_service import enforce_user_can_create_config

router = APIRouter(prefix="/client-templates", tags=["client-templates"])


def _to_response(row) -> ClientTemplateResponse:
    return ClientTemplateResponse.model_validate(row)


def _active_node_id(db: Session) -> int:
    return get_active_node(db).id


@router.get("", response_model=list[ClientTemplateResponse])
def list_client_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.admin, UserRole.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return [_to_response(row) for row in list_templates(db, _active_node_id(db))]


@router.post("", response_model=ClientTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_client_template(
    payload: ClientTemplateCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        row = create_template(db, _active_node_id(db), **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(row)


@router.patch("/{template_id}", response_model=ClientTemplateResponse)
def update_client_template(
    template_id: int,
    payload: ClientTemplateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = get_template(db, _active_node_id(db), template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    try:
        row = update_template(db, row, **payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(row)


@router.delete("/{template_id}", response_model=MessageResponse)
def delete_client_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = get_template(db, _active_node_id(db), template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    try:
        delete_template(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Шаблон удалён")


@router.post("/{template_id}/apply", response_model=VpnConfigResponse, status_code=status.HTTP_201_CREATED)
def apply_client_template(
    template_id: int,
    payload: ClientTemplateApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_template(db, _active_node_id(db), template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")

    enforce_user_can_create_config(db, current_user)
    require_ha_primary_for_client_ops(db)
    owner_id = payload.owner_id if current_user.role == UserRole.admin and payload.owner_id else current_user.id
    try:
        config = apply_template(
            db,
            row,
            client_name=payload.client_name,
            owner_id=owner_id,
            actor=current_user,
            feature_service=get_feature_service(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    node = get_active_node(db)
    admin_notify_service.send_config_create(
        db,
        actor_username=current_user.username,
        target_name=config.client_name,
        target_type=config.vpn_type.value,
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )

    from app.routers.configs import _to_response

    return _to_response(config, db, include_files=True, adapter=get_active_adapter(db))
