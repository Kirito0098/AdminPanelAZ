"""Mini App: redeem unlock code for the bound user (owner scope)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_tg_mini_user
from app.database import get_db
from app.models import User
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.unlock_codes import redeem_unlock_code_for_user
from app.services.unlock_redeem_rate_limit import unlock_redeem_rate_limit_service

router = APIRouter()


class RedeemCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.post("/me/redeem-code")
def redeem_code(
    payload: RedeemCodeRequest,
    user: User = Depends(get_tg_mini_user),
    db: Session = Depends(get_db),
):
    if not get_feature_service().is_enabled("unlock_codes"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("unlock_codes"),
        )
    if not user.telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не привязан")
    limited = unlock_redeem_rate_limit_service.consume(user.telegram_id)
    if limited:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=limited)
    try:
        return redeem_unlock_code_for_user(db, code=payload.code.strip(), user=user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
