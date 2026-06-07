from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.security import SecurityService

router = APIRouter(prefix="/security", tags=["security"])


class SecuritySettingsUpdate(BaseModel):
    ip_restriction_enabled: bool | None = None
    allowed_ips: list[str] | None = None
    block_scanners: bool | None = None
    scanner_max_attempts: int | None = Field(default=None, ge=1, le=20)
    scanner_ban_seconds: int | None = Field(default=None, ge=60, le=86400)
    qr_download_ttl_seconds: int | None = Field(default=None, ge=60, le=3600)
    qr_download_max_downloads: int | None = None
    qr_download_pin: str | None = None


class TempWhitelistRequest(BaseModel):
    ip: str
    hours: int = Field(ge=1, le=24, default=1)


@router.get("")
def get_security(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return SecurityService().get_settings(db)


@router.patch("")
def update_security(payload: SecuritySettingsUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return SecurityService().update_settings(db, payload.model_dump(exclude_none=True))


@router.post("/temp-whitelist")
def add_temp_whitelist(payload: TempWhitelistRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return SecurityService().add_temp_whitelist(db, payload.ip, payload.hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/check-ip")
def check_ip(request: Request, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    client_ip = request.client.host if request.client else "unknown"
    allowed = SecurityService().is_ip_allowed(db, client_ip)
    return {"client_ip": client_ip, "allowed": allowed}
