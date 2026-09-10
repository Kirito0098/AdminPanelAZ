"""Admin API for unlock codes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.unlock_codes import (
    create_unlock_code,
    list_unlock_codes,
    revoke_unlock_code,
)

router = APIRouter(
    prefix="/unlock-codes",
    tags=["unlock-codes"],
)


class UnlockCodeCreateRequest(BaseModel):
    grant_days: int = Field(ge=1, le=3650)
    protocols: list[str] = Field(min_length=1)
    mode: str = Field(default="single")
    max_redemptions: int | None = Field(default=None, ge=1, le=1000)
    code_expires_at: datetime | None = None
    code: str | None = None


def _require_unlock_codes_enabled() -> None:
    if not get_feature_service().is_enabled("unlock_codes"):
        raise HTTPException(status_code=403, detail=module_disabled_message("unlock_codes"))


def _default_max_redemptions(mode: str, max_redemptions: int | None) -> int:
    if max_redemptions is not None:
        return max_redemptions
    return 1 if (mode or "").strip().lower() == "single" else 10


@router.get("")
def get_unlock_codes(
    include_revoked: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _require_unlock_codes_enabled()
    return list_unlock_codes(db, include_revoked=include_revoked)


@router.post("")
def post_unlock_code(
    payload: UnlockCodeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    _require_unlock_codes_enabled()
    try:
        row = create_unlock_code(
            db,
            grant_days=payload.grant_days,
            protocols=payload.protocols,
            mode=payload.mode,
            max_redemptions=_default_max_redemptions(payload.mode, payload.max_redemptions),
            code_expires_at=payload.code_expires_at,
            creator=current_user,
            code=payload.code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": row.id,
        "code": row.code,
        "grant_days": row.grant_days,
        "protocols": payload.protocols,
        "mode": row.mode,
        "max_redemptions": row.max_redemptions,
        "code_expires_at": row.code_expires_at.isoformat() if row.code_expires_at else None,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "revoked_at": None,
    }


@router.post("/{code_id}/revoke")
def revoke_code(
    code_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _require_unlock_codes_enabled()
    try:
        revoke_unlock_code(db, code_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "id": code_id}
