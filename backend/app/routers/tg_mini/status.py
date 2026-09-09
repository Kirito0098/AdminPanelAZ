"""Status endpoints for Telegram Mini App."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_tg_mini_admin
from app.database import get_db
from app.models import User
from app.services.tg_mini_status import (
    build_awg2_status_payload,
    build_cidr_status_payload,
    build_warper_status_payload,
)

router = APIRouter()


@router.get("/warper/status")
def mini_warper_status(db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)):
    from app.routers import tg_mini as root

    if not root.get_feature_service().is_enabled("warper"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Модуль WARPER отключён")
    return build_warper_status_payload(db)


@router.get("/awg2/status")
def mini_awg2_status(db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)):
    from app.routers import tg_mini as root

    if not root.get_feature_service().is_enabled("awg2"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Модуль AZ-AWG2 отключён")
    return build_awg2_status_payload(db)


@router.get("/cidr/status")
def mini_cidr_status(db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)):
    return build_cidr_status_payload(db)
