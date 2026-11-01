"""Admin API for unlock codes."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin, tg_mini_token_allowed
from app.database import get_db
from app.models import User
from app.services.app_setting_store import _get_setting
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.telegram import send_tg_message
from app.services.unlock_codes import (
    create_unlock_code,
    list_unlock_codes,
    revoke_unlock_code,
    serialize_unlock_code,
)

logger = logging.getLogger(__name__)

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
    allowed_client_names: list[str] | None = None
    target_user_id: int | None = None
    comment: str | None = Field(default=None, max_length=128)
    # Если задан и у абонента привязан Telegram — отправить код ему в личный чат.
    send_to_user_id: int | None = None


def _require_unlock_codes_enabled() -> None:
    if not get_feature_service().is_enabled("unlock_codes"):
        raise HTTPException(status_code=403, detail=module_disabled_message("unlock_codes"))


def _default_max_redemptions(mode: str, max_redemptions: int | None) -> int:
    if max_redemptions is not None:
        return max_redemptions
    return 1 if mode.strip().lower() == "single" else 10


@router.get("")
@tg_mini_token_allowed
def get_unlock_codes(
    include_revoked: bool = False,
    comment: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _require_unlock_codes_enabled()
    return list_unlock_codes(db, include_revoked=include_revoked, comment_query=comment)


@router.post("")
@tg_mini_token_allowed
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
            allowed_client_names=payload.allowed_client_names,
            target_user_id=payload.target_user_id,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target_name = None
    if row.target_user_id is not None:
        target_user = db.get(User, row.target_user_id)
        target_name = target_user.username if target_user is not None else None
    result = serialize_unlock_code(row, target_user_name=target_name)
    sent = False
    if payload.send_to_user_id is not None:
        target = db.get(User, payload.send_to_user_id)
        bot_token = _get_setting(db, "telegram_bot_token")
        if target is not None and target.telegram_id and bot_token:
            text = (
                f"🔑 Ключ продления: {row.code}\n"
                f"Срок: {row.grant_days} дн. Активируйте в боте или Mini App."
            )
            try:
                sent = bool(send_tg_message(bot_token, target.telegram_id, text))
            except Exception:  # noqa: BLE001 — доставка не должна ломать создание кода
                logger.exception("unlock code telegram send failed code_id=%s", row.id)
                sent = False
    result["sent_to_telegram"] = sent
    return result


@router.post("/{code_id}/revoke")
@tg_mini_token_allowed
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
