from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_password_hash, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import (
    QrDownloadAuditLog,
    QrDownloadToken,
    RefreshToken,
    User,
    UserActionLog,
    UserReminderLog,
    UserRole,
    ViewerConfigAccess,
    VpnConfig,
    WebAuthnCredential,
)
from app.schemas import MessageResponse, UserCreate, UserResponse, UserUpdate
from app.services.action_log import log_action
from app.services.admin_notify import admin_notify_service
from app.services.ip_restriction import ip_restriction_service
from app.services.notify_time import get_client_timezone_from_request
from app.services.admin_bootstrap import (
    scrub_admin_bootstrap_secret_from_env,
    should_scrub_env_after_password_change,
)
from app.services.password_policy import validate_password

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


def _purge_user_before_delete(db: Session, user: User, successor: User) -> None:
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete(synchronize_session=False)
    db.query(ViewerConfigAccess).filter(ViewerConfigAccess.user_id == user.id).delete(synchronize_session=False)
    db.query(UserReminderLog).filter(UserReminderLog.user_id == user.id).delete(synchronize_session=False)
    db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).delete(synchronize_session=False)
    db.query(VpnConfig).filter(VpnConfig.owner_id == user.id).update(
        {VpnConfig.owner_id: successor.id},
        synchronize_session=False,
    )
    db.query(QrDownloadToken).filter(QrDownloadToken.created_by_user_id == user.id).update(
        {QrDownloadToken.created_by_user_id: None},
        synchronize_session=False,
    )
    db.query(QrDownloadAuditLog).filter(QrDownloadAuditLog.actor_user_id == user.id).update(
        {QrDownloadAuditLog.actor_user_id: None},
        synchronize_session=False,
    )
    db.query(UserActionLog).filter(UserActionLog.user_id == user.id).update(
        {UserActionLog.user_id: None},
        synchronize_session=False,
    )


@router.get("", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь уже существует")
    validate_password(payload.password, username=payload.username)
    user = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        theme=payload.theme,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_create",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"created={payload.username}, role={payload.role.value}",
        )
    admin_notify_service.send_user_create(
        db,
        actor_username=admin.username,
        target_name=user.username,
        details=f"role={payload.role.value}",
        client_timezone=get_client_timezone_from_request(request),
    )
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    is_admin = current_user.role == UserRole.admin
    if not is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    if payload.role is not None:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять роль")
        user.role = payload.role
    if payload.theme is not None:
        user.theme = payload.theme
    if payload.is_active is not None:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять статус")
        user.is_active = payload.is_active
    if payload.password:
        if not is_admin and current_user.id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        validate_password(payload.password, username=user.username)
        user.password_hash = get_password_hash(payload.password)
    if payload.telegram_id is not None:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять Telegram ID")
        tg_id = payload.telegram_id.strip()
        if tg_id:
            existing = db.query(User).filter(User.telegram_id == tg_id, User.id != user.id).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Этот Telegram ID уже привязан к другому пользователю",
                )
            user.telegram_id = tg_id
        else:
            user.telegram_id = None
    if payload.config_quota is not None:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять квоту")
        user.config_quota = payload.config_quota

    db.commit()
    db.refresh(user)
    if payload.password and should_scrub_env_after_password_change(user.username):
        scrub_admin_bootstrap_secret_from_env()
    if settings.audit_log_enabled and (payload.password or payload.role is not None or payload.is_active is not None):
        log_action(
            db,
            action="user_update",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"target={user.username}",
        )
    return user


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить себя")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.role == UserRole.admin:
        other_admins = (
            db.query(User)
            .filter(User.role == UserRole.admin, User.id != user.id, User.is_active.is_(True))
            .count()
        )
        if other_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя удалить последнего администратора",
            )
    deleted_username = user.username
    _purge_user_before_delete(db, user, current_user)
    db.delete(user)
    db.commit()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_delete",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"deleted={deleted_username}",
        )
    admin_notify_service.send_user_delete(
        db,
        actor_username=current_user.username,
        target_name=deleted_username,
        client_timezone=get_client_timezone_from_request(request),
    )
    return MessageResponse(message="Пользователь удалён")
