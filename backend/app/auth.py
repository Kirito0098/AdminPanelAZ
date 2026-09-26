from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ActiveWebSession, User, UserRole

# bcrypt accepts at most 72 bytes; passlib historically truncated — keep that behaviour
# so existing hashes and long passwords remain verifiable under bcrypt 5.x.
_BCRYPT_MAX_BYTES = 72

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
settings = get_settings()


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_user_access_token(user: User, *, session_id: str | None = None) -> str:
    data: dict[str, Any] = {"sub": user.username, "role": user.role.value, "tv": user.token_version or 0}
    if session_id:
        data["sid"] = session_id
    return create_access_token(
        data=data,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def _decode_access_payload(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") not in (None, "access"):
        return None
    return payload


def access_token_session_id(token: str) -> str | None:
    payload = _decode_access_payload(token)
    sid = payload.get("sid") if payload else None
    return sid if isinstance(sid, str) and sid else None


def bearer_session_id(request: Request) -> str | None:
    scheme, _, token = (request.headers.get("Authorization") or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return access_token_session_id(token.strip())


def _web_session_revoked(db: Session, session_id: object) -> bool:
    if not isinstance(session_id, str) or not session_id:
        return False
    return (
        db.query(ActiveWebSession.id)
        .filter(ActiveWebSession.session_id == session_id, ActiveWebSession.revoked_at.isnot(None))
        .first()
        is not None
    )


def _token_version_current(payload: dict, user: User) -> bool:
    """Tokens issued before the user's last password change carry an older ``tv`` (absent = 0)."""
    try:
        return int(payload.get("tv") or 0) == (user.token_version or 0)
    except (TypeError, ValueError):
        return False


TG_MINI_TOKEN_TYPE = "tg_mini"
_TG_MINI_ENDPOINT_ATTR = "_tg_mini_token_allowed"
_TG_MINI_ROUTER_PACKAGE = "app.routers.tg_mini"

_EndpointT = TypeVar("_EndpointT", bound=Callable[..., Any])


def tg_mini_token_allowed(endpoint: _EndpointT) -> _EndpointT:
    """Let a panel endpoint accept Mini App tokens (it is called from frontend/src/tg-mini/api.ts)."""
    setattr(endpoint, _TG_MINI_ENDPOINT_ATTR, True)
    return endpoint


def create_tg_mini_token(username: str, telegram_id: str, *, token_version: int = 0) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": username,
        "tg": telegram_id,
        "tv": token_version,
        "exp": expire,
        "type": TG_MINI_TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _tg_mini_token_allowed(request: Request) -> bool:
    endpoint = request.scope.get("endpoint")
    if endpoint is None:
        return False
    if getattr(endpoint, _TG_MINI_ENDPOINT_ATTR, False):
        return True
    module = getattr(endpoint, "__module__", "") or ""
    return module == _TG_MINI_ROUTER_PACKAGE or module.startswith(f"{_TG_MINI_ROUTER_PACKAGE}.")


def create_2fa_pending_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=5)
    payload = {"sub": username, "exp": expire, "type": "2fa_pending"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_2fa_pending_token(token: str) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Сессия 2FA истекла, войдите снова",
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "2fa_pending":
            raise credentials_exception
        username: str | None = payload.get("sub")
        if not username:
            raise credentials_exception
        return username
    except jwt.PyJWTError as exc:
        raise credentials_exception from exc


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def get_active_user_from_access_token(db: Session, token: str) -> User | None:
    payload = _decode_access_payload(token)
    if payload is None:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or not _token_version_current(payload, user):
        return None
    if _web_session_revoked(db, payload.get("sid")):
        return None
    return user


def _get_active_user_from_tg_mini_token(db: Session, token: str) -> User | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != TG_MINI_TOKEN_TYPE:
        return None
    username = payload.get("sub")
    telegram_id = str(payload.get("tg") or "").strip()
    if not username or not telegram_id:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or (user.telegram_id or "").strip() != telegram_id:
        return None
    if not _token_version_current(payload, user):
        return None
    return user


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = get_active_user_from_access_token(db, token)
    if user is None and _tg_mini_token_allowed(request):
        user = _get_active_user_from_tg_mini_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен авторизации",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    return current_user


def get_tg_mini_user(current_user: User = Depends(get_current_user)) -> User:
    """Mini App access requires a live Telegram binding (unlink must revoke access immediately)."""
    if not (current_user.telegram_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram не привязан к аккаунту",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_tg_mini_admin(current_user: User = Depends(get_tg_mini_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    return current_user
