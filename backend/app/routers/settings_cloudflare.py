from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    CloudflareProxyRefreshRequest,
    CloudflareProxyRefreshResponse,
    CloudflareProxySettingsResponse,
    CloudflareProxySettingsUpdate,
)
from app.services import cloudflare_proxy_settings as cloudflare_proxy_settings_service

router = APIRouter(tags=["maintenance"])


@router.get("/settings/cloudflare-proxy", response_model=CloudflareProxySettingsResponse)
def get_cloudflare_proxy_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return CloudflareProxySettingsResponse(**cloudflare_proxy_settings_service.get_cloudflare_proxy_state(db))


@router.patch("/settings/cloudflare-proxy", response_model=CloudflareProxySettingsResponse)
def update_cloudflare_proxy_settings(
    payload: CloudflareProxySettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    before = cloudflare_proxy_settings_service.get_cloudflare_proxy_state(db)
    next_enabled = before["enabled"] if payload.enabled is None else payload.enabled
    next_origin_lock = before["origin_lock_enabled"]
    if payload.origin_lock_enabled is not None:
        next_origin_lock = payload.origin_lock_enabled
    elif payload.enabled is False:
        next_origin_lock = False

    if payload.origin_lock_enabled is True and not next_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала включите Cloudflare proxy-mode",
        )
    if payload.origin_lock_enabled is True and not cloudflare_proxy_settings_service.has_valid_origin_allow_snippet():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет валидного списка IP Cloudflare. Нажмите «Обновить сейчас».",
        )

    enabled_changing = next_enabled != before["enabled"]
    lock_changing = next_origin_lock != before["origin_lock_enabled"]
    state = cloudflare_proxy_settings_service.set_cloudflare_proxy_flags(
        db,
        enabled=payload.enabled,
        origin_lock_enabled=payload.origin_lock_enabled,
        auto_update=payload.auto_update,
        interval_days=payload.interval_days,
    )
    if enabled_changing or lock_changing:
        try:
            cloudflare_proxy_settings_service.regenerate_panel_nginx_for_cloudflare_proxy()
        except Exception as exc:
            cloudflare_proxy_settings_service.set_cloudflare_proxy_flags(
                db,
                enabled=before["enabled"],
                origin_lock_enabled=before["origin_lock_enabled"],
                auto_update=before["auto_update"],
                interval_days=before["interval_days"],
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Не удалось перегенерировать конфигурацию nginx: {exc}",
            ) from exc
    return CloudflareProxySettingsResponse(**state)


@router.post("/settings/cloudflare-proxy/refresh", response_model=CloudflareProxyRefreshResponse)
def refresh_cloudflare_proxy(
    payload: CloudflareProxyRefreshRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    force = bool(payload.force) if payload is not None else False
    result = cloudflare_proxy_settings_service.refresh_cloudflare_ips(db, force=force)
    return CloudflareProxyRefreshResponse(**result)
