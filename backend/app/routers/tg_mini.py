"""Telegram Mini App API + full UI (ported from AdminAntizapret tg_mini)."""

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/tg-mini", tags=["tg-mini"])
settings = get_settings()

MINI_APP_HTML = """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<title>AntiZapret Mini</title>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6;--ok:#22c55e;--err:#ef4444}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);margin:0;padding:0 0 72px}}
header{{padding:16px;text-align:center;border-bottom:1px solid #334155}}
.tabs{{display:flex;position:fixed;bottom:0;left:0;right:0;background:#1e293b;border-top:1px solid #334155}}
.tab{{flex:1;padding:12px 4px;text-align:center;font-size:12px;color:var(--muted);cursor:pointer;border:none;background:none}}
.tab.active{{color:var(--accent)}}
.panel{{display:none;padding:16px}}
.panel.active{{display:block}}
.card{{background:var(--card);border-radius:12px;padding:14px;margin-bottom:10px}}
.kpi{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.kpi .card{{text-align:center;padding:12px}}
.kpi b{{display:block;font-size:20px;color:var(--accent)}}
.kpi span{{font-size:11px;color:var(--muted)}}
.client{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #334155}}
.client:last-child{{border:none}}
.btn{{background:var(--accent);color:#fff;border:none;padding:8px 14px;border-radius:8px;font-size:13px;cursor:pointer}}
.btn-sm{{padding:6px 10px;font-size:12px}}
.btn-ghost{{background:#334155}}
.status{{padding:12px;text-align:center;color:var(--muted);font-size:13px}}
.err{{color:var(--err)}}.ok{{color:var(--ok)}}
input,select{{width:100%;padding:8px;border-radius:8px;border:1px solid #475569;background:#0f172a;color:var(--text);margin:4px 0 8px}}
</style></head><body>
<header><h2 style="margin:0;font-size:18px">AntiZapret Mini</h2><div id="hdrStatus" class="status">Авторизация...</div></header>
<div id="panel-dash" class="panel active">
<div class="kpi" id="kpi"></div>
<div class="card"><b>Подключённые OpenVPN</b><div id="ovpnList"></div></div>
<div class="card"><b>WireGuard</b><div id="wgList"></div></div>
</div>
<div id="panel-clients" class="panel">
<div id="configList"></div>
</div>
<div id="panel-settings" class="panel">
<div class="card" id="settingsCard">Загрузка...</div>
</div>
<nav class="tabs">
<button class="tab active" data-tab="dash">Дашборд</button>
<button class="tab" data-tab="clients">Конфиги</button>
<button class="tab" data-tab="settings">Настройки</button>
</nav>
<script>
const tg=window.Telegram&&window.Telegram.WebApp;let token=localStorage.getItem('tg_token')||'';
if(tg){{tg.ready();tg.expand();}}
const hdr=document.getElementById('hdrStatus');
async function api(path,opts={{}}){{
  const r=await fetch('/api/tg-mini'+path,{{...opts,headers:{{'Content-Type':'application/json',...(token?{{Authorization:'Bearer '+token}}:{{}}),...(opts.headers||{{}})}}}});
  const d=await r.json().catch(()=>({{}}));
  if(!r.ok)throw new Error(d.detail||d.message||'Ошибка');
  return d;
}}
async function auth(){{
  if(!tg||!tg.initData){{hdr.textContent='Откройте через Telegram';return;}}
  const r=await fetch('/api/tg-mini/auth',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{init_data:tg.initData}})}});
  const d=await r.json();
  if(!r.ok){{hdr.textContent=d.detail||'Ошибка авторизации';hdr.className='status err';return;}}
  token=d.access_token;localStorage.setItem('tg_token',token);
  hdr.textContent='Подключено';hdr.className='status ok';loadAll();
}}
function showTab(name){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
  document.querySelector('[data-tab="'+name+'"]').classList.add('active');
}}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>showTab(t.dataset.tab));
function fmtB(n){{const u=['B','KB','MB','GB'];let i=0,v=n||0;while(v>=1024&&i<u.length-1){{v/=1024;i++;}}return v.toFixed(1)+' '+u[i];}}
async function loadDash(){{
  const d=await api('/dashboard');
  document.getElementById('kpi').innerHTML=
    '<div class="card"><b>'+d.total_configs+'</b><span>Конфигов</span></div>'+
    '<div class="card"><b>'+d.connected_openvpn+'</b><span>OpenVPN</span></div>'+
    '<div class="card"><b>'+d.connected_wireguard+'</b><span>WireGuard</span></div>'+
    '<div class="card"><b>'+(d.server_ip||'—')+'</b><span>Сервер</span></div>';
  document.getElementById('ovpnList').innerHTML=(d.openvpn_clients||[]).map(c=>'<div class="client"><span>'+c.common_name+'</span><span class="ok">online</span></div>').join('')||'<div class="status">Нет подключений</div>';
  document.getElementById('wgList').innerHTML=(d.wireguard_peers||[]).map(p=>'<div class="client"><span>'+(p.client_name||p.public_key.slice(0,8))+'</span><span class="ok">'+fmtB(p.transfer_rx+p.transfer_tx)+'</span></div>').join('')||'<div class="status">Нет пиров</div>';
}}
async function loadConfigs(){{
  const d=await api('/configs');
  document.getElementById('configList').innerHTML=(d.configs||[]).map(c=>'<div class="card"><div class="client"><div><b>'+c.client_name+'</b><br><span style="color:var(--muted);font-size:12px">'+c.vpn_type+'</span></div>'+
    '<button class="btn btn-sm" onclick="sendConfig('+c.id+')">Отправить</button></div></div>').join('')||'<div class="status">Нет конфигов</div>';
}}
async function sendConfig(id){{
  try{{await api('/send-config',{{method:'POST',body:JSON.stringify({{config_id:id}})}});alert('Конфиг отправлен в Telegram');}}
  catch(e){{alert(e.message);}}
}}
async function loadSettings(){{
  try{{
    const d=await api('/settings');
    document.getElementById('settingsCard').innerHTML='<p><b>Сервер:</b> '+(d.server_ip||'—')+'</p><p><b>Бот:</b> '+(d.bot_configured?'настроен':'не настроен')+'</p>';
  }}catch(e){{document.getElementById('settingsCard').innerHTML='<p class="err">'+e.message+'</p>';}}
}}
async function loadAll(){{await loadDash();await loadConfigs();await loadSettings();}}
if(token){{hdr.textContent='Подключено';loadAll();}}else{{auth();}}
</script></body></html>"""


class TelegramAuthRequest(BaseModel):
    init_data: str


class SendConfigRequest(BaseModel):
    config_id: int
    path: str | None = None


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
    return json.loads(parsed.get("user", "{}"))


def _get_bot_token(db: Session) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
    return row.value if row else ""


@router.get("")
def mini_app_page():
    return HTMLResponse(MINI_APP_HTML)


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
        user = User(username=f"tg_{tg_id}", password_hash=get_password_hash(tg_id), role=UserRole.user, is_active=True)
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
        "openvpn_clients": [c.model_dump() if hasattr(c, "model_dump") else c.__dict__ for c in ovpn[:20]],
        "wireguard_peers": [
            {
                "client_name": getattr(p, "client_name", None),
                "public_key": getattr(p, "public_key", ""),
                "transfer_rx": getattr(p, "transfer_rx", 0),
                "transfer_tx": getattr(p, "transfer_tx", 0),
            }
            for p in wg[:20]
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/configs")
def mini_configs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role.value == "admin":
        rows = db.query(VpnConfig).all()
    else:
        rows = db.query(VpnConfig).filter(VpnConfig.owner_id == current_user.id).all()
    return {
        "configs": [
            {
                "id": c.id,
                "client_name": c.client_name,
                "vpn_type": c.vpn_type.value,
            }
            for c in rows
        ]
    }


@router.get("/settings")
def mini_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    adapter = get_active_adapter(db)
    token = _get_bot_token(db)
    return {
        "server_ip": adapter.get_server_ip(),
        "bot_configured": bool(token),
        "username": current_user.username,
        "role": current_user.role.value,
    }


@router.post("/send-config")
def send_config(payload: SendConfigRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = db.query(VpnConfig).filter(VpnConfig.id == payload.config_id).first()
    if not config or (config.owner_id != current_user.id and current_user.role.value != "admin"):
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    if not files:
        raise HTTPException(status_code=404, detail="Файлы конфигурации не найдены")
    path = payload.path or files[0].get("path", "")
    content = adapter.read_profile_file(path)
    token = _get_bot_token(db)
    chat_row = db.query(AppSetting).filter(AppSetting.key == "telegram_chat_id").first()
    if not token:
        raise HTTPException(status_code=503, detail="Telegram не настроен")
    chat_id = chat_row.value if chat_row else ""
    if not chat_id:
        raise HTTPException(status_code=503, detail="Telegram chat_id не настроен")
    from app.services.telegram import send_tg_document
    import os
    import tempfile

    suffix = ".ovpn" if config.vpn_type.value == "openvpn" else ".conf"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        tmp = f.name
    try:
        send_tg_document(token, chat_id, tmp, caption=f"Конфиг: {config.client_name}")
    finally:
        os.unlink(tmp)
    return {"message": "Конфиг отправлен в Telegram"}


@router.post("/check-bot-delivery")
def check_bot_delivery(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    token = _get_bot_token(db)
    if not token:
        return {"success": False, "message": "Бот не настроен"}
    import httpx

    try:
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            return {"success": True, "message": f"Бот @{data['result'].get('username', '')} доступен"}
        return {"success": False, "message": data.get("description", "Ошибка API")}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
