from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AppSetting
from app.services.node_manager import get_active_adapter
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
