"""Permanent client portal links on a dedicated portal_domain host."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, ClientPortalToken, User, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.groups import find_sync_group_containing_node
from app.services.panel_publish_info import public_https_origin_url
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files


_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def normalize_portal_domain(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return ""
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0].strip()
    # strip port for storage; public_https_origin_url re-appends HTTPS_PUBLIC_PORT
    value = value.split(":")[0].strip()
    if not value or not _HOSTNAME_RE.match(value):
        raise ValueError("Некорректный хост портала (ожидается поддомен, например sub.example.com)")
    return value


def get_portal_domain(db: Session) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == "portal_domain").first()
    return (row.value or "").strip() if row else ""


def set_portal_domain(db: Session, raw: str | None) -> str:
    host = normalize_portal_domain(raw) if raw is not None else ""
    row = db.query(AppSetting).filter(AppSetting.key == "portal_domain").first()
    if row:
        row.value = host
    else:
        db.add(AppSetting(key="portal_domain", value=host))
    return host


def resolve_portal_base_url(db: Session) -> str | None:
    host = get_portal_domain(db)
    if not host:
        return None
    settings = get_settings()
    origin = public_https_origin_url(host, settings.https_public_port)
    if not origin:
        return None
    from app.services.panel_paths import access_path

    prefix = access_path(settings)
    if prefix:
        return f"{origin}{prefix}"
    return origin


def portal_page_url(db: Session, token: str) -> str:
    base = resolve_portal_base_url(db)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Задайте поддомен клиентского портала в настройках выдачи профилей",
        )
    return f"{base}/p/{token}"


def openvpn_import_url(https_download_url: str) -> str:
    return f"openvpn://import-profile/{https_download_url}"


def _request_host(request_host: str | None) -> str:
    host = (request_host or "").split(",")[0].strip().lower()
    return host.split(":")[0].strip()


def assert_portal_host(db: Session, request_host: str | None) -> None:
    expected = get_portal_domain(db)
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    got = _request_host(request_host)
    if got != expected.lower():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _portal_node_id(db: Session) -> int:
    active = get_active_node(db)
    group, _role = find_sync_group_containing_node(db, active.id)
    if group:
        return group.primary_node_id
    return active.id


def _active_token(db: Session, *, node_id: int, client_name: str) -> ClientPortalToken | None:
    return (
        db.query(ClientPortalToken)
        .filter(
            ClientPortalToken.node_id == node_id,
            ClientPortalToken.client_name == client_name,
            ClientPortalToken.revoked_at.is_(None),
        )
        .order_by(ClientPortalToken.id.desc())
        .first()
    )


def _new_token_value() -> str:
    return secrets.token_urlsafe(18)


def ensure_client_configs(db: Session, client_name: str) -> list[VpnConfig]:
    name = (client_name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не указан клиент")
    node_id = _portal_node_id(db)
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == name,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    if not configs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")
    return configs


def get_or_create_portal_token(
    db: Session,
    *,
    client_name: str,
    creator: User | None = None,
) -> ClientPortalToken:
    configs = ensure_client_configs(db, client_name)
    node_id = configs[0].node_id
    name = configs[0].client_name
    existing = _active_token(db, node_id=node_id, client_name=name)
    if existing:
        return existing
    row = ClientPortalToken(
        token=_new_token_value(),
        node_id=node_id,
        client_name=name,
        created_by_user_id=creator.id if creator else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def rotate_portal_token(
    db: Session,
    *,
    client_name: str,
    creator: User | None = None,
) -> ClientPortalToken:
    configs = ensure_client_configs(db, client_name)
    node_id = configs[0].node_id
    name = configs[0].client_name
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in (
        db.query(ClientPortalToken)
        .filter(
            ClientPortalToken.node_id == node_id,
            ClientPortalToken.client_name == name,
            ClientPortalToken.revoked_at.is_(None),
        )
        .all()
    ):
        row.revoked_at = now
    new_row = ClientPortalToken(
        token=_new_token_value(),
        node_id=node_id,
        client_name=name,
        created_by_user_id=creator.id if creator else None,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


def revoke_portal_token(db: Session, *, client_name: str) -> None:
    configs = ensure_client_configs(db, client_name)
    node_id = configs[0].node_id
    name = configs[0].client_name
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (
        db.query(ClientPortalToken)
        .filter(
            ClientPortalToken.node_id == node_id,
            ClientPortalToken.client_name == name,
            ClientPortalToken.revoked_at.is_(None),
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка портала не найдена")
    for row in rows:
        row.revoked_at = now
    db.commit()


def get_valid_portal_token(db: Session, token: str) -> ClientPortalToken:
    row = db.query(ClientPortalToken).filter(ClientPortalToken.token == token).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка недействительна")
    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ссылка отозвана")
    return row


def _list_files_for_configs(db: Session, configs: list[VpnConfig]) -> list[dict]:
    adapter = get_active_adapter(db)
    out: list[dict] = []
    for config in configs:
        files = adapter.get_profile_files(config.client_name, config.vpn_type)
        files = enrich_profile_files(config.client_name, files)
        for f in files:
            path = f.get("path") or ""
            if not path:
                continue
            filename = build_profile_download_filename(config.client_name, path=path)
            label = f.get("name") or filename
            out.append(
                {
                    "path": path,
                    "label": label,
                    "filename": filename,
                    "vpn_type": config.vpn_type.value,
                    "config_id": config.id,
                }
            )
    return out


def build_portal_payload(db: Session, token_row: ClientPortalToken) -> dict:
    base = resolve_portal_base_url(db)
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == token_row.node_id,
            VpnConfig.client_name == token_row.client_name,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    files_meta = _list_files_for_configs(db, configs)
    files = []
    for item in files_meta:
        download_url = f"{base}/api/public/portal/{token_row.token}/download?path={quote(item['path'], safe='')}"
        entry = {
            "path": item["path"],
            "label": item["label"],
            "filename": item["filename"],
            "vpn_type": item["vpn_type"],
            "download_url": download_url,
        }
        if item["vpn_type"] == VpnType.openvpn.value or (item["filename"] or "").lower().endswith(".ovpn"):
            entry["openvpn_import_url"] = openvpn_import_url(download_url)
        files.append(entry)
    protocols = sorted({c.vpn_type.value for c in configs})
    return {
        "client_name": token_row.client_name,
        "brand_title": "VPN",
        "protocols": protocols,
        "files": files,
    }


def read_portal_profile(db: Session, token_row: ClientPortalToken, path: str) -> tuple[str, str | bytes]:
    path = (path or "").strip()
    if not path or ".." in path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный путь")
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == token_row.node_id,
            VpnConfig.client_name == token_row.client_name,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    allowed = {item["path"] for item in _list_files_for_configs(db, configs)}
    if path not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    adapter = get_active_adapter(db)
    hosts = load_node_remote_hosts(db, token_row.node_id)
    content = read_profile_file_for_delivery(adapter, path, hosts)
    filename = build_profile_download_filename(token_row.client_name, path=path)
    return filename, content


def link_response(db: Session, row: ClientPortalToken) -> dict:
    return {
        "token": row.token,
        "client_name": row.client_name,
        "url": portal_page_url(db, row.token),
        "revoked": row.revoked_at is not None,
    }
