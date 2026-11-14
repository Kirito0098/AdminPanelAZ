"""Mini App: собственная ссылка клиентского портала (без админа).

Абонент получает/перевыпускает ссылку со всеми своими профилями. Срок жизни —
тот же `portal_link_ttl_days`, что в настройках панели; истёкшую ссылку
`POST` перевыпускает автоматически.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_tg_mini_user
from app.database import get_db
from app.models import User
from app.services.client_portal import (
    _active_user_token,
    get_or_create_user_portal_token,
    portal_page_url,
    resolve_portal_base_url,
    rotate_user_portal_token,
)
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.portal_link_settings import (
    get_portal_link_ttl_days,
    portal_link_expires_at,
)

router = APIRouter()


def _require_portal(db: Session) -> None:
    if not get_feature_service().is_enabled("client_portal"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("client_portal"),
        )
    if not resolve_portal_base_url(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Клиентский портал ещё не готов. Задайте поддомен и настройте публикацию "
                "в разделе «Абоненты → Портал и коды»."
            ),
        )


def _payload(db: Session, row, ttl_days: int) -> dict:
    expires = portal_link_expires_at(row.created_at, ttl_days)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "exists": True,
        "url": portal_page_url(db, row.token),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": expires.isoformat() + "Z" if expires else None,
        "ttl_days": ttl_days,
        "expired": bool(expires is not None and now >= expires),
    }


@router.get("/me/portal-link")
def get_my_portal_link(
    user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)
) -> dict:
    _require_portal(db)
    ttl_days = get_portal_link_ttl_days(db)
    row = _active_user_token(db, user_id=user.id)
    if row is None:
        return {
            "exists": False,
            "url": None,
            "created_at": None,
            "expires_at": None,
            "ttl_days": ttl_days,
            "expired": False,
        }
    return _payload(db, row, ttl_days)


@router.post("/me/portal-link")
def create_my_portal_link(
    user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)
) -> dict:
    _require_portal(db)
    ttl_days = get_portal_link_ttl_days(db)
    row = _active_user_token(db, user_id=user.id)
    if row is not None and _payload(db, row, ttl_days)["expired"]:
        row = rotate_user_portal_token(db, user_id=user.id)
    elif row is None:
        row = get_or_create_user_portal_token(db, user_id=user.id)
    return _payload(db, row, ttl_days)


@router.post("/me/portal-link/rotate")
def rotate_my_portal_link(
    user: User = Depends(get_tg_mini_user), db: Session = Depends(get_db)
) -> dict:
    _require_portal(db)
    ttl_days = get_portal_link_ttl_days(db)
    row = rotate_user_portal_token(db, user_id=user.id)
    return _payload(db, row, ttl_days)
