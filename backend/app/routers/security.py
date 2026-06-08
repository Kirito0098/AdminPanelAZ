from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.action_log import log_action
from app.services.ip_restriction import ip_restriction_service
from app.services.public_download_settings import is_public_download_enabled, set_public_download_enabled
from app.services.security import SecurityService

router = APIRouter(prefix="/security", tags=["security"])
settings = get_settings()


class SecuritySettingsUpdate(BaseModel):
    ip_restriction_enabled: bool | None = None
    allowed_ips: list[str] | None = None
    whitelist_firewall: bool | None = None
    block_scanners: bool | None = None
    scanner_max_attempts: int | None = Field(default=None, ge=1, le=20)
    scanner_ban_seconds: int | None = Field(default=None, ge=60, le=86400)
    qr_download_ttl_seconds: int | None = Field(default=None, ge=60, le=3600)
    qr_download_max_downloads: int | None = None
    qr_download_pin: str | None = None
    public_download_enabled: bool | None = None


class PublicDownloadToggle(BaseModel):
    enabled: bool | None = None


class TempWhitelistRequest(BaseModel):
    ip: str
    hours: int = Field(ge=1, le=24, default=1)


@router.get("")
def get_security(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return SecurityService().get_settings(db)


@router.patch("")
def update_security(
    payload: SecuritySettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    service = SecurityService()
    result = service.update_settings(db, payload.model_dump(exclude_none=True))
    service.sync_whitelist_port_firewall(db)
    if settings.audit_log_enabled:
        changed = ", ".join(payload.model_dump(exclude_none=True).keys())
        log_action(
            db,
            action="security_settings_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=changed or "no-op",
        )
    return result


@router.post("/temp-whitelist")
def add_temp_whitelist(
    payload: TempWhitelistRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        service = SecurityService()
        result = service.add_temp_whitelist(db, payload.ip, payload.hours)
        service.sync_whitelist_port_firewall(db)
        if settings.audit_log_enabled:
            log_action(
                db,
                action="security_temp_whitelist",
                user_id=admin.id,
                username=admin.username,
                remote_addr=ip_restriction_service.get_client_ip(request),
                details=f"ip={payload.ip}, hours={payload.hours}",
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/temp-whitelist/{ip}")
def remove_temp_whitelist(
    ip: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    service = SecurityService()
    result = service.remove_temp_whitelist(db, ip)
    service.sync_whitelist_port_firewall(db)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="security_temp_whitelist_remove",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"ip={ip.strip()}",
        )
    return result


@router.post("/public-download")
def toggle_public_download(
    payload: PublicDownloadToggle,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    current = is_public_download_enabled(db)
    next_state = payload.enabled if payload.enabled is not None else not current
    set_public_download_enabled(db, next_state)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="settings_public_download_toggle",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"{'вкл' if current else 'выкл'} → {'вкл' if next_state else 'выкл'}",
        )
    return {
        "enabled": next_state,
        "message": "Публичный доступ к файлам включен." if next_state else "Публичный доступ к файлам выключен.",
    }


@router.get("/check-ip")
def check_ip(request: Request, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    client_ip = request.client.host if request.client else "unknown"
    allowed = SecurityService().is_ip_allowed(db, client_ip)
    return {"client_ip": client_ip, "allowed": allowed}


class UnbanRequest(BaseModel):
    ip: str


@router.get("/scanner-bans")
def get_scanner_bans(_: User = Depends(require_admin)):
    from app.services.ip_restriction import ip_restriction_service

    return {"active_bans": ip_restriction_service.get_active_bans()}


@router.post("/scanner-bans/unban")
def unban_scanner_ip(payload: UnbanRequest, _: User = Depends(require_admin)):
    from app.services.ip_restriction import ip_restriction_service

    if not ip_restriction_service.unban_ip(payload.ip.strip()):
        raise HTTPException(status_code=400, detail="Некорректный IP")
    return {"message": f"IP {payload.ip} разблокирован"}


@router.post("/scanner-bans/clear")
def clear_scanner_bans(_: User = Depends(require_admin)):
    from app.services.ip_restriction import ip_restriction_service

    ip_restriction_service.clear_all_bans()
    return {"message": "Все баны сканеров сняты"}
