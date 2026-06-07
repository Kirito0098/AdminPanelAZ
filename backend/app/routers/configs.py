from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User, UserRole, VpnConfig, VpnType
from app.schemas import MessageResponse, VpnConfigCreate, VpnConfigResponse, VpnConfigUpdate
from app.services.antizapret import antizapret_service

router = APIRouter(prefix="/configs", tags=["configs"])


def _can_access_config(user: User, config: VpnConfig) -> bool:
    return user.role == UserRole.admin or config.owner_id == user.id


def _to_response(config: VpnConfig, db: Session, include_files: bool = True) -> VpnConfigResponse:
    owner = db.query(User).filter(User.id == config.owner_id).first()
    files = antizapret_service.get_profile_files(config.client_name, config.vpn_type) if include_files else []
    return VpnConfigResponse(
        id=config.id,
        client_name=config.client_name,
        vpn_type=config.vpn_type,
        owner_id=config.owner_id,
        owner_username=owner.username if owner else None,
        cert_expire_days=config.cert_expire_days,
        description=config.description,
        created_at=config.created_at,
        updated_at=config.updated_at,
        profile_files=files,
    )


@router.get("", response_model=list[VpnConfigResponse])
def list_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(VpnConfig)
    if current_user.role != UserRole.admin:
        query = query.filter(VpnConfig.owner_id == current_user.id)
    configs = query.order_by(VpnConfig.created_at.desc()).all()
    return [_to_response(c, db) for c in configs]


@router.post("", response_model=VpnConfigResponse, status_code=status.HTTP_201_CREATED)
def create_config(
    payload: VpnConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    owner_id = payload.owner_id if current_user.role == UserRole.admin and payload.owner_id else current_user.id
    owner = db.query(User).filter(User.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Владелец не найден")

    existing = (
        db.query(VpnConfig)
        .filter(VpnConfig.client_name == payload.client_name, VpnConfig.vpn_type == payload.vpn_type)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Конфигурация уже существует")

    if payload.vpn_type == VpnType.openvpn:
        antizapret_service.add_openvpn_client(payload.client_name, payload.cert_expire_days or 3650)
    else:
        antizapret_service.add_wireguard_client(payload.client_name)

    config = VpnConfig(
        client_name=payload.client_name,
        vpn_type=payload.vpn_type,
        owner_id=owner_id,
        cert_expire_days=payload.cert_expire_days,
        description=payload.description,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _to_response(config, db)


@router.get("/{config_id}", response_model=VpnConfigResponse)
def get_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return _to_response(config, db)


@router.patch("/{config_id}", response_model=VpnConfigResponse)
def update_config(
    config_id: int,
    payload: VpnConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    if payload.description is not None:
        config.description = payload.description
    if payload.owner_id is not None:
        if current_user.role != UserRole.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять владельца")
        owner = db.query(User).filter(User.id == payload.owner_id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Владелец не найден")
        config.owner_id = payload.owner_id
    if payload.cert_expire_days is not None and config.vpn_type == VpnType.openvpn:
        antizapret_service.add_openvpn_client(config.client_name, payload.cert_expire_days)
        config.cert_expire_days = payload.cert_expire_days

    db.commit()
    db.refresh(config)
    return _to_response(config, db)


@router.delete("/{config_id}", response_model=MessageResponse)
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    if config.vpn_type == VpnType.openvpn:
        antizapret_service.delete_openvpn_client(config.client_name)
    else:
        antizapret_service.delete_wireguard_client(config.client_name)

    db.delete(config)
    db.commit()
    return MessageResponse(message=f"Клиент '{config.client_name}' удалён")


@router.get("/{config_id}/download")
def download_profile(
    config_id: int,
    path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    content = antizapret_service.read_profile_file(path)
    filename = path.split("/")[-1]
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/sync", response_model=MessageResponse)
def sync_from_antizapret(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Импорт существующих клиентов AntiZapret в базу данных."""
    admin = db.query(User).filter(User.role == UserRole.admin).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Администратор не найден")

    imported = 0
    for client_name in antizapret_service.list_openvpn_clients():
        exists = (
            db.query(VpnConfig)
            .filter(VpnConfig.client_name == client_name, VpnConfig.vpn_type == VpnType.openvpn)
            .first()
        )
        if not exists:
            db.add(VpnConfig(client_name=client_name, vpn_type=VpnType.openvpn, owner_id=admin.id))
            imported += 1

    for client_name in antizapret_service.list_wireguard_clients():
        exists = (
            db.query(VpnConfig)
            .filter(VpnConfig.client_name == client_name, VpnConfig.vpn_type == VpnType.wireguard)
            .first()
        )
        if not exists:
            db.add(VpnConfig(client_name=client_name, vpn_type=VpnType.wireguard, owner_id=admin.id))
            imported += 1

    db.commit()
    return MessageResponse(message=f"Синхронизировано клиентов: {imported}")
