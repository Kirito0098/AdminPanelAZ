from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AppSetting
from app.constants.public_routes import PUBLIC_ROUTE_ROUTERS
from app.services.action_log import log_action
from app.services.feature_guards import require_openvpn_and_security
from app.services.ip_restriction import ip_restriction_service
from app.services.node_manager import get_active_adapter
from app.services.public_download_settings import is_public_download_enabled
from app.services.qr_download import QrDownloadService
from app.services.security import SecurityService

router = APIRouter(prefix="/public", tags=["public"])
settings = get_settings()


class PinRequest(BaseModel):
    pin: str = ""


def _qr_settings(db: Session) -> dict:
    sec = SecurityService().get_settings(db)
    pin_row = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    return {
        "ttl_seconds": sec["qr_download_ttl_seconds"],
        "max_downloads": sec["qr_download_max_downloads"],
        "pin": pin_row.value if pin_row else "",
    }


@router.get("/qr-download/{token}")
def qr_download_get(token: str, db: Session = Depends(get_db)):
    svc = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    if svc and svc.value:
        raise HTTPException(status_code=428, detail="Требуется PIN")
    row = QrDownloadService(db, **_qr_settings(db)).redeem_token(token, remote_addr="")
    content = get_active_adapter(db).read_profile_file(row.file_path)
    filename = row.config_name
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/qr-download/{token}")
def qr_download_post(token: str, payload: PinRequest, request: Request, db: Session = Depends(get_db)):
    cfg = _qr_settings(db)
    svc = QrDownloadService(db, **cfg)
    row = svc.redeem_token(token, pin=payload.pin or None, remote_addr=request.client.host if request.client else None)
    content = get_active_adapter(db).read_profile_file(row.file_path)
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{row.config_name}"'})


@router.get("/route-download/{router}")
def public_route_download(router: str, request: Request, db: Session = Depends(get_db)):
    """Public download of Keenetic / MikroTik / TP-Link route files (not QR one-time links)."""
    require_openvpn_and_security()
    if not is_public_download_enabled(db):
        raise HTTPException(status_code=404, detail="Not found")

    result_key = PUBLIC_ROUTE_ROUTERS.get(router)
    if not result_key:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        payload = get_active_adapter(db).get_route_result_content(result_key)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Not found") from exc
        raise

    filename = payload["filename"]
    content = payload["content"]
    client_ip = ip_restriction_service.get_client_ip(request)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="config_download",
            username="public",
            remote_addr=client_ip,
            details=f"channel=public router={router} file={filename}",
        )
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
