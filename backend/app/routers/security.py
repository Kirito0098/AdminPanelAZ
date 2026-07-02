from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User
from app.services.action_log import log_action
from app.services.ip_restriction import ip_restriction_service
from app.services.public_download_settings import is_public_download_enabled, set_public_download_enabled
from app.schemas import (
    ActiveWebSessionResponse,
    SecretRotationApplyRequest,
    SecretRotationApplyResponse,
    SecretRotationItemResponse,
    SecretRotationPreviewRequest,
    SecretRotationPreviewResponse,
)
from app.services.active_web_session import active_web_session_service
from app.services.secrets_rotation import SecretsRotationService
from app.services.event_webhooks import event_webhook_service
from app.services.audit_stream import audit_stream_service
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
    scanner_window_seconds: int | None = Field(default=None, ge=10, le=3600)
    block_ip_blocked_dwell: bool | None = None
    ip_blocked_dwell_seconds: int | None = Field(default=None, ge=30, le=3600)
    qr_download_ttl_seconds: int | None = Field(default=None, ge=60, le=3600)
    qr_download_max_downloads: int | None = None
    qr_download_pin: str | None = None
    public_download_enabled: bool | None = None


class PublicDownloadToggle(BaseModel):
    enabled: bool | None = None


class EventWebhookSettingsUpdate(BaseModel):
    url: str | None = None
    secret: str | None = None
    enabled: bool | None = None
    events: list[dict[str, object]] | None = None


class AuditStreamSettingsUpdate(BaseModel):
    enabled: bool | None = None
    mode: str | None = None
    http_url: str | None = None
    secret: str | None = None
    syslog_host: str | None = None
    syslog_port: int | None = Field(default=None, ge=1, le=65535)
    syslog_protocol: str | None = None
    format: str | None = None


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


@router.get("/event-webhooks")
def get_event_webhooks(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return event_webhook_service.get_settings(db)


@router.patch("/event-webhooks")
def update_event_webhooks(
    payload: EventWebhookSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = event_webhook_service.update_settings(db, payload.model_dump(exclude_none=True))
    if settings.audit_log_enabled:
        log_action(
            db,
            action="event_webhook_settings_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details="event_webhook_settings",
        )
    return result


@router.get("/audit-stream")
def get_audit_stream_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return audit_stream_service.get_settings(db)


@router.patch("/audit-stream")
def update_audit_stream_settings(
    payload: AuditStreamSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        result = audit_stream_service.update_settings(db, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if settings.audit_log_enabled:
        log_action(
            db,
            action="audit_stream_settings_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details="audit_stream_settings",
        )
    return result


@router.post("/audit-stream/test")
def test_audit_stream(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    cfg = audit_stream_service.get_settings(db)
    if not cfg["enabled"]:
        raise HTTPException(status_code=400, detail="Audit stream выключен")
    payload = audit_stream_service.build_test_payload()
    fmt = cfg["format"]
    message = audit_stream_service.format_message(payload, fmt)
    results: dict[str, str] = {}
    mode = cfg["mode"]
    if mode in {"http", "both"}:
        url = cfg["http_url"].strip()
        if not url:
            results["http"] = "skipped: URL не задан"
        else:
            body = message.encode("utf-8")
            secret = db.query(AppSetting).filter(AppSetting.key == "audit_stream_http_secret").first()
            secret_val = secret.value if secret else ""
            ok, code, err = event_webhook_service._post_once(url, body, secret_val or "")
            results["http"] = "ok" if ok else f"failed: {code} {err}"
    if mode in {"syslog", "both"}:
        host = cfg["syslog_host"].strip()
        if not host:
            results["syslog"] = "skipped: host не задан"
        else:
            dest = f"{cfg['syslog_protocol']}://{host}:{cfg['syslog_port']}"
            ok, err = audit_stream_service.send_syslog(dest, message)
            results["syslog"] = "ok" if ok else f"failed: {err}"
    if settings.audit_log_enabled:
        log_action(
            db,
            action="audit_stream_test",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
        )
    return {"results": results}


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


@router.get("/active-sessions", response_model=list[ActiveWebSessionResponse])
def list_active_sessions(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not active_web_session_service.is_enabled():
        return []
    current_session_id = active_web_session_service.get_session_id_from_request(request)
    rows = active_web_session_service.list_active_sessions(db)
    return [
        ActiveWebSessionResponse(
            session_id=row.session_id,
            username=row.username,
            remote_addr=row.remote_addr,
            user_agent=row.user_agent,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            is_current=bool(current_session_id and row.session_id == current_session_id),
        )
        for row in rows
    ]


@router.delete("/active-sessions/{session_id}")
def revoke_active_session(
    session_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not active_web_session_service.revoke_session(db, session_id):
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return {"message": "Сессия отозвана"}


@router.get("/secrets-rotation", response_model=list[SecretRotationItemResponse])
def list_secrets_rotation(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return SecretsRotationService().list_secrets(db)


@router.post("/secrets-rotation/preview", response_model=SecretRotationPreviewResponse)
def preview_secrets_rotation(
    payload: SecretRotationPreviewRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return SecretsRotationService().preview(db, payload.secret_id, value=payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/secrets-rotation/apply", response_model=SecretRotationApplyResponse)
def apply_secrets_rotation(
    payload: SecretRotationApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        result = SecretsRotationService().apply(
            db,
            payload.secret_id,
            new_value=payload.new_value,
            preview_token=payload.preview_token,
            confirm=payload.confirm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.audit_log_enabled:
        log_action(
            db,
            action="secrets_rotation_apply",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"secret_id={payload.secret_id}",
        )
    return result
