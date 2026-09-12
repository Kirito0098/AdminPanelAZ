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
    BackgroundTaskResponse,
    PortalPublishRequest,
    PortalPublishStatusResponse,
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
    qr_download_ttl_seconds: int | None = Field(default=None, ge=60, le=86400)
    qr_download_max_downloads: int | None = None
    qr_download_pin: str | None = None
    public_download_enabled: bool | None = None
    portal_domain: str | None = None


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


@router.get("/portal-publish-status", response_model=PortalPublishStatusResponse)
def get_portal_publish_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from pathlib import Path

    from app.services.client_portal import get_portal_domain
    from app.services.env_file import EnvFileService
    from app.services.feature_guards import get_feature_service, module_disabled_message
    from app.services.panel_publish_info import build_portal_publish_status, resolve_active_publish_mode_key

    if not get_feature_service().is_enabled("client_portal"):
        raise HTTPException(status_code=403, detail=module_disabled_message("client_portal"))

    env_path = Path(__file__).resolve().parents[2] / ".env"
    env = EnvFileService(env_path)
    panel_domain = env.get_env_value("DOMAIN", "") or (settings.domain or "")
    ssl_cert = env.get_env_value("SSL_CERT", "")
    behind = (env.get_env_value("BEHIND_NGINX", "") or "").lower() in {"1", "true", "yes"}
    use_https = (env.get_env_value("USE_HTTPS", "") or "").lower() in {"1", "true", "yes"}
    backend_host = env.get_env_value("BACKEND_HOST", "127.0.0.1") or "127.0.0.1"
    from app.services.panel_publish_info import resolve_panel_publish_mode

    mode_key = resolve_panel_publish_mode(
        behind_nginx=behind,
        backend_host=backend_host,
        use_https=use_https,
    )
    active = resolve_active_publish_mode_key(
        mode_key=mode_key,
        ssl_cert=ssl_cert,
        publish_mode=env.get_env_value("PUBLISH_MODE", ""),
        domain=panel_domain,
    )
    status_payload = build_portal_publish_status(
        portal_domain=get_portal_domain(db),
        panel_domain=panel_domain,
        publish_mode=active,
        ssl_cert=ssl_cert,
        backend_port=env.get_env_value("BACKEND_PORT", "8000") or "8000",
        https_public_port=int(env.get_env_value("HTTPS_PUBLIC_PORT", "443") or "443"),
    )
    return PortalPublishStatusResponse(**status_payload)


@router.post("/portal-publish", status_code=202, response_model=BackgroundTaskResponse)
def post_portal_publish(
    payload: PortalPublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from pathlib import Path

    from fastapi.responses import JSONResponse

    from app.services.background_tasks import background_task_service
    from app.services.client_portal import normalize_portal_domain, set_portal_domain
    from app.services.env_file import EnvFileService
    from app.services.feature_guards import get_feature_service, module_disabled_message
    from app.services.panel_publish_info import resolve_active_publish_mode_key, resolve_panel_publish_mode

    if not get_feature_service().is_enabled("client_portal"):
        raise HTTPException(status_code=403, detail=module_disabled_message("client_portal"))

    try:
        portal_host = normalize_portal_domain(payload.portal_domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not portal_host:
        raise HTTPException(status_code=400, detail="Укажите хост портала")

    env_path = Path(__file__).resolve().parents[2] / ".env"
    env = EnvFileService(env_path)
    panel_domain = env.get_env_value("DOMAIN", "") or (settings.domain or "")

    if payload.save_domain:
        try:
            set_portal_domain(db, portal_host, panel_domain=panel_domain)
            db.commit()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    behind = (env.get_env_value("BEHIND_NGINX", "") or "").lower() in {"1", "true", "yes"}
    use_https = (env.get_env_value("USE_HTTPS", "") or "").lower() in {"1", "true", "yes"}
    backend_host = env.get_env_value("BACKEND_HOST", "127.0.0.1") or "127.0.0.1"
    mode_key = resolve_panel_publish_mode(
        behind_nginx=behind,
        backend_host=backend_host,
        use_https=use_https,
    )
    active = resolve_active_publish_mode_key(
        mode_key=mode_key,
        ssl_cert=env.get_env_value("SSL_CERT", ""),
        publish_mode=env.get_env_value("PUBLISH_MODE", ""),
        domain=panel_domain,
    )

    active_task = background_task_service.find_active_task("portal_publish")
    if active_task:
        return JSONResponse(
            status_code=409,
            content={"detail": "Настройка портала уже выполняется", "active_task_id": active_task.id},
        )
    if background_task_service.find_active_task("vpn_network_publish"):
        return JSONResponse(
            status_code=409,
            content={"detail": "Сначала дождитесь завершения публикации панели"},
        )

    task_payload = {
        "portal_domain": portal_host,
        "email": payload.email,
        "domain": panel_domain,
        "publish_mode": active or "http_direct",
        "backend_port": env.get_env_value("BACKEND_PORT", "8000") or "8000",
        "https_public_port": env.get_env_value("HTTPS_PUBLIC_PORT", "443") or "443",
        "http_acme_port": env.get_env_value("HTTP_ACME_PORT", "80") or "80",
        "ssl_cert": env.get_env_value("SSL_CERT", ""),
        "ssl_key": env.get_env_value("SSL_KEY", ""),
    }

    def _callable(progress_updater=None):
        return background_task_service.task_portal_publish(task_payload, progress_updater)

    task = background_task_service.enqueue_background_task(
        "portal_publish",
        _callable,
        created_by_username=admin.username,
        queued_message="Настройка клиентского портала поставлена в очередь",
    )
    if settings.audit_log_enabled:
        log_action(
            db,
            action="portal_publish",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=portal_host,
        )
    return background_task_service.build_accepted_payload(
        task,
        "Настройка клиентского портала запущена в фоне.",
    )

@router.patch("")
def update_security(
    payload: SecuritySettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    service = SecurityService()
    try:
        result = service.update_settings(db, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
