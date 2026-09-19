"""Permanent client portal links on a dedicated portal_domain host."""

from __future__ import annotations

from dataclasses import dataclass
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AmneziaWg2AccessPolicy,
    AppSetting,
    ClientPortalToken,
    Node,
    OpenVpnAccessPolicy,
    User,
    UserPortalToken,
    UserTrafficStatProtocol,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
from app.services.node_manager import get_adapter_for_node, get_active_node
from app.services.node_sync.groups import find_sync_group_containing_node
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files


_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)

PORTAL_RESTORE_HINT = (
    "Данные портала и unlock восстановлены из БД. "
    "Nginx/TLS портала не входят в архив — откройте Подписка и нажмите "
    "«Настроить под текущую публикацию»."
)


@dataclass(frozen=True)
class PortalTokenResolution:
    kind: Literal["client", "user"]
    client_row: ClientPortalToken | None = None
    user_row: UserPortalToken | None = None


def read_portal_domain_from_sqlite(db_path: Path | str) -> str:
    """Read ``portal_domain`` from a restored SQLite file (no SQLAlchemy session)."""
    path = Path(db_path)
    if not path.is_file():
        return ""
    try:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
                ("portal_domain",),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return ""
    return (row[0] or "").strip() if row else ""


def sync_portal_domain_after_restore(*, db_path: Path | str, env_path: Path | str) -> dict:
    """Align ``PORTAL_DOMAIN`` in ``.env`` with restored DB; do not run nginx/certbot."""
    from app.services.env_file import EnvFileService

    host = read_portal_domain_from_sqlite(db_path)
    env = EnvFileService(env_path)
    if not host:
        env.remove_env_key("PORTAL_DOMAIN")
        return {
            "portal_domain": None,
            "portal_reprovision_needed": False,
        }
    env.set_env_value("PORTAL_DOMAIN", host)
    return {
        "portal_domain": host,
        "portal_reprovision_needed": True,
        "portal_hint": PORTAL_RESTORE_HINT,
    }


def suggest_portal_domain(panel_domain: str | None) -> str:
    """Suggest a short portal host: portal.<apex> when panel is panel./admin./… subdomain."""
    host = (panel_domain or "").strip().lower()
    host = re.sub(r"^https?://", "", host)
    host = host.split("/")[0].split(":")[0].strip()
    if not host or not _HOSTNAME_RE.match(host):
        return ""
    if host.startswith("portal."):
        # panel host already uses portal. — use clients.<rest>
        rest = host[len("portal.") :]
        return f"clients.{rest}" if rest else ""
    labels = host.split(".")
    # panel.example.com → portal.example.com (sibling suggestion; nested portal.panel.* also valid)
    if len(labels) >= 3 and labels[0] in {"panel", "admin", "app", "ui", "cp", "manage"}:
        return "portal." + ".".join(labels[1:])
    return f"portal.{host}"


def assert_portal_domain_not_panel(portal_host: str, panel_domain: str | None) -> None:
    portal = (portal_host or "").strip().lower().split(":")[0]
    panel = (panel_domain or "").strip().lower().split(":")[0]
    if portal and panel and portal == panel:
        raise ValueError(
            "Хост портала не должен совпадать с доменом панели. "
            f"Укажите поддомен, например {suggest_portal_domain(panel) or 'portal.example.com'}."
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


def set_portal_domain(db: Session, raw: str | None, *, panel_domain: str | None = None) -> str:
    host = normalize_portal_domain(raw) if raw is not None else ""
    if host:
        if panel_domain is None:
            from app.config import get_settings

            panel_domain = (get_settings().domain or "").strip()
        assert_portal_domain_not_panel(host, panel_domain)
        from app.services.antizapret_settings import format_az_panel_domain_conflict_message

        az_conflict = format_az_panel_domain_conflict_message(host)
        if az_conflict:
            raise ValueError(az_conflict)
    row = db.query(AppSetting).filter(AppSetting.key == "portal_domain").first()
    if row:
        row.value = host
    else:
        db.add(AppSetting(key="portal_domain", value=host))
    from app.services.portal_host_gate import invalidate_portal_domain_cache

    invalidate_portal_domain_cache()
    return host


def get_portal_domain(db: Session) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == "portal_domain").first()
    return (row.value or "").strip() if row else ""


def resolve_portal_base_url(db: Session) -> str | None:
    """Origin for permanent portal / QR / TG delivery links.

    Returns a URL only when the portal host is configured **and** publish status
    is ready (nginx vhost+cert). Unsupported modes (uvicorn / http_direct) never
    qualify. Until ready, callers should fall back to the panel public URL.

    Always the portal host root — never panel ACCESS_PATH.
    """
    host = get_portal_domain(db)
    if not host:
        return None

    from pathlib import Path

    from app.services.env_file import EnvFileService
    from app.services.panel_publish_info import (
        build_portal_publish_status,
        resolve_active_publish_mode_key,
        resolve_panel_publish_mode,
    )

    settings = get_settings()
    env = EnvFileService(Path(__file__).resolve().parents[2] / ".env")
    panel_domain = env.get_env_value("DOMAIN", "") or (settings.domain or "")
    ssl_cert = env.get_env_value("SSL_CERT", "")
    behind = (env.get_env_value("BEHIND_NGINX", "") or "").lower() in {"1", "true", "yes"}
    use_https = (env.get_env_value("USE_HTTPS", "") or "").lower() in {"1", "true", "yes"}
    backend_host = env.get_env_value("BACKEND_HOST", "127.0.0.1") or "127.0.0.1"
    backend_port = env.get_env_value("BACKEND_PORT", "8000") or "8000"
    https_port_raw = env.get_env_value("HTTPS_PUBLIC_PORT", "") or str(settings.https_public_port)
    try:
        https_public_port = int(https_port_raw)
    except ValueError:
        https_public_port = 443

    mode_key = resolve_panel_publish_mode(
        behind_nginx=behind,
        backend_host=backend_host,
        use_https=use_https,
    )
    active = resolve_active_publish_mode_key(
        mode_key=mode_key,
        ssl_cert=ssl_cert,
        publish_mode=env.get_env_value("PUBLISH_MODE", ""),
        domain=panel_domain,
    )
    status = build_portal_publish_status(
        portal_domain=host,
        panel_domain=panel_domain,
        publish_mode=active,
        ssl_cert=ssl_cert,
        backend_port=backend_port,
        https_public_port=https_public_port,
    )
    if not status.get("portal_ready"):
        return None
    access = (
        status.get("portal_access_url") or status.get("access_url") or ""
    ).strip().rstrip("/")
    return access or None


def portal_page_url(db: Session, token: str) -> str:
    base = resolve_portal_base_url(db)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Клиентский портал ещё не готов. Задайте поддомен и нажмите "
                "«Настроить под текущую публикацию» в разделе Подписка."
            ),
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


def _active_user_token(db: Session, *, user_id: int) -> UserPortalToken | None:
    return (
        db.query(UserPortalToken)
        .filter(
            UserPortalToken.user_id == user_id,
            UserPortalToken.revoked_at.is_(None),
        )
        .order_by(UserPortalToken.id.desc())
        .first()
    )


def _token_exists(db: Session, token: str) -> bool:
    return bool(
        db.query(ClientPortalToken.id).filter(ClientPortalToken.token == token).first()
        or db.query(UserPortalToken.id).filter(UserPortalToken.token == token).first()
    )


def _new_token_value(db: Session) -> str:
    for _ in range(16):
        candidate = secrets.token_urlsafe(18)
        if not _token_exists(db, candidate):
            return candidate
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Не удалось создать ссылку портала — повторите попытку",
    )


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


def ensure_portal_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return user


def _owned_portal_targets(db: Session, *, user_id: int) -> list[tuple[int, str]]:
    rows = (
        db.query(VpnConfig.node_id, VpnConfig.client_name)
        .filter(
            VpnConfig.owner_id == user_id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .order_by(VpnConfig.node_id.asc(), VpnConfig.client_name.asc())
        .all()
    )
    seen: set[tuple[int, str]] = set()
    targets: list[tuple[int, str]] = []
    for node_id, client_name in rows:
        target = (int(node_id), str(client_name))
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def get_or_create_portal_token(
    db: Session,
    *,
    client_name: str,
    creator: User | None = None,
) -> ClientPortalToken:
    from sqlalchemy.exc import IntegrityError

    configs = ensure_client_configs(db, client_name)
    node_id = configs[0].node_id
    name = configs[0].client_name
    existing = _active_token(db, node_id=node_id, client_name=name)
    if existing:
        return existing
    row = ClientPortalToken(
        token=_new_token_value(db),
        node_id=node_id,
        client_name=name,
        created_by_user_id=creator.id if creator else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = _active_token(db, node_id=node_id, client_name=name)
        if raced:
            return raced
        raise
    db.refresh(row)
    return row


def rotate_portal_token(
    db: Session,
    *,
    client_name: str,
    creator: User | None = None,
) -> ClientPortalToken:
    from sqlalchemy.exc import IntegrityError

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
        token=_new_token_value(db),
        node_id=node_id,
        client_name=name,
        created_by_user_id=creator.id if creator else None,
    )
    db.add(new_row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Не удалось сменить ссылку портала — повторите попытку",
        ) from None
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


def get_or_create_user_portal_token(
    db: Session,
    *,
    user_id: int,
    creator: User | None = None,
) -> UserPortalToken:
    from sqlalchemy.exc import IntegrityError

    ensure_portal_user(db, user_id)
    existing = _active_user_token(db, user_id=user_id)
    if existing:
        return existing
    row = UserPortalToken(
        token=_new_token_value(db),
        user_id=user_id,
        created_by_user_id=creator.id if creator else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = _active_user_token(db, user_id=user_id)
        if raced:
            return raced
        raise
    db.refresh(row)
    return row


def rotate_user_portal_token(
    db: Session,
    *,
    user_id: int,
    creator: User | None = None,
) -> UserPortalToken:
    from sqlalchemy.exc import IntegrityError

    ensure_portal_user(db, user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in (
        db.query(UserPortalToken)
        .filter(
            UserPortalToken.user_id == user_id,
            UserPortalToken.revoked_at.is_(None),
        )
        .all()
    ):
        row.revoked_at = now
    new_row = UserPortalToken(
        token=_new_token_value(db),
        user_id=user_id,
        created_by_user_id=creator.id if creator else None,
    )
    db.add(new_row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Не удалось сменить ссылку портала — повторите попытку",
        ) from None
    db.refresh(new_row)
    return new_row


def revoke_user_portal_token(db: Session, *, user_id: int) -> None:
    ensure_portal_user(db, user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (
        db.query(UserPortalToken)
        .filter(
            UserPortalToken.user_id == user_id,
            UserPortalToken.revoked_at.is_(None),
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка портала не найдена")
    for row in rows:
        row.revoked_at = now
    db.commit()


def get_valid_portal_token(db: Session, token: str) -> PortalTokenResolution:
    client_row = db.query(ClientPortalToken).filter(ClientPortalToken.token == token).first()
    user_row = db.query(UserPortalToken).filter(UserPortalToken.token == token).first()
    candidates = []
    if client_row is not None:
        candidates.append(("client", client_row))
    if user_row is not None:
        candidates.append(("user", user_row))
    if not candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка недействительна")

    active = [(kind, row) for kind, row in candidates if row.revoked_at is None]
    if len(active) > 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ссылка недействительна")
    if active:
        kind, row = active[0]
    else:
        kind, row = candidates[0]
        if row.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ссылка отозвана")

    if kind == "client":
        return PortalTokenResolution(kind="client", client_row=row)
    return PortalTokenResolution(kind="user", user_row=row)


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


def _adapter_for_node_id(db: Session, node_id: int):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    return get_adapter_for_node(node)


def _list_files_for_configs(db: Session, configs: list[VpnConfig]) -> list[dict]:
    if not configs:
        return []
    adapter = _adapter_for_node_id(db, configs[0].node_id)
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
        # WG policy rows are stored lowercased across the stack.
        wg_name = client_name.lower()
        policies.append(
            db.query(WgAccessPolicy)
            .filter(WgAccessPolicy.node_id == node_id, WgAccessPolicy.client_name == wg_name)
            .first()
        )
    if "amneziawg2" in protocols:
        awg2_name = client_name.lower()
        policies.append(
            db.query(AmneziaWg2AccessPolicy)
            .filter(
                AmneziaWg2AccessPolicy.node_id == node_id,
                AmneziaWg2AccessPolicy.client_name == awg2_name,
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


def _portal_brand_title(db: Session) -> str:
    brand = _setting_value(db, "app_name") or "VPN"
    if brand.lower().startswith("adminpanel"):
        brand = "VPN"
    return brand


def _portal_download_url(
    *,
    base: str,
    token: str,
    path: str,
    node_id: int | None = None,
    client_name: str | None = None,
) -> str:
    params: dict[str, str | int] = {"path": path}
    if node_id is not None:
        params["node_id"] = node_id
    if client_name:
        params["client_name"] = client_name
    return f"{base}/api/public/portal/{token}/download?{urlencode(params, quote_via=quote)}"


def _portal_file_entries(
    *,
    base: str,
    token: str,
    files_meta: list[dict],
    node_id: int | None = None,
    client_name: str | None = None,
) -> list[dict]:
    files = []
    for item in files_meta:
        download_url = _portal_download_url(
            base=base,
            token=token,
            path=item["path"],
            node_id=node_id,
            client_name=client_name,
        )
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
    return files


def _parse_portal_status_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _apply_user_subscription_status(status_payload: dict, user: User) -> dict:
    deadline = getattr(user, "access_until", None)
    if deadline is None:
        return status_payload
    updated = dict(status_payload)
    current_expires_at = _parse_portal_status_datetime(updated.get("expires_at"))
    if current_expires_at is None or deadline < current_expires_at:
        updated["expires_at"] = deadline.isoformat() + "Z"
        updated["expires_label"] = _format_expires_label(deadline)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if deadline <= now and updated.get("status") != "blocked":
        updated["status"] = "expired"
        updated["status_label"] = "Истекла"
    return updated


def _build_client_portal_entry(
    db: Session,
    *,
    token: str,
    node_id: int,
    client_name: str,
    base: str,
    download_node_id: int | None = None,
    download_client_name: str | None = None,
) -> dict:
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == client_name,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    files_meta = _list_files_for_configs(db, configs)
    files = _portal_file_entries(
        base=base,
        token=token,
        files_meta=files_meta,
        node_id=download_node_id,
        client_name=download_client_name,
    )
    return {
        "node_id": node_id,
        "client_name": client_name,
        "protocols": sorted({f["vpn_type"] for f in files}),
        "files": files,
        "status": build_portal_status(
            db,
            node_id=node_id,
            client_name=client_name,
            configs=configs,
        ),
    }


def build_portal_payload(db: Session, token_row: ClientPortalToken) -> dict:
    base = resolve_portal_base_url(db)
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    from app.services.feature_guards import get_feature_service

    entry = _build_client_portal_entry(
        db,
        token=token_row.token,
        node_id=token_row.node_id,
        client_name=token_row.client_name,
        base=base,
    )
    return {
        "kind": "client",
        "node_id": token_row.node_id,
        "client_name": token_row.client_name,
        "brand_title": _portal_brand_title(db),
        "protocols": entry["protocols"],
        "files": entry["files"],
        "unlock_codes_enabled": get_feature_service().is_enabled("unlock_codes"),
        "status": entry["status"],
    }


def build_user_portal_payload(db: Session, token_row: UserPortalToken) -> dict:
    base = resolve_portal_base_url(db)
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    user = ensure_portal_user(db, token_row.user_id)
    from app.services.feature_guards import get_feature_service

    clients = []
    for node_id, client_name in _owned_portal_targets(db, user_id=user.id):
        entry = _build_client_portal_entry(
            db,
            token=token_row.token,
            node_id=node_id,
            client_name=client_name,
            base=base,
            download_node_id=node_id,
            download_client_name=client_name,
        )
        entry["status"] = _apply_user_subscription_status(entry["status"], user)
        clients.append(entry)
    return {
        "kind": "user",
        "user_id": user.id,
        "brand_title": _portal_brand_title(db),
        "unlock_codes_enabled": get_feature_service().is_enabled("unlock_codes"),
        "clients": clients,
    }


def build_public_portal_payload(db: Session, resolution: PortalTokenResolution) -> dict:
    if resolution.kind == "client":
        if resolution.client_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return build_portal_payload(db, resolution.client_row)
    if resolution.user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return build_user_portal_payload(db, resolution.user_row)


def _read_client_portal_profile(
    db: Session,
    *,
    node_id: int,
    client_name: str,
    path: str,
) -> tuple[str, str | bytes]:
    path = (path or "").strip()
    if not path or ".." in path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный путь")
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == client_name,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    allowed = {item["path"] for item in _list_files_for_configs(db, configs)}
    if path not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    adapter = _adapter_for_node_id(db, node_id)
    hosts = load_node_remote_hosts(db, node_id)
    content = read_profile_file_for_delivery(adapter, path, hosts)
    filename = build_profile_download_filename(client_name, path=path)
    return filename, content


def read_portal_profile(
    db: Session,
    resolution: PortalTokenResolution,
    path: str,
    *,
    node_id: int | None = None,
    client_name: str | None = None,
) -> tuple[str, str | bytes]:
    if resolution.kind == "client":
        if resolution.client_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return _read_client_portal_profile(
            db,
            node_id=resolution.client_row.node_id,
            client_name=resolution.client_row.client_name,
            path=path,
        )

    if resolution.user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    key = (client_name or "").strip().lower()
    if node_id is None or not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не указан клиент")
    for target_node_id, target_client_name in _owned_portal_targets(db, user_id=resolution.user_row.user_id):
        if target_node_id != node_id:
            continue
        if target_client_name.strip().lower() != key:
            continue
        return _read_client_portal_profile(
            db,
            node_id=target_node_id,
            client_name=target_client_name,
            path=path,
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Клиент не найден")


def redeem_public_portal_code(db: Session, resolution: PortalTokenResolution, *, code: str) -> dict:
    from app.services import unlock_codes as unlock_codes_service
    from app.services.access_until import effective_access_until_for_client

    if resolution.kind == "client":
        if resolution.client_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        result = unlock_codes_service.redeem_unlock_code(
            db,
            code=code,
            client_name=resolution.client_row.client_name,
            node_id=resolution.client_row.node_id,
        )
        access_until = effective_access_until_for_client(
            db,
            resolution.client_row.node_id,
            resolution.client_row.client_name,
        )
        return {
            **result,
            "access_until": access_until.isoformat() if access_until else None,
        }

    if resolution.user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    retryable_messages = {
        unlock_codes_service._REDEEM_CLIENT_NOT_ALLOWED_MESSAGE,
        unlock_codes_service._REDEEM_PROTOCOL_MISMATCH_MESSAGE,
    }
    last_retryable_error: str | None = None
    for node_id, client_name in _owned_portal_targets(db, user_id=resolution.user_row.user_id):
        try:
            result = unlock_codes_service.redeem_unlock_code(
                db,
                code=code,
                client_name=client_name,
                node_id=node_id,
            )
        except ValueError as exc:
            if str(exc) in retryable_messages:
                last_retryable_error = str(exc)
                continue
            raise
        user = ensure_portal_user(db, resolution.user_row.user_id)
        access_until = getattr(user, "access_until", None)
        return {
            **result,
            "access_until": access_until.isoformat() if access_until else None,
        }

    raise ValueError(last_retryable_error or "Профили пользователя не найдены")


def link_response(db: Session, row: ClientPortalToken) -> dict:
    return {
        "kind": "client",
        "token": row.token,
        "node_id": row.node_id,
        "client_name": row.client_name,
        "url": portal_page_url(db, row.token),
        "revoked": row.revoked_at is not None,
    }


def user_link_response(db: Session, row: UserPortalToken) -> dict:
    return {
        "kind": "user",
        "token": row.token,
        "user_id": row.user_id,
        "url": portal_page_url(db, row.token),
        "revoked": row.revoked_at is not None,
    }
