"""Permanent client portal links on a dedicated portal_domain host."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AmneziaWg2AccessPolicy,
    AppSetting,
    ClientPortalToken,
    OpenVpnAccessPolicy,
    User,
    UserTrafficStatProtocol,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
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
    """Require Host to match configured portal_domain.

    Deployment note: this check is only as strong as the reverse proxy's
    virtual-host pinning. Terminate TLS and reject unmatched Host at the edge
    so public portal write paths (including redeem) cannot be reached by
    spoofing Host against a direct upstream bind.
    """
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


def _portal_protocol_for_file(file_item: dict, config: VpnConfig) -> str:
    """Prefer on-disk profile protocol (WG vs AWG) over DB vpn_type.

    AmneziaWG clients are stored as VpnType.wireguard but expose both
    ``wireguard`` and ``amneziawg`` profile files — same split as dashboard tabs.
    """
    proto = (file_item.get("protocol") or "").strip().lower()
    if proto in {"openvpn", "wireguard", "amneziawg", "amneziawg2"}:
        return proto
    return config.vpn_type.value


def _protocol_feature_key(protocol: str) -> str | None:
    if protocol == "openvpn":
        return "openvpn"
    if protocol == "wireguard":
        return "wireguard"
    if protocol == "amneziawg":
        return "amneziawg"
    if protocol == "amneziawg2":
        return "awg2"
    return None


def _protocol_feature_enabled(protocol: str) -> bool:
    key = _protocol_feature_key(protocol)
    if not key:
        return True
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled(key)


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
            protocol = _portal_protocol_for_file(f, config)
            if not _protocol_feature_enabled(protocol):
                continue
            filename = (
                f.get("download_filename")
                or build_profile_download_filename(
                    config.client_name,
                    protocol=protocol,
                    variant=f.get("variant", ""),
                    path=path,
                )
            )
            label = f.get("name") or filename
            out.append(
                {
                    "path": path,
                    "label": label,
                    "filename": filename,
                    "vpn_type": protocol,
                    "config_id": config.id,
                }
            )
    return out


def _setting_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row and (row.value or "").strip():
        return (row.value or "").strip()
    return default


def _format_bytes_label(n: int) -> str:
    value = float(max(0, int(n or 0)))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    return f"{value:.2f} {units[idx]}"


def _policy_blocked(policy) -> bool:
    if policy is None:
        return False
    if bool(getattr(policy, "is_permanent_blocked", False)):
        return True
    if bool(getattr(policy, "is_temp_blocked", False)):
        return True
    until = getattr(policy, "block_until", None)
    if until is None:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        return until > now
    except TypeError:
        return False


def _collect_access_policies(db: Session, *, node_id: int, client_name: str, protocols: set[str]) -> list:
    policies = []
    if "openvpn" in protocols:
        policies.append(
            db.query(OpenVpnAccessPolicy)
            .filter(OpenVpnAccessPolicy.node_id == node_id, OpenVpnAccessPolicy.client_name == client_name)
            .first()
        )
    if "wireguard" in protocols or "amneziawg" in protocols:
        policies.append(
            db.query(WgAccessPolicy)
            .filter(WgAccessPolicy.node_id == node_id, WgAccessPolicy.client_name == client_name)
            .first()
        )
    if "amneziawg2" in protocols:
        policies.append(
            db.query(AmneziaWg2AccessPolicy)
            .filter(
                AmneziaWg2AccessPolicy.node_id == node_id,
                AmneziaWg2AccessPolicy.client_name == client_name,
            )
            .first()
        )
    return [p for p in policies if p is not None]


def _earliest_datetime(values: list[datetime | None]) -> datetime | None:
    present = [v for v in values if v is not None]
    return min(present) if present else None


def _format_expires_label(expires_at: datetime | None, *, now: datetime | None = None) -> str:
    if expires_at is None:
        return "Бессрочно"
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    delta = expires_at - current
    days_left = delta.days if delta.total_seconds() > 0 else 0
    until = expires_at.strftime("%d.%m.%Y")
    if days_left <= 0:
        return f"истёк {until}"
    return f"{days_left} дн. (до {until})"


def build_portal_status(db: Session, *, node_id: int, client_name: str, configs: list[VpnConfig]) -> dict:
    """Account overview for the public portal (status / expiry / traffic)."""
    protocols = {c.vpn_type.value for c in configs}
    policies = _collect_access_policies(db, node_id=node_id, client_name=client_name, protocols=protocols)
    blocked = any(_policy_blocked(p) for p in policies)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    access_until_candidates: list[datetime | None] = []
    for p in policies:
        for attr in ("expires_at", "access_until"):
            value = getattr(p, attr, None)
            if isinstance(value, datetime):
                access_until_candidates.append(value)
    access_until = _earliest_datetime(access_until_candidates)
    access_expired = bool(access_until and access_until <= now)

    if access_until is not None:
        expires_at = access_until
    else:
        # Prefer actual access deadlines over certificate notAfter.
        expiry_candidates: list[datetime | None] = []
        for c in configs:
            expiry_candidates.append(getattr(c, "expires_at", None))
            expiry_candidates.append(getattr(c, "cert_expires_at", None))
        expires_at = _earliest_datetime(expiry_candidates)

    expired = bool(expires_at and expires_at <= now)

    if blocked:
        status_key = "blocked"
        status_label = "Заблокирована"
    elif access_expired or expired:
        status_key = "expired"
        status_label = "Истекла"
    else:
        status_key = "active"
        status_label = "Активна"

    expires_label = _format_expires_label(expires_at, now=now)

    stats = (
        db.query(UserTrafficStatProtocol)
        .filter(
            UserTrafficStatProtocol.node_id == node_id,
            UserTrafficStatProtocol.common_name == client_name,
        )
        .all()
    )
    used_bytes = sum(int(r.total_received or 0) + int(r.total_sent or 0) for r in stats)

    limit_candidates = [
        int(p.traffic_limit_bytes)
        for p in policies
        if getattr(p, "traffic_limit_bytes", None) is not None and int(p.traffic_limit_bytes or 0) > 0
    ]
    limit_bytes = min(limit_candidates) if limit_candidates else None

    if limit_bytes is None:
        traffic_label = f"{_format_bytes_label(used_bytes)} / ∞"
    else:
        traffic_label = f"{_format_bytes_label(used_bytes)} / {_format_bytes_label(limit_bytes)}"

    return {
        "status": status_key,
        "status_label": status_label,
        "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
        "expires_label": expires_label,
        "traffic_used_bytes": used_bytes,
        "traffic_limit_bytes": limit_bytes,
        "traffic_label": traffic_label,
    }


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
    brand = _setting_value(db, "app_name") or "VPN"
    # Shorten default panel name for the public page
    if brand.lower().startswith("adminpanel"):
        brand = "VPN"
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
        if item["vpn_type"] == "openvpn" or (item["filename"] or "").lower().endswith(".ovpn"):
            entry["openvpn_import_url"] = openvpn_import_url(download_url)
        files.append(entry)
    # Protocols shown on the page = enabled profile protocols actually present.
    protocols = sorted({f["vpn_type"] for f in files})
    from app.services.feature_guards import get_feature_service

    return {
        "client_name": token_row.client_name,
        "brand_title": brand,
        "protocols": protocols,
        "files": files,
        "unlock_codes_enabled": get_feature_service().is_enabled("unlock_codes"),
        "status": build_portal_status(
            db,
            node_id=token_row.node_id,
            client_name=token_row.client_name,
            configs=configs,
        ),
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
