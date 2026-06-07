"""IP-blocked dwell page (ported from AdminAntizapret ip_blocked blueprint)."""

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ip_restriction import ip_restriction_service

router = APIRouter(tags=["ip-blocked"])

BLOCKED_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Доступ ограничен</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
.container{{max-width:480px;text-align:center}}
.lock{{font-size:48px;margin-bottom:16px}}
h1{{color:#f87171;margin:0 0 8px}}
.subtitle{{color:#94a3b8;margin-bottom:24px}}
.ip-box{{background:#1e293b;border-radius:12px;padding:16px;font-family:monospace;font-size:18px;margin:16px 0}}
.info{{font-size:13px;color:#64748b}}
.toast{{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#7f1d1d;color:#fecaca;padding:12px 20px;border-radius:8px;display:none}}
</style>
</head>
<body>
<div class="container">
<div class="lock">🔒</div>
<h1>Доступ ограничен</h1>
<p class="subtitle">Ваш IP-адрес не входит в список разрешённых для доступа к этой системе</p>
<div class="ip-box" id="ipDisplay">{client_ip}</div>
<p class="info">Время: {current_time}</p>
</div>
<div class="toast" id="toast">Доступ заблокирован на уровне сервера</div>
<script>
const dwellEnabled={dwell_enabled};
const dwellSeconds={dwell_seconds};
const pingUrl="/api/ip-blocked/ping";
let pingTimer=null;
async function ping(){{
  if(!dwellEnabled)return;
  try{{
    const r=await fetch(pingUrl,{{method:"POST",credentials:"same-origin"}});
    const d=await r.json();
    if(d.banned){{document.getElementById("toast").style.display="block";if(pingTimer)clearInterval(pingTimer);}}
  }}catch(e){{}}
}}
if(dwellEnabled){{ping();pingTimer=setInterval(ping,5000);}}
</script>
</body>
</html>"""


@router.get("/ip-blocked")
def ip_blocked_page(request: Request, db: Session = Depends(get_db)):
    settings = ip_restriction_service.get_settings(db)
    if not settings.get("ip_restriction_enabled"):
        return HTMLResponse('<script>location.href="/login"</script>', status_code=302)
    client_ip = ip_restriction_service.get_client_ip(request)
    if ip_restriction_service.is_ip_allowed(db, client_ip):
        return HTMLResponse('<script>location.href="/login"</script>', status_code=302)
    dwell = ip_restriction_service.touch_ip_blocked_presence(db, client_ip)
    if dwell.get("banned"):
        return JSONResponse(status_code=403, content={"detail": "Доступ заблокирован"})
    html = BLOCKED_HTML.format(
        client_ip=client_ip,
        current_time=time.strftime("%Y-%m-%d %H:%M:%S"),
        dwell_enabled="true" if ip_restriction_service.block_ip_blocked_dwell else "false",
        dwell_seconds=ip_restriction_service.ip_blocked_dwell_seconds,
    )
    return HTMLResponse(html)


@router.api_route("/ip-blocked/ping", methods=["GET", "POST"])
def ip_blocked_ping(request: Request, db: Session = Depends(get_db)):
    settings = ip_restriction_service.get_settings(db)
    if not settings.get("ip_restriction_enabled"):
        return JSONResponse(status_code=404, content={"success": False, "message": "IP-ограничения выключены"})
    client_ip = ip_restriction_service.get_client_ip(request)
    if ip_restriction_service.is_ip_allowed(db, client_ip):
        return {"banned": False, "tracking": False}
    dwell = ip_restriction_service.touch_ip_blocked_presence(db, client_ip)
    if dwell.get("banned"):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": f"Доступ запрещён с вашего IP: {client_ip}", **dwell},
        )
    return {"success": True, **dwell}
