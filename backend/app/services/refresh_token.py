"""Refresh token issuance, rotation with reuse detection, and revocation."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RefreshToken, User

logger = logging.getLogger(__name__)

# Browser tabs share the refresh cookie and may refresh at the same moment; the loser presents
# the token the winner just rotated. Within this window that is a race, not token theft.
ROTATION_GRACE_SECONDS = 30

_INVALID_TOKEN_DETAIL = "Недействительный или истёкший refresh-токен"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(db: Session, user: User, *, family_id: str | None = None) -> tuple[str, RefreshToken]:
    settings = get_settings()
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked=False,
        family_id=family_id or secrets.token_hex(16),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def _active_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


def _revoke_family_on_reuse(db: Session, row: RefreshToken) -> None:
    query = db.query(RefreshToken).filter(RefreshToken.revoked.is_(False))
    if row.family_id:
        query = query.filter(RefreshToken.family_id == row.family_id)
    else:
        query = query.filter(RefreshToken.user_id == row.user_id)
    revoked = query.update(
        {"revoked": True, "revoked_at": datetime.utcnow(), "revoke_reason": "reuse"},
        synchronize_session=False,
    )
    db.commit()
    logger.warning(
        "Refresh token reuse detected: user_id=%s family=%s, revoked %s token(s)",
        row.user_id,
        row.family_id or "-",
        revoked,
    )


def _within_rotation_grace(row: RefreshToken, now: datetime) -> bool:
    return (
        row.revoke_reason == "rotated"
        and row.revoked_at is not None
        and now - row.revoked_at <= timedelta(seconds=ROTATION_GRACE_SECONDS)
    )


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[str | None, User]:
    """Exchange a refresh token for a new one.

    Returns ``(None, user)`` for a concurrent refresh that lost the race: the caller should issue
    an access token only, since the browser already holds the winner's cookie.
    """
    now = datetime.utcnow()
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash_token(raw_token)).first()
    if row is None or row.expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_TOKEN_DETAIL)
    if row.revoked:
        if _within_rotation_grace(row, now):
            return None, _active_user(db, row.user_id)
        _revoke_family_on_reuse(db, row)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_TOKEN_DETAIL)

    user = _active_user(db, row.user_id)
    claimed = (
        db.query(RefreshToken)
        .filter(RefreshToken.id == row.id, RefreshToken.revoked.is_(False))
        .update(
            {"revoked": True, "revoked_at": now, "revoke_reason": "rotated"},
            synchronize_session=False,
        )
    )
    db.commit()
    if not claimed:
        return None, user
    raw, _ = create_refresh_token(db, user, family_id=row.family_id)
    return raw, user


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if row and not row.revoked:
        row.revoked = True
        row.revoked_at = datetime.utcnow()
        row.revoke_reason = "logout"
        db.commit()


def revoke_all_user_tokens(db: Session, user_id: int, *, reason: str = "revoked") -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False),
    ).update(
        {"revoked": True, "revoked_at": datetime.utcnow(), "revoke_reason": reason},
        synchronize_session=False,
    )
    db.commit()
