from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import (
    BackgroundTaskResponse,
    DdnsActionResponse,
    DdnsSettingsResponse,
    DdnsSettingsUpdateRequest,
    VpnNetworkDomainSslStatusResponse,
    VpnNetworkEnvRow,
    VpnNetworkPortStatusResponse,
    VpnNetworkPublishModeInfo,
    VpnNetworkPublishRequest,
    VpnNetworkSettingsResponse,
)
from app.services.admin_notify import admin_notify_service
from app.services.action_log import log_action
from app.services.antizapret_settings import (
    az_hosts_matching_domain,
    format_az_panel_domain_conflict_message,
    read_az_vpn_hosts,
)
from app.services.background_tasks import background_task_service
from app.services import ddns_settings as ddns_settings_service
from app.services.env_file import EnvFileService
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.notify_time import get_client_timezone_from_request
from app.services.panel_publish_info import (
    build_panel_publish_context,
    build_subpath_publish_warnings,
    build_uvicorn_publish_warnings,
    build_vpn_network_publish_modes,
    discover_ssl_certificate_candidates,
    inspect_tcp_port,
    is_nginx_installed,
    letsencrypt_cert_paths,
    letsencrypt_exists_for_domain,
    nginx_is_foreign_vhost_for_domain,
    nginx_is_status_openvpn_on_domain,
    panel_restart_command,
    resolve_publish_ssl_paths,
    resolve_vpn_network_request_url,
    server_primary_ip,
)

router = APIRouter(tags=["maintenance"])


@router.get("/settings/vpn-network", response_model=VpnNetworkSettingsResponse)
def get_vpn_network_settings(
    request: Request,
    _: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )
    settings = get_settings()
    env_path = Path(__file__).resolve().parents[2] / ".env"
    env = EnvFileService(env_path)
    ctx = build_panel_publish_context(
        get_env_value=env.get_env_value,
        request_url=resolve_vpn_network_request_url(
            request,
            env_get=env.get_env_value,
            env_key_defined=env.env_key_defined_in_file,
            settings=settings,
        ),
        settings=settings,
        env_key_defined=env.env_key_defined_in_file,
    )
    publish_modes = [VpnNetworkPublishModeInfo(**row) for row in build_vpn_network_publish_modes()]
    domain = env.get_env_value("DOMAIN", "")
    ssl_cert = env.get_env_value("SSL_CERT", "")
    ssl_key = env.get_env_value("SSL_KEY", "")
    suggestions = discover_ssl_certificate_candidates(
        domain=domain,
        ssl_cert=ssl_cert,
        ssl_key=ssl_key,
    )
    known_cert = ssl_cert if ssl_cert and Path(ssl_cert).is_file() else None
    known_key = ssl_key if ssl_key and Path(ssl_key).is_file() else None
    if not known_cert and suggestions:
        known_cert = suggestions[0]["cert"]
        known_key = suggestions[0]["key"]
    uvicorn_warnings = build_uvicorn_publish_warnings(
        domain=domain,
        backend_port=ctx["backend_port"],
        ssl_cert_suggestions=suggestions,
        https_public_port=env.get_env_value("HTTPS_PUBLIC_PORT", "443") or "443",
    )
    access_path_value = env.get_env_value("ACCESS_PATH", "")
    subpath_warnings = build_subpath_publish_warnings(
        domain=domain,
        access_path=access_path_value,
        publish_mode=ctx.get("active_publish_mode") or "",
    )
    uvicorn_warnings = [*subpath_warnings, *uvicorn_warnings]
    az_hosts = sorted(read_az_vpn_hosts())
    return VpnNetworkSettingsResponse(
        mode_key=ctx["mode_key"],
        mode_title=ctx["mode_title"],
        bullet_points=ctx["bullet_points"],
        internal_url=ctx["internal_url"],
        primary_urls=ctx["primary_urls"],
        env_rows=[VpnNetworkEnvRow(**row) for row in ctx["env_rows"]],
        backend_port=ctx["backend_port"],
        publish_modes=publish_modes,
        active_publish_mode=ctx.get("active_publish_mode"),
        known_ssl_cert=known_cert,
        known_ssl_key=known_key,
        ssl_cert_suggestions=suggestions,
        nginx_installed=is_nginx_installed(),
        panel_restart_command=panel_restart_command(),
        uvicorn_publish_warnings=uvicorn_warnings,
        shared_domain_foreign_vhost=bool(ctx.get("shared_domain_foreign_vhost")),
        shared_domain_status_openvpn=bool(ctx.get("shared_domain_status_openvpn")),
        server_primary_ip=server_primary_ip(),
        az_vpn_hosts=az_hosts,
        az_vpn_conflict_hint=(
            "Нельзя использовать домен AntiZapret (OPENVPN_HOST / WIREGUARD_HOST) "
            f"для панели: {', '.join(az_hosts)}. Через конфиг AZ он уходит в туннель. "
            "Свой DNS: отдельное имя для панели; на VPN-домен можно несколько A-записей. "
            "DuckDNS (https://www.duckdns.org/): создайте второе имя для панели."
            if az_hosts
            else None
        ),
    )


@router.get("/settings/vpn-network/domain-ssl", response_model=VpnNetworkDomainSslStatusResponse)
def get_vpn_network_domain_ssl(
    domain: str,
    _: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )
    domain_host = (domain or "").strip().split(":")[0]
    if not domain_host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите домен")
    cert, key = letsencrypt_cert_paths(domain_host)
    has_le = letsencrypt_exists_for_domain(domain_host)
    az_conflict_hosts = az_hosts_matching_domain(domain_host)
    return VpnNetworkDomainSslStatusResponse(
        domain=domain_host,
        has_letsencrypt=has_le,
        cert=cert if has_le else None,
        key=key if has_le else None,
        shared_domain_foreign_vhost=nginx_is_foreign_vhost_for_domain(domain_host),
        shared_domain_status_openvpn=nginx_is_status_openvpn_on_domain(domain_host),
        az_vpn_host_conflict=bool(az_conflict_hosts),
        az_vpn_hosts=az_conflict_hosts,
        az_vpn_conflict_message=format_az_panel_domain_conflict_message(
            domain_host, az_conflict_hosts
        ),
    )


@router.get("/settings/vpn-network/port-status", response_model=VpnNetworkPortStatusResponse)
def get_vpn_network_port_status(
    port: int,
    role: str = "backend",
    _: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )
    allowed_roles = {"backend", "nginx_https", "nginx_http"}
    if role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная роль порта")
    result = inspect_tcp_port(port, role=role)
    return VpnNetworkPortStatusResponse(**result)

def _require_vpn_network_feature() -> None:
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )


def _ddns_settings_response() -> DdnsSettingsResponse:
    return DdnsSettingsResponse(**ddns_settings_service.public_ddns_status())


@router.get("/settings/vpn-network/ddns", response_model=DdnsSettingsResponse)
def get_vpn_network_ddns(_: User = Depends(require_admin)):
    _require_vpn_network_feature()
    return _ddns_settings_response()


@router.put("/settings/vpn-network/ddns", response_model=DdnsActionResponse)
def put_vpn_network_ddns(
    payload: DdnsSettingsUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    _require_vpn_network_feature()
    provider = payload.provider
    output_parts: list[str] = []

    try:
        if provider == "none":
            try:
                ddns_settings_service.set_ddns_timer(False)
            except RuntimeError as exc:
                # Timer may already be absent
                output_parts.append(str(exc))
            ddns_settings_service.clear_ddns_config()
            log_action(
                db,
                action="ddns_settings",
                user_id=admin.id,
                username=admin.username,
                details="provider=none",
            )
            return DdnsActionResponse(
                message="DDNS отключён",
                output="\n".join(output_parts) or None,
                settings=_ddns_settings_response(),
            )

        existing = ddns_settings_service.load_ddns_config()
        previous_config = ddns_settings_service.snapshot_ddns_config()
        token, password = ddns_settings_service.merge_secret_fields(
            provider,
            existing,
            token=payload.token,
            password=payload.password,
        )
        ddns_settings_service.write_ddns_config(
            provider,
            subdomain=(payload.subdomain or "").strip(),
            token=token,
            hostname=(payload.hostname or "").strip(),
            username=(payload.username or "").strip(),
            password=password,
        )

        def _rollback_ddns_config() -> None:
            try:
                ddns_settings_service.restore_ddns_config_snapshot(previous_config)
            except (OSError, RuntimeError):
                # Prefer surfacing the original update/timer error to the admin.
                pass

        update_applied = False
        if payload.run_update:
            try:
                output_parts.append(ddns_settings_service.run_ddns_update())
                update_applied = True
            except RuntimeError as exc:
                _rollback_ddns_config()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

        try:
            output_parts.append(ddns_settings_service.set_ddns_timer(bool(payload.enable_timer)))
        except RuntimeError as exc:
            # Keep new ddns.env if provider update already succeeded — rolling back would
            # desync panel config from the provider. Only roll back when update was skipped.
            if not update_applied:
                _rollback_ddns_config()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

        log_action(
            db,
            action="ddns_settings",
            user_id=admin.id,
            username=admin.username,
            details=f"provider={provider} timer={payload.enable_timer}",
        )
        settings = _ddns_settings_response()
        return DdnsActionResponse(
            message=f"DDNS сохранён ({settings.domain or provider})",
            output="\n".join(p for p in output_parts if p) or None,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось записать конфигурацию DDNS: {exc}",
        ) from exc


@router.post("/settings/vpn-network/ddns/update", response_model=DdnsActionResponse)
def post_vpn_network_ddns_update(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    _require_vpn_network_feature()
    cfg = ddns_settings_service.load_ddns_config()
    if not cfg.configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DDNS не настроен — сначала сохраните провайдера",
        )
    try:
        output = ddns_settings_service.run_ddns_update()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_action(
        db,
        action="ddns_update",
        user_id=admin.id,
        username=admin.username,
        details=cfg.domain or cfg.provider,
    )
    return DdnsActionResponse(
        message="IP обновлён у провайдера DDNS",
        output=output or None,
        settings=_ddns_settings_response(),
    )


@router.post("/settings/vpn-network/publish", status_code=status.HTTP_202_ACCEPTED, response_model=BackgroundTaskResponse)
def publish_vpn_network(
    payload: VpnNetworkPublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )

    if payload.mode in {"nginx_le", "uvicorn_le"} and not (payload.domain or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DOMAIN обязателен для Let's Encrypt")

    domain_for_az_check = ((payload.domain or "").strip().split(":")[0] or None)
    az_conflict = format_az_panel_domain_conflict_message(domain_for_az_check)
    if az_conflict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=az_conflict)

    from app.services.panel_paths import AccessPathError, normalize_access_path

    normalized_access_path = ""
    if payload.access_path:
        try:
            normalized_access_path = normalize_access_path(payload.access_path)
        except AccessPathError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if normalized_access_path and payload.mode.startswith("uvicorn_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ACCESS_PATH поддерживается только с nginx reverse proxy",
        )
    if normalized_access_path and payload.mode == "http_direct":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ACCESS_PATH поддерживается только с nginx reverse proxy",
        )

    env_path = Path(__file__).resolve().parents[2] / ".env"
    env = EnvFileService(env_path)

    if payload.mode in {"nginx_custom", "uvicorn_custom"}:
        cert, key = resolve_publish_ssl_paths(
            ssl_cert=payload.ssl_cert,
            ssl_key=payload.ssl_key,
            domain=payload.domain,
            get_env_value=env.get_env_value,
        )
        if not cert or not key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите пути к сертификату и ключу или задайте DOMAIN для Let's Encrypt",
            )
        if not Path(cert).is_file() or not Path(key).is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Файлы сертификата не найдены: {cert}, {key}",
            )
        payload.ssl_cert = cert
        payload.ssl_key = key

    uvicorn_modes = {"uvicorn_le", "uvicorn_selfsigned", "uvicorn_custom"}
    if payload.mode not in uvicorn_modes:
        if payload.backend_port == payload.https_public_port or payload.backend_port == payload.http_acme_port:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="BACKEND_PORT конфликтует с публичными портами")
        if payload.http_acme_port == payload.https_public_port:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="HTTP_ACME_PORT совпадает с HTTPS_PUBLIC_PORT")

    active = background_task_service.find_active_task("vpn_network_publish")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Публикация панели уже выполняется",
                "active_task_id": active.id,
            },
        )

    task_payload = payload.model_dump()
    if task_payload.get("domain"):
        domain_host = str(task_payload["domain"]).strip().split(":")[0]
        task_payload["domain"] = domain_host or None
    if normalized_access_path:
        task_payload["access_path"] = normalized_access_path
    else:
        task_payload["access_path"] = None
    domain_host = (task_payload.get("domain") or env.get_env_value("DOMAIN", "") or "").strip().split(":")[0]

    def _callable(progress_updater=None):
        return background_task_service.task_vpn_network_publish(task_payload, progress_updater)

    task = background_task_service.enqueue_background_task(
        "vpn_network_publish",
        _callable,
        created_by_username=admin.username,
        queued_message="Публикация панели поставлена в очередь",
    )

    from app.services.ip_restriction import ip_restriction_service

    if get_settings().audit_log_enabled:
        log_action(
            db,
            action="settings_vpn_network_publish",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"mode={payload.mode}, port={payload.backend_port}",
        )

    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_vpn_network_publish",
        details=f"mode={payload.mode}",
        client_timezone=get_client_timezone_from_request(request),
    )

    return background_task_service.build_accepted_payload(
        task,
        "Публикация панели запущена в фоне.",
    )
