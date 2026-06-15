"""Access control for FastAPI OpenAPI /docs, /redoc, /openapi.json."""

from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from jose import JWTError, jwt

from app.auth import decode_access_token_username
from app.config import get_settings
from app.database import SessionLocal
from app.models import User, UserRole
from app.services.ip_restriction import ip_restriction_service


def _ip_matches_allowlist(client_ip: str, entries: list[str]) -> bool:
    if not entries:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in entries:
        entry = (entry or "").strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def _is_admin_token(token: str, db: Session) -> bool:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") not in (None, "access"):
            return False
        if payload.get("role") == UserRole.admin.value:
            return True
        username = payload.get("sub")
    except JWTError:
        username = decode_access_token_username(token)
    else:
        if not username:
            username = decode_access_token_username(token)
    if not username:
        return False
    user = db.query(User).filter(User.username == username).first()
    return bool(user and user.is_active and user.role == UserRole.admin)


def assert_openapi_docs_access(request: Request) -> None:
    """Raise HTTPException when OpenAPI docs must not be served."""
    settings = get_settings()
    if not settings.openapi_docs_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    client_ip = ip_restriction_service.get_client_ip(request)
    if _ip_matches_allowlist(client_ip, settings.openapi_docs_allowed_ip_list):
        return

    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            db = SessionLocal()
            try:
                if _is_admin_token(token, db):
                    return
            finally:
                db.close()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="OpenAPI documentation requires admin JWT or allowed IP",
        headers={"WWW-Authenticate": "Bearer"},
    )
