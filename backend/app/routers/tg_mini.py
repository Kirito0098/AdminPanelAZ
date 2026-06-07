"""Telegram Mini App API (core endpoints ported from AdminAntizapret tg_mini)."""

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User, VpnConfig
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/tg-mini", tags=["tg-mini"])
settings = get_settings()


class TelegramAuthRequest(BaseModel):
    init_data: str


class SendConfigRequest(BaseModel):
    config_id: int
    path: str


def _verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("hash отсутствует")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if computed != received_hash:
        raise ValueError("Неверная подпись init_data")
    user_raw = parsed.get("user", "{}")
    return json.loads(user_raw)


def _get_bot_token(db: Session) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
    return row.value if row else ""


@router.get("")
def mini_app_page():
    html = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <title>AntiZapret Mini</title>
    <style>body{font-family:system-ui;background:var(--tg-theme-bg-color,#111);color:var(--tg-theme-text-color,#eee);margin:0;padding:16px}
    .card{background:var(--tg-theme-secondary-bg-color,#222);border-radius:12px;padding:16px;margin-bottom:12px}
    button{background:var(--tg-theme-button-color,#2481cc);color:var(--tg-theme-button-text-color,#fff);border:none;padding:10px 16px;border-radius:8px;width:100%;margin-top:8px}
    </style></head><body>
    <h2>AntiZapret Mini</h2><div id="status" class="card">Авторизация...</div><div id="dashboard"></div>
    <script>
    const tg=window.Telegram.WebApp;tg.ready();tg.expand();
    async function auth(){const r=await fetch('/api/tg-mini/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData})});
    const d=await r.json();if(!r.ok){document.getElementById('status').textContent=d.detail||'Ошибка';return;}
    localStorage.setItem('tg_token',d.access_token);loadDashboard();}
    async function loadDashboard(){const t=localStorage.getItem('tg_token');
    const r=await fetch('/api/tg-mini/dashboard',{headers:{Authorization:'Bearer '+t}});
    const d=await r.json();document.getElementById('status').textContent='Подключено';
    document.getElementById('dashboard').innerHTML='<div class="card"><b>Клиентов:</b> '+d.total_configs+
    '<br><b>OpenVPN:</b> '+d.connected_openvpn+'<br><b>WireGuard:</b> '+d.connected_wireguard+'</div>';}
    auth();
    </script></body></html>"""
    return HTMLResponse(html)


@router.post("/auth")
def tg_auth(payload: TelegramAuthRequest, db: Session = Depends(get_db)):
    token = _get_bot_token(db)
    if not token:
        raise HTTPException(status_code=503, detail="Telegram bot не настроен")
    try:
        tg_user = _verify_telegram_init_data(payload.init_data, token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    tg_id = str(tg_user.get("id", ""))
    user = db.query(User).filter(User.username == f"tg_{tg_id}").first()
    if not user:
        from app.auth import get_password_hash
        from app.models import UserRole
        user = User(
            username=f"tg_{tg_id}",
            password_hash=get_password_hash(tg_id),
            role=UserRole.user,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "telegram_id": tg_id}


@router.get("/dashboard")
def mini_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    ovpn = adapter.parse_openvpn_status()
    wg = adapter.parse_wireguard_status()
    configs = db.query(VpnConfig).filter(VpnConfig.owner_id == current_user.id).count()
    return {
        "total_configs": configs,
        "connected_openvpn": len(ovpn),
        "connected_wireguard": sum(1 for p in wg if p.latest_handshake),
        "server_ip": adapter.get_server_ip(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/send-config")
def send_config(payload: SendConfigRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = db.query(VpnConfig).filter(VpnConfig.id == payload.config_id).first()
    if not config or (config.owner_id != current_user.id and current_user.role.value != "admin"):
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    content = get_active_adapter(db).read_profile_file(payload.path)
    chat_row = db.query(AppSetting).filter(AppSetting.key == "telegram_chat_id").first()
    token = _get_bot_token(db)
    if not token or not chat_row:
        raise HTTPException(status_code=503, detail="Telegram не настроен")
    from app.services.telegram import send_tg_document
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ovpn", delete=False) as f:
        f.write(content)
        tmp = f.name
    try:
        send_tg_document(token, chat_row.value, tmp, caption=f"Конфиг: {config.client_name}")
    finally:
        os.unlink(tmp)
    return {"message": "Конфиг отправлен в Telegram"}
