"""Assign VpnConfig.owner_id with the same side effects as admin PATCH / bulk change_owner."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.services.password_policy import validate_password
from app.services.self_service import password_change_required_on_admin_set
from app.models import User, UserRole, VpnConfig
from app.schemas import UserFromExistingCreate
from app.services.client_portal import revoke_client_portal_links
from app.services.node_sync.client_sync import maybe_replicate_config_metadata


def assign_config_owner(db: Session, *, config: VpnConfig, new_owner: User) -> None:
    if config.ha_primary_config_id is not None:
        raise ValueError("Можно назначать только primary-конфиг (не HA-реплику)")
    previous = config.owner_id
    config.owner_id = new_owner.id
    if previous != new_owner.id:
        revoke_client_portal_links(db, node_id=config.node_id, client_name=config.client_name)


def create_user_from_existing(
    db: Session,
    *,
    payload: UserFromExistingCreate,
    actor: User,
) -> User:
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Пользователь уже существует")

    if not payload.panel_login_enabled:
        password = payload.password or secrets.token_urlsafe(24)
    else:
        if not payload.password:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Пароль обязателен, когда вход в панель включён",
            )
        password = payload.password
    validate_password(password, username=payload.username)

    ids = list(dict.fromkeys(payload.config_ids))  # stable unique
    if payload.config_quota is not None and len(ids) > payload.config_quota:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Число привязываемых конфигов больше квоты",
        )

    configs: list[VpnConfig] = []
    for cid in ids:
        cfg = db.query(VpnConfig).filter(VpnConfig.id == cid).first()
        if cfg is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Конфиг {cid} не найден")
        if cfg.ha_primary_config_id is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Конфиг {cid} — HA-реплика; укажите primary",
            )
        configs.append(cfg)

    user = User(
        username=payload.username,
        password_hash=get_password_hash(password),
        role=UserRole.user,
        panel_login_enabled=payload.panel_login_enabled,
        client_base_name=None,
        access_until=payload.access_until,
        config_quota=payload.config_quota,
        telegram_id=(payload.telegram_id or "").strip() or None,
        provision_state="unmanaged",
        must_change_password=password_change_required_on_admin_set(db),
        is_active=True,
    )
    db.add(user)
    db.flush()  # get user.id

    for cfg in configs:
        assign_config_owner(db, config=cfg, new_owner=user)

    db.commit()
    db.refresh(user)

    for cfg in configs:
        maybe_replicate_config_metadata(db, node_id=cfg.node_id, primary_config=cfg)

    return user
