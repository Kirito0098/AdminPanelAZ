from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, Node, QrDownloadToken
from app.constants.public_routes import PUBLIC_ROUTE_ROUTERS
from app.services.action_log import log_action
from app.services.file_download import attachment_response
from app.services.feature_guards import require_openvpn_and_security
from app.services.ip_restriction import ip_restriction_service
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery
from app.services.public_download_settings import is_public_download_enabled
from app.services.public_download_rate_limit import public_download_rate_limit_service
from app.services.qr_download import QrDownloadService
from app.services.security import SecurityService

router = APIRouter(prefix="/public", tags=["public"])
settings = get_settings()


def _qr_settings(db: Session) -> dict:
    sec = SecurityService().get_settings(db)
    pin_row = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    return {
        "ttl_seconds": sec["qr_download_ttl_seconds"],
        "max_downloads": sec["qr_download_max_downloads"],
        "pin": pin_row.value if pin_row else "",
    }


def _global_pin_set(db: Session) -> bool:
    pin_row = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    return bool(pin_row and pin_row.value)


def _qr_delivery_source(db: Session, row: QrDownloadToken):
    if row.node_id is None:
        node = get_active_node(db)
    else:
        node = db.get(Node, row.node_id)
        if node is None:
            raise HTTPException(status_code=410, detail="Сервер этой ссылки удалён — запросите новую ссылку")
    return get_adapter_for_node(node), load_node_remote_hosts(db, node.id)


def _qr_download_page(*, token: str, config_name: str, pin_required: bool) -> HTMLResponse:
    """Self-contained page: GET must not redeem the one-time token (link previews)."""
    name = escape(config_name or "config")
    pin_block = (
        '<label for="pin">PIN</label><input id="pin" name="pin" type="password" '
        'inputmode="numeric" autocomplete="one-time-code" required />'
        if pin_required
        else ""
    )
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex,nofollow"/>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"/>
<title>Скачать конфиг</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;max-width:28rem;line-height:1.4}}
button{{margin-top:1rem;padding:.6rem 1rem;font-size:1rem}}
input{{display:block;width:100%;margin-top:.35rem;padding:.5rem;box-sizing:border-box}}
</style>
</head>
<body>
<h1>Скачать конфиг</h1>
<p><code>{name}</code></p>
<form method="post" action="/api/public/qr-download/{escape(token)}">
{pin_block}
<button type="submit">Скачать</button>
</form>
</body>
</html>"""
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Robots-Tag": "noindex, nofollow",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/qr-download/{token}")
def qr_download_get(token: str, request: Request, db: Session = Depends(get_db)):
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)

    cfg = _qr_settings(db)
    svc = QrDownloadService(db, **cfg)
    row = svc.peek_token(token)
    pin_required = bool(row.pin_hash or _global_pin_set(db))
    return _qr_download_page(token=token, config_name=row.config_name, pin_required=pin_required)


@router.post("/qr-download/{token}")
async def qr_download_post(token: str, request: Request, db: Session = Depends(get_db)):
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)

    pin: str | None = None
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        body = await request.json()
        pin = str((body or {}).get("pin") or "") or None
    else:
        form = await request.form()
        pin = str(form.get("pin") or "") or None

    cfg = _qr_settings(db)
    svc = QrDownloadService(db, **cfg)
    adapter, hosts = _qr_delivery_source(db, svc.peek_token(token))
    row = svc.redeem_token(token, pin=pin, remote_addr=client_ip)
    content = read_profile_file_for_delivery(adapter, row.file_path, hosts)
    return attachment_response(content, row.config_name)


@router.get("/route-download/{router}")
def public_route_download(router: str, request: Request, db: Session = Depends(get_db)):
    """Public download of Keenetic / MikroTik / TP-Link route files (not QR one-time links)."""
    require_openvpn_and_security()
    if not is_public_download_enabled(db):
        raise HTTPException(status_code=404, detail="Not found")

    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)

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
    if settings.audit_log_enabled:
        log_action(
            db,
            action="config_download",
            username="public",
            remote_addr=client_ip,
            details=f"channel=public router={router} file={filename}",
        )
    return attachment_response(content, filename)
