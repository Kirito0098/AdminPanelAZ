"""Telegram Mini App API + full UI (ported from AdminAntizapret tg_mini)."""

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/tg-mini", tags=["tg-mini"])
settings = get_settings()
_STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "tg_mini"

MINI_APP_HTML = """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="stylesheet" href="/api/tg-mini/assets/tg_mini_app.css">
<title>AntiZapret Mini</title>
</head>
<body class="tg-mini-app">
<main class="tg-mini-main">
<div class="tg-mini-shell" id="tgMiniApp">
  <header class="tg-mini-header">
    <p class="tg-mini-kicker">AdminPanelAZ</p>
    <h1 class="tg-mini-brand">Панель в Telegram</h1>
    <div id="hdrStatus" class="tg-mini-status">Авторизация...</div>
  </header>

  <div class="tg-mini-tabs-sticky">
    <nav class="tg-mini-tabs" role="tablist" aria-label="Mini app tabs">
      <button class="tg-mini-tab is-active" data-pane="dash" type="button">Дашборд</button>
      <button class="tg-mini-tab" data-pane="clients" type="button">Конфиги</button>
      <button class="tg-mini-tab" data-pane="settings" type="button">Настройки</button>
    </nav>
  </div>

  <section class="tg-mini-pane is-active" data-pane="dash">
    <div class="tg-mini-cards" id="kpi"></div>
    <article class="tg-mini-panel"><h3>Подключённые OpenVPN</h3><div id="ovpnList"></div></article>
    <article class="tg-mini-panel"><h3>WireGuard</h3><div id="wgList"></div></article>
  </section>

  <section class="tg-mini-pane" data-pane="clients">
    <div id="configList"></div>
  </section>

  <section class="tg-mini-pane" data-pane="settings">
    <article class="tg-mini-panel" id="settingsCard">Загрузка...</article>
  </section>
</div>
</main>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
let token = localStorage.getItem('tg_token') || '';
if (tg) { tg.ready(); tg.expand(); }
const hdr = document.getElementById('hdrStatus');

function openBottomSheet(html) {
  const modal = document.createElement('div');
  modal.className = 'tg-mini-modal';
  modal.innerHTML =
    '<div class="tg-mini-modal-backdrop"></div>' +
    '<div class="tg-mini-modal-dialog" role="dialog" aria-modal="true">' +
    '<div class="tg-mini-modal-handle" aria-hidden="true"></div>' + html + '</div>';
  const close = () => {
    modal.classList.remove('is-open');
    document.body.classList.remove('tg-mini-modal-open');
    setTimeout(() => modal.remove(), 220);
  };
  modal.querySelector('.tg-mini-modal-backdrop').onclick = close;
  const closeBtn = modal.querySelector('.tg-mini-modal-close');
  if (closeBtn) closeBtn.onclick = close;
  document.body.appendChild(modal);
  document.body.classList.add('tg-mini-modal-open');
  requestAnimationFrame(() => modal.classList.add('is-open'));
  return { modal, close };
}

async function api(path, opts = {}) {
  const r = await fetch('/api/tg-mini' + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(opts.headers || {}),
    },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || d.message || 'Ошибка');
  return d;
}

async function auth() {
  if (!tg || !tg.initData) {
    hdr.textContent = 'Откройте через Telegram';
    hdr.className = 'tg-mini-status is-error';
    return;
  }
  const r = await fetch('/api/tg-mini/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: tg.initData }),
  });
  const d = await r.json();
  if (!r.ok) {
    hdr.textContent = d.detail || 'Ошибка авторизации';
    hdr.className = 'tg-mini-status is-error';
    return;
  }
  token = d.access_token;
  localStorage.setItem('tg_token', token);
  hdr.textContent = 'Подключено';
  hdr.className = 'tg-mini-status is-success';
  loadAll();
}

function showPane(name) {
  document.querySelectorAll('.tg-mini-pane').forEach((p) => p.classList.remove('is-active'));
  document.querySelectorAll('.tg-mini-tab').forEach((t) => t.classList.remove('is-active'));
  document.querySelector('[data-pane="' + name + '"].tg-mini-pane').classList.add('is-active');
  document.querySelector('.tg-mini-tab[data-pane="' + name + '"]').classList.add('is-active');
}

document.querySelectorAll('.tg-mini-tab').forEach((t) => {
  t.onclick = () => showPane(t.dataset.pane);
});

function fmtB(n) {
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n || 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(1) + ' ' + u[i];
}

async function loadDash() {
  const d = await api('/dashboard');
  document.getElementById('kpi').innerHTML =
    '<article class="tg-mini-card"><b>' + d.total_configs + '</b><span>Конфигов</span></article>' +
    '<article class="tg-mini-card"><b>' + d.connected_openvpn + '</b><span>OpenVPN</span></article>' +
    '<article class="tg-mini-card"><b>' + d.connected_wireguard + '</b><span>WireGuard</span></article>' +
    '<article class="tg-mini-card"><b>' + (d.server_ip || '—') + '</b><span>Сервер</span></article>';
  document.getElementById('ovpnList').innerHTML = (d.openvpn_clients || [])
    .map((c) => '<div class="tg-mini-client"><span>' + c.common_name + '</span><span style="color:var(--ok)">online</span></div>')
    .join('') || '<div class="tg-mini-empty">Нет подключений</div>';
  document.getElementById('wgList').innerHTML = (d.wireguard_peers || [])
    .map((p) => '<div class="tg-mini-client"><span>' + (p.client_name || p.public_key.slice(0, 8)) + '</span><span style="color:var(--ok)">' + fmtB(p.transfer_rx + p.transfer_tx) + '</span></div>')
    .join('') || '<div class="tg-mini-empty">Нет пиров</div>';
}

async function loadConfigs() {
  const d = await api('/configs');
  document.getElementById('configList').innerHTML = (d.configs || [])
    .map((c) =>
      '<article class="tg-mini-panel"><div class="tg-mini-client"><div><b>' + c.client_name + '</b><br><span style="color:var(--muted);font-size:12px">' + c.vpn_type + '</span></div>' +
      '<button class="tg-mini-btn tg-mini-btn-sm" data-send="' + c.id + '">Отправить</button></div></article>'
    )
    .join('') || '<div class="tg-mini-empty">Нет конфигов</div>';
  document.querySelectorAll('[data-send]').forEach((btn) => {
    btn.onclick = () => confirmSendConfig(Number(btn.dataset.send), btn.closest('.tg-mini-panel')?.querySelector('b')?.textContent || '');
  });
}

function confirmSendConfig(id, name) {
  const sheet = openBottomSheet(
    '<button type="button" class="tg-mini-modal-close" aria-label="Закрыть">×</button>' +
    '<div class="tg-mini-modal-header"><h4>Отправить конфиг</h4>' +
    '<p class="tg-mini-modal-message">Конфиг «' + name + '» будет отправлен в Telegram.</p></div>' +
    '<div class="tg-mini-modal-actions">' +
    '<button type="button" class="tg-mini-btn tg-mini-btn-ghost tg-mini-cancel">Отмена</button>' +
    '<button type="button" class="tg-mini-btn tg-mini-submit">Отправить</button></div>'
  );
  sheet.modal.querySelector('.tg-mini-cancel').onclick = sheet.close;
  sheet.modal.querySelector('.tg-mini-submit').onclick = async () => {
    const btn = sheet.modal.querySelector('.tg-mini-submit');
    btn.disabled = true;
    try {
      await api('/send-config', { method: 'POST', body: JSON.stringify({ config_id: id }) });
      sheet.close();
      const ok = openBottomSheet(
        '<div class="tg-mini-modal-header"><h4>Готово</h4><p class="tg-mini-modal-message">Конфиг отправлен в Telegram.</p></div>' +
        '<div class="tg-mini-modal-actions"><button type="button" class="tg-mini-btn tg-mini-ok">OK</button></div>'
      );
      ok.modal.querySelector('.tg-mini-ok').onclick = ok.close;
    } catch (e) {
      btn.disabled = false;
      alert(e.message);
    }
  };
}

async function loadSettings() {
  try {
    const d = await api('/settings');
    document.getElementById('settingsCard').innerHTML =
      '<h3>Настройки</h3><p><b>Сервер:</b> ' + (d.server_ip || '—') + '</p>' +
      '<p><b>Бот:</b> ' + (d.bot_configured ? 'настроен' : 'не настроен') + '</p>' +
      '<p><b>Пользователь:</b> ' + d.username + '</p>';
  } catch (e) {
    document.getElementById('settingsCard').innerHTML = '<p style="color:var(--err)">' + e.message + '</p>';
  }
}

async function loadAll() {
  await loadDash();
  await loadConfigs();
  await loadSettings();
}

if (token) {
  hdr.textContent = 'Подключено';
  hdr.className = 'tg-mini-status is-success';
  loadAll();
} else {
  auth();
}
</script>
</body></html>"""


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


@router.get("/assets/tg_mini_app.css", include_in_schema=False)
def mini_app_css():
    css_path = _STATIC_DIR / "tg_mini_app.css"
    return FileResponse(css_path, media_type="text/css")


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
