"""Telegram Mini App API + static React UI."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import DEFAULT_TG_NOTIFY_EVENTS, AppSetting, User, VpnConfig, VpnType
from app.routers.maintenance import (
    _admin_notify_settings_response,
    _get_setting,
    _set_setting,
    _telegram_settings_response,
    update_telegram_settings,
)
from app.schemas import (
    AdminNotifySettingsResponse,
    AdminNotifySettingsUpdate,
    MessageResponse,
    TelegramSettingsResponse,
    TelegramSettingsUpdate,
)
from app.services.admin_notify import TG_NOTIFY_EVENT_LABELS, admin_notify_service
from app.services.action_log import log_action
from app.services.feature_guards import get_feature_service
from app.services.ip_restriction import ip_restriction_service
from app.services.node_manager import (
    check_node_health,
    get_active_adapter,
    get_active_node,
    get_active_node_id,
    node_metadata_dict,
    set_active_node_id,
    sync_local_node,
    update_node_from_health,
)
from app.services.notify_time import get_client_timezone_from_request
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.qr_download import QrDownloadService
from app.services.security import SecurityService
from app.services.telegram import send_tg_message
from app.services.tg_mini_status import build_cidr_status_payload, build_warper_status_payload

router = APIRouter(prefix="/tg-mini", tags=["tg-mini"])
settings = get_settings()
_STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "tg_mini"


class TelegramAuthRequest(BaseModel):
    init_data: str


class SendConfigRequest(BaseModel):
    config_id: int
    path: str | None = None


class SendConfigV2Request(BaseModel):
    path: str | None = None
    destination: Literal["self", "chat"] = "self"


def _verify_telegram_init_data(init_data: str, bot_token: str, *, max_age: int = 300) -> dict:
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("hash отсутствует")
    auth_date_raw = (parsed.get("auth_date") or "").strip()
    if not auth_date_raw.isdigit():
        raise ValueError("auth_date отсутствует или некорректен")
    if abs(int(time.time()) - int(auth_date_raw)) > max(30, min(max_age, 86400)):
        raise ValueError("init_data устарел")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if computed != received_hash:
        raise ValueError("Неверная подпись init_data")
    return json.loads(parsed.get("user", "{}"))


def _get_bot_token(db: Session) -> str:
    return _get_setting(db, "telegram_bot_token")


def _static_index() -> Path:
    return _STATIC_DIR / "index.html"


def _qr_download_service(db: Session, request: Request) -> QrDownloadService:
    sec = SecurityService().get_settings(db)
    pin_row = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    base_url = str(request.base_url).rstrip("/")
    return QrDownloadService(
        db,
        base_url=base_url,
        ttl_seconds=sec["qr_download_ttl_seconds"],
        max_downloads=sec["qr_download_max_downloads"],
        pin=pin_row.value if pin_row else "",
    )


def _get_accessible_config(db: Session, config_id: int, current_user: User) -> VpnConfig:
    node = get_active_node(db)
    config = (
        db.query(VpnConfig)
        .filter(VpnConfig.id == config_id, VpnConfig.node_id == node.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if config.owner_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return config


def _resolve_send_chat_id(
    db: Session,
    current_user: User,
    destination: Literal["self", "chat"],
) -> str:
    if destination == "chat":
        if current_user.role.value != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только admin может отправлять в общий chat")
        chat_id = _get_setting(db, "telegram_chat_id").strip()
        if not chat_id:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Глобальный chat_id не настроен")
        return chat_id
    chat_id = (current_user.telegram_id or "").strip()
    if not chat_id and current_user.role.value == "admin":
        chat_id = _get_setting(db, "telegram_chat_id").strip()
    if not chat_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram ID не привязан к вашему аккаунту")
    return chat_id


def _send_config_file(
    db: Session,
    config: VpnConfig,
    current_user: User,
    *,
    path: str | None,
    destination: Literal["self", "chat"],
) -> MessageResponse:
    from app.services.telegram_config_send import send_config_for_user

    token = _get_bot_token(db)
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram не настроен")
    sent, error = send_config_for_user(
        db,
        config,
        current_user,
        bot_token=token,
        path=path,
        destination=destination,
        run_async=False,
    )
    if sent == 0:
        status_code = status.HTTP_404_NOT_FOUND if error == "Файлы конфигурации не найдены" else status.HTTP_502_BAD_GATEWAY
        if error in {
            "Telegram не настроен",
            "Telegram ID не привязан к вашему аккаунту",
            "Глобальный chat_id не настроен",
        }:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        if error == "Только admin может отправлять в общий chat":
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=error or "Не удалось отправить конфиг")
    return MessageResponse(message="Конфиг отправлен в Telegram")


def _serialize_tg_node(node, *, active_id: int | None) -> dict:
    meta = node_metadata_dict(node)
    return {
        "id": node.id,
        "name": node.name,
        "host": node.host,
        "port": node.port,
        "status": node.status.value if hasattr(node.status, "value") else str(node.status),
        "is_local": bool(node.is_local),
        "mtls_enabled": False if node.is_local else bool(node.mtls_enabled),
        "is_active": node.id == active_id,
        "last_seen_at": node.last_seen_at.isoformat() if node.last_seen_at else None,
        "metadata": {
            key: meta[key]
            for key in (
                "server_ip",
                "services_active",
                "services_total",
                "agent_version",
                "antizapret_version",
                "hostname",
                "last_error",
            )
            if key in meta
        },
    }


def _get_tg_node_or_404(node_id: int, db: Session):
    from app.models import Node

    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    return node


@router.get("/nodes")
def mini_list_nodes(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    sync_local_node(db)
    from app.models import Node

    active_id = get_active_node_id(db)
    nodes = db.query(Node).order_by(Node.is_local.desc(), Node.name).all()
    return {
        "active_node_id": active_id,
        "nodes": [_serialize_tg_node(node, active_id=active_id) for node in nodes],
    }


@router.get("/nodes/{node_id}")
def mini_get_node(node_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    sync_local_node(db)
    node = _get_tg_node_or_404(node_id, db)
    active_id = get_active_node_id(db)
    return _serialize_tg_node(node, active_id=active_id)


@router.post("/nodes/{node_id}/health")
def mini_node_health(
    node_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    node = _get_tg_node_or_404(node_id, db)
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.commit()
    db.refresh(node)
    active_id = get_active_node_id(db)
    return {
        "node": _serialize_tg_node(node, active_id=active_id),
        "health": health,
    }


@router.post("/nodes/{node_id}/activate")
def mini_activate_node(
    node_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    node = _get_tg_node_or_404(node_id, db)
    set_active_node_id(db, node.id)
    db.commit()
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.commit()
    db.refresh(node)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_activate",
            user_id=admin.id,
            username=admin.username,
            remote_addr="tg-mini",
            details=f"name={node.name}, id={node.id}",
        )
    active_id = get_active_node_id(db)
    return {
        "node": _serialize_tg_node(node, active_id=active_id),
        "health": health,
    }


@router.get("/warper/status")
def mini_warper_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not get_feature_service().is_enabled("warper"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Модуль WARPER отключён")
    return build_warper_status_payload(db)


@router.get("/cidr/status")
def mini_cidr_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return build_cidr_status_payload(db)


@router.get("/assets/{file_path:path}", include_in_schema=False)
def mini_app_asset(file_path: str):
    asset_path = (_STATIC_DIR / "assets" / file_path).resolve()
    assets_root = (_STATIC_DIR / "assets").resolve()
    if not str(asset_path).startswith(str(assets_root)) or not asset_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(asset_path)


@router.get("")
def mini_app_page(request: Request):
    from app.services.html_csp import serve_html_with_nonce

    index_path = _static_index()
    if not index_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mini App UI не собран. Выполните: cd frontend && npm run build:tg-mini",
        )
    return serve_html_with_nonce(request, index_path)


@router.post("/auth")
def tg_auth(payload: TelegramAuthRequest, request: Request, db: Session = Depends(get_db)):
    token = _get_bot_token(db)
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram bot не настроен")
    try:
        max_age_raw = _get_setting(db, "telegram_auth_max_age_seconds")
        max_age = int(max_age_raw) if max_age_raw.isdigit() else 300
        tg_user = _verify_telegram_init_data(payload.init_data, token, max_age=max_age)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    tg_id = str(tg_user.get("id", ""))
    user = db.query(User).filter(User.telegram_id == tg_id).first()
    if not user:
        user = db.query(User).filter(User.username == f"tg_{tg_id}").first()
        if user and not user.telegram_id:
            user.telegram_id = tg_id
            db.commit()
    if not user:
        admin_notify_service.send_tg_login_unlinked(
            db,
            telegram_id=tg_id,
            remote_addr=ip_restriction_service.get_client_ip(request),
            mini=True,
            client_timezone=get_client_timezone_from_request(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Этот Telegram аккаунт не привязан ни к одному пользователю панели",
        )
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "telegram_id": tg_id}


@router.get("/dashboard")
def mini_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    ovpn = adapter.parse_openvpn_status()
    wg = adapter.parse_wireguard_status()
    node = get_active_node(db)
    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == node.id, VpnConfig.owner_id == current_user.id)
        .count()
    )
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
    node = get_active_node(db)
    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id)
    if current_user.role.value != "admin":
        query = query.filter(VpnConfig.owner_id == current_user.id)
    rows = query.all()
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


@router.get("/configs/{config_id}/files")
def mini_config_files(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, config_id, current_user)
    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файлы конфигурации не найдены")
    return {"files": enrich_profile_files(config.client_name, files)}


@router.post("/configs/{config_id}/send", response_model=MessageResponse)
def mini_send_config(
    config_id: int,
    payload: SendConfigV2Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, config_id, current_user)
    return _send_config_file(db, config, current_user, path=payload.path, destination=payload.destination)


@router.get("/qr-link")
def mini_qr_link(
    request: Request,
    config_id: int = Query(...),
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, config_id, current_user)
    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    if not any(item.get("path") == path for item in files):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    return _qr_download_service(db, request).create_token(
        file_path=path,
        config_type=config.vpn_type.value,
        config_name=build_profile_download_filename(config.client_name, path=path),
        creator_id=current_user.id,
        creator_username=current_user.username,
        remote_addr=request.client.host if request.client else None,
    )


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


@router.get("/admin-notify", response_model=AdminNotifySettingsResponse)
def mini_get_admin_notify(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _admin_notify_settings_response(db, current_user)


@router.patch("/admin-notify", response_model=AdminNotifySettingsResponse)
def mini_update_admin_notify(
    payload: AdminNotifySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.telegram_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Изменение Telegram ID в Mini App недоступно — используйте /link в боте или веб-панель",
        )
    if payload.events is not None:
        merged = current_user.merged_tg_notify_events()
        for key in DEFAULT_TG_NOTIFY_EVENTS:
            if key in payload.events:
                merged[key] = bool(payload.events[key])
        current_user.tg_notify_events = json.dumps(merged)
    db.commit()
    db.refresh(current_user)
    return _admin_notify_settings_response(db, current_user)


@router.post("/admin-notify/test", response_model=MessageResponse)
def mini_test_admin_notify(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите Telegram ID в настройках уведомлений")
    bot_token = _get_bot_token(db)
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    merged = current_user.merged_tg_notify_events()
    enabled = [label for key, label in TG_NOTIFY_EVENT_LABELS if merged.get(key)]
    events_text = "\n".join(f"  ✓ {item}" for item in enabled) if enabled else "  (нет включённых событий)"
    text = (
        "🔔 <b>Тест уведомлений AdminPanelAZ</b>\n\n"
        f"Аккаунт: <code>{current_user.username}</code>\n\n"
        f"Включённые события:\n{events_text}"
    )
    ok = send_tg_message(bot_token, current_user.telegram_id, text, run_async=False)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
    return MessageResponse(message="Тестовое сообщение отправлено")


@router.get("/telegram-settings", response_model=TelegramSettingsResponse)
def mini_get_telegram_settings(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _telegram_settings_response(db, request)


@router.patch("/telegram-settings", response_model=TelegramSettingsResponse)
def mini_update_telegram_settings(
    payload: TelegramSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return update_telegram_settings(payload, request, db, admin)


@router.post("/telegram-settings/test", response_model=MessageResponse)
def mini_test_telegram(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    bot_token = _get_bot_token(db)
    chat_id = _get_setting(db, "telegram_chat_id")
    if not bot_token or not chat_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите токен бота и chat_id")
    ok = send_tg_message(
        bot_token,
        chat_id,
        "✅ <b>AdminPanelAZ</b>: тестовое уведомление Telegram",
        run_async=False,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
    return MessageResponse(message="Тестовое сообщение отправлено")


@router.post("/send-config", response_model=MessageResponse, deprecated=True)
def send_config(
    payload: SendConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _get_accessible_config(db, payload.config_id, current_user)
    return _send_config_file(db, config, current_user, path=payload.path, destination="self")


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
