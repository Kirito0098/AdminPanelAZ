"""Shared helpers and models for Telegram Mini App router package."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, User, VpnConfig
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.panel_publish_info import resolve_public_base_url
from app.services.qr_download import QrDownloadService
from app.services.security import SecurityService

settings = get_settings()
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "tg_mini"


class TelegramAuthRequest(BaseModel):
    init_data: str


class SendConfigV2Request(BaseModel):
    path: str | None = None
    destination: Literal["self", "owner"] = "self"
    platform: Literal["ios", "mac", "windows", "android", "linux"] | None = None


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
    base_url = resolve_public_base_url(request)
    return QrDownloadService(
        db,
        base_url=base_url,
        ttl_seconds=sec["qr_download_ttl_seconds"],
        max_downloads=sec["qr_download_max_downloads"],
        pin=pin_row.value if pin_row else "",
    )


def _get_accessible_config(db: Session, config_id: int, current_user: User) -> VpnConfig:
    from app.services.config_access import can_view_config
    from app.services.node_manager import get_active_node

    node = get_active_node(db)
    config = (
        db.query(VpnConfig)
        .filter(VpnConfig.id == config_id, VpnConfig.node_id == node.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not can_view_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return config


def _send_config_file(
    db: Session,
    config: VpnConfig,
    current_user: User,
    *,
    path: str | None,
    destination: Literal["self", "owner"],
    install_platform: Literal["ios", "mac", "windows", "android", "linux"] | None = None,
):
    from app.routers import tg_mini as root
    from app.schemas import MessageResponse
    from app.services.telegram_config_send import send_config_for_user

    token = root._get_bot_token(db)
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram не настроен")
    if destination == "owner" and current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    sent, error = send_config_for_user(
        db,
        config,
        current_user,
        bot_token=token,
        path=path,
        destination=destination,
        run_async=False,
        install_platform=install_platform,
    )
    if sent == 0:
        status_code = status.HTTP_502_BAD_GATEWAY
        if error == "Файлы конфигурации не найдены":
            status_code = status.HTTP_404_NOT_FOUND
        elif error == "Недостаточно прав":
            status_code = status.HTTP_403_FORBIDDEN
        elif error in {"У пользователя не привязан Telegram", "Владелец конфига не найден"}:
            status_code = status.HTTP_400_BAD_REQUEST
        elif error in {
            "Telegram не настроен",
            "Telegram ID не привязан к вашему аккаунту",
        }:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=status_code, detail=error or "Не удалось отправить конфиг")
    if error:
        return MessageResponse(message=error)
    if destination == "owner":
        if install_platform:
            return MessageResponse(message="Конфиг и инструкция отправлены пользователю в Telegram")
        return MessageResponse(message="Конфиг отправлен пользователю в Telegram")
    if install_platform:
        return MessageResponse(message="Конфиг и инструкция отправлены в Telegram")
    return MessageResponse(message="Конфиг отправлен в Telegram")


def _serialize_tg_node(node, *, active_id: int | None) -> dict:
    from app.services.node_manager import node_metadata_dict

    meta = node_metadata_dict(node)
    return {
        "id": node.id,
        "name": node.name,
        "host": node.host,
        "port": node.port,
        "status": node.status.value if hasattr(node.status, "value") else str(node.status),
        "is_local": bool(node.is_local),
        "mtls_enabled": False if node.is_local else bool(node.mtls_enabled),
        "node_kind": (getattr(node, "node_kind", None) or "vpn"),
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
