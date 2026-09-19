from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AmneziaWg2AccessPolicy, Node, OpenVpnAccessPolicy, User, VpnConfig, VpnType, WgAccessPolicy
from app.services.access_until import _policy_service_for_node, _reconcile_access_until, set_access_until
from app.services.unlock_codes import _is_manual_admin_block

_VPN_PROTOCOLS = {
    VpnType.openvpn: "openvpn",
    VpnType.wireguard: "wireguard",
    VpnType.amneziawg2: "amneziawg2",
}


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_db_datetime(dt: datetime | None) -> datetime | None:
    value = _as_utc(dt)
    if value is None:
        return None
    return value.replace(tzinfo=None)


def get_user_access_until(user: User) -> datetime | None:
    return _as_utc(getattr(user, "access_until", None))


def user_subscription_expired(user: User, *, now: datetime | None = None) -> bool:
    deadline = get_user_access_until(user)
    if deadline is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return deadline <= current


def _policy_model(protocol: str):
    if protocol == "openvpn":
        return OpenVpnAccessPolicy
    if protocol == "wireguard":
        return WgAccessPolicy
    if protocol == "amneziawg2":
        return AmneziaWg2AccessPolicy
    raise ValueError(f"Unsupported protocol: {protocol}")


def _policy_client_name(protocol: str, client_name: str) -> str:
    normalized = (client_name or "").strip()
    if protocol == "openvpn":
        return normalized
    return normalized.lower()


def _owned_configs(db: Session, user_id: int) -> list[VpnConfig]:
    return (
        db.query(VpnConfig)
        .filter(
            VpnConfig.owner_id == user_id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .order_by(VpnConfig.node_id.asc(), VpnConfig.client_name.asc(), VpnConfig.vpn_type.asc())
        .all()
    )


def _policy_row(db: Session, *, protocol: str, node_id: int, client_name: str):
    model = _policy_model(protocol)
    return (
        db.query(model)
        .filter_by(node_id=node_id, client_name=_policy_client_name(protocol, client_name))
        .first()
    )


def list_owned_client_targets(db: Session, user_id: int) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for config in _owned_configs(db, user_id):
        target = (config.node_id, config.client_name)
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def sync_owned_clients_access_until(db: Session, user: User, *, actor: str, commit: bool = True) -> dict:
    access_until = get_user_access_until(user)
    services: dict[int, object] = {}
    queued: list[tuple[int, str, str]] = []
    synced = 0

    for config in _owned_configs(db, user.id):
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        client_name = _policy_client_name(protocol, config.client_name)
        set_access_until(
            db,
            protocol,
            config.node_id,
            client_name,
            access_until,
            actor=actor,
            commit=False,
        )
        queued.append((config.node_id, protocol, client_name))

    if commit:
        db.commit()
    else:
        db.flush()

    for node_id, protocol, client_name in queued:
        service = services.get(node_id)
        if service is None:
            node = db.get(Node, node_id)
            if node is None:
                continue
            service = _policy_service_for_node(db, node)
            services[node_id] = service
        _reconcile_access_until(service, protocol, client_name)
        synced += 1

    return {
        "targets": len(list_owned_client_targets(db, user.id)),
        "synced": synced,
    }


def apply_user_subscription_expiry(
    db: Session,
    user: User,
    *,
    actor: str = "access_expiry_worker",
    commit: bool = True,
) -> dict:
    if not user_subscription_expired(user):
        return {
            "targets": len(list_owned_client_targets(db, user.id)),
            "expired": 0,
            "skipped_manual": 0,
            "skipped_not_expired": 1,
        }

    access_until = get_user_access_until(user)
    services: dict[int, object] = {}
    queued: list[tuple[int, str, str]] = []
    skipped_manual = 0

    for config in _owned_configs(db, user.id):
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        row = _policy_row(db, protocol=protocol, node_id=config.node_id, client_name=config.client_name)
        if _is_manual_admin_block(row):
            skipped_manual += 1
            continue
        client_name = _policy_client_name(protocol, config.client_name)
        set_access_until(
            db,
            protocol,
            config.node_id,
            client_name,
            access_until,
            actor=actor,
            commit=False,
        )
        queued.append((config.node_id, protocol, client_name))

    if commit:
        db.commit()
    else:
        db.flush()

    expired = 0
    for node_id, protocol, client_name in queued:
        service = services.get(node_id)
        if service is None:
            node = db.get(Node, node_id)
            if node is None:
                continue
            service = _policy_service_for_node(db, node)
            services[node_id] = service
        _reconcile_access_until(service, protocol, client_name)
        row = _policy_row(db, protocol=protocol, node_id=node_id, client_name=client_name)
        if (getattr(row, "block_reason", None) or "").strip().lower() == "access_expired":
            expired += 1

    return {
        "targets": len(list_owned_client_targets(db, user.id)),
        "expired": expired,
        "skipped_manual": skipped_manual,
        "skipped_not_expired": 0,
    }


def clear_access_expired_for_user(db: Session, user: User, *, actor: str, commit: bool = True) -> dict:
    access_until = get_user_access_until(user)
    services: dict[int, object] = {}
    queued: list[tuple[int, str, str]] = []
    skipped_manual = 0

    for config in _owned_configs(db, user.id):
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        row = _policy_row(db, protocol=protocol, node_id=config.node_id, client_name=config.client_name)
        if row is None:
            continue
        if _is_manual_admin_block(row):
            skipped_manual += 1
            continue
        reason = (getattr(row, "block_reason", None) or "").strip().lower()
        if reason != "access_expired":
            continue
        client_name = _policy_client_name(protocol, config.client_name)
        set_access_until(
            db,
            protocol,
            config.node_id,
            client_name,
            access_until,
            actor=actor,
            commit=False,
        )
        queued.append((config.node_id, protocol, client_name))

    if commit:
        db.commit()
    else:
        db.flush()

    cleared = 0
    for node_id, protocol, client_name in queued:
        service = services.get(node_id)
        if service is None:
            node = db.get(Node, node_id)
            if node is None:
                continue
            service = _policy_service_for_node(db, node)
            services[node_id] = service
        _reconcile_access_until(service, protocol, client_name)
        row = _policy_row(db, protocol=protocol, node_id=node_id, client_name=client_name)
        if (getattr(row, "block_reason", None) or "").strip().lower() != "access_expired":
            cleared += 1

    return {
        "targets": len(list_owned_client_targets(db, user.id)),
        "cleared": cleared,
        "skipped_manual": skipped_manual,
    }


def set_user_access_until(
    db: Session,
    user: User,
    access_until: datetime | None,
    *,
    actor: str,
    sync_clients: bool = True,
) -> User:
    user.access_until = _to_db_datetime(access_until)
    db.add(user)
    db.commit()
    db.refresh(user)
    if sync_clients:
        sync_owned_clients_access_until(db, user, actor=actor, commit=True)
    return user
