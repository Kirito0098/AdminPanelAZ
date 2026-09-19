from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AmneziaWg2AccessPolicy, Node, OpenVpnAccessPolicy, User, VpnConfig, VpnType, WgAccessPolicy
from app.services.access_until import _policy_service_for_node, _reconcile_access_until, _row_access_until, set_access_until
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


def client_access_conflicts_with_owner(
    db: Session,
    *,
    owner: User | None,
    client_access_until: datetime | None,
) -> bool:
    _ = db
    if owner is None:
        return False
    user_until = get_user_access_until(owner)
    if user_until is None and client_access_until is None:
        return False
    return _as_utc(client_access_until) != user_until


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


def _reconcile_owned_client_queue(db: Session, queued: list[tuple[int, str, str]]) -> int:
    services: dict[int, object] = {}
    synced = 0

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

    return synced


def _owned_client_protocol_targets(
    db: Session,
    *,
    user_id: int,
    node_id: int,
    client_name: str,
) -> list[tuple[int, str, str]]:
    targets: list[tuple[int, str, str]] = []
    seen: set[tuple[int, str, str]] = set()
    client_key = (client_name or "").strip().lower()

    for config in _owned_configs(db, user_id):
        if config.node_id != node_id:
            continue
        if (config.client_name or "").strip().lower() != client_key:
            continue
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        target = (config.node_id, protocol, _policy_client_name(protocol, config.client_name))
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)

    return targets


def reconcile_owned_clients_access_until(db: Session, user: User) -> dict:
    queued: list[tuple[int, str, str]] = []

    for config in _owned_configs(db, user.id):
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        queued.append((config.node_id, protocol, _policy_client_name(protocol, config.client_name)))

    return {
        "targets": len(list_owned_client_targets(db, user.id)),
        "synced": _reconcile_owned_client_queue(db, queued),
    }


def sync_owned_clients_access_until(db: Session, user: User, *, actor: str, commit: bool = True) -> dict:
    access_until = get_user_access_until(user)
    queued: list[tuple[int, str, str]] = []

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

    return {
        "targets": len(list_owned_client_targets(db, user.id)),
        "synced": _reconcile_owned_client_queue(db, queued) if commit else 0,
    }


def sync_client_access_until_from_owner(
    db: Session,
    *,
    owner: User,
    node_id: int,
    client_name: str,
    actor: str,
    commit: bool = True,
) -> dict:
    access_until = get_user_access_until(owner)
    queued = _owned_client_protocol_targets(
        db,
        user_id=owner.id,
        node_id=node_id,
        client_name=client_name,
    )

    for target_node_id, protocol, normalized_client_name in queued:
        set_access_until(
            db,
            protocol,
            target_node_id,
            normalized_client_name,
            access_until,
            actor=actor,
            commit=False,
        )

    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "client_name": client_name,
        "targets": len(queued),
        "protocols": [protocol for (_node_id, protocol, _client_name) in queued],
        "synced": _reconcile_owned_client_queue(db, queued) if commit else 0,
        "access_until": access_until.isoformat() if access_until else None,
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
    queued: list[tuple[int, str, str]] = []
    seed_missing_rows: list[tuple[int, str, str]] = []
    skipped_manual = 0
    skipped_not_expired = 0

    for config in _owned_configs(db, user.id):
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        row = _policy_row(db, protocol=protocol, node_id=config.node_id, client_name=config.client_name)
        if _is_manual_admin_block(row):
            skipped_manual += 1
            continue
        client_name = _policy_client_name(protocol, config.client_name)
        queued.append((config.node_id, protocol, client_name))
        if row is None or _row_access_until(protocol, row) is None:
            seed_missing_rows.append((config.node_id, protocol, client_name))

    for node_id, protocol, client_name in seed_missing_rows:
        set_access_until(
            db,
            protocol,
            node_id,
            client_name,
            access_until,
            actor=actor,
            commit=False,
        )

    # End the read snapshot before atomic claims so concurrent redeem/PATCH can win.
    if commit:
        db.commit()
    else:
        db.flush()

    expired = 0
    for node_id, protocol, client_name in queued:
        result = set_access_until(
            db,
            protocol,
            node_id,
            client_name,
            None,
            actor=actor,
            require_deadline_lte=access_until,
            commit=commit,
        )
        if result is None:
            skipped_not_expired += 1
            continue
        if (result.get("block_mode") or "").strip().lower() == "access_expired":
            expired += 1

    return {
        "targets": len(list_owned_client_targets(db, user.id)),
        "expired": expired,
        "skipped_manual": skipped_manual,
        "skipped_not_expired": skipped_not_expired,
    }


def apply_due_user_subscription_blocks(db: Session) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    counts = {
        "users_due": 0,
        "cascaded": 0,
        "skipped": 0,
        "errors": 0,
    }

    due_user_ids = [
        user_id
        for (user_id,) in db.query(User.id)
        .filter(
            User.access_until.isnot(None),
            User.access_until <= now.replace(tzinfo=None),
        )
        .all()
    ]

    # End the read snapshot so each user refresh sees concurrent extensions.
    db.commit()
    db.expire_all()

    for user_id in due_user_ids:
        counts["users_due"] += 1
        try:
            user = db.get(User, user_id)
            if user is None or not user_subscription_expired(user, now=now):
                counts["skipped"] += 1
                continue
            result = apply_user_subscription_expiry(db, user, commit=True)
        except Exception:
            db.rollback()
            counts["errors"] += 1
            continue
        counts["cascaded"] += int(result.get("expired", 0) or 0)
        counts["skipped"] += int(result.get("skipped_manual", 0) or 0)
        counts["skipped"] += int(result.get("skipped_not_expired", 0) or 0)

    return counts


def clear_access_expired_for_user(db: Session, user: User, *, actor: str, commit: bool = True) -> dict:
    access_until = get_user_access_until(user)
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
    if commit:
        _reconcile_owned_client_queue(db, queued)
        for node_id, protocol, client_name in queued:
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
    commit: bool = True,
) -> User:
    user.access_until = _to_db_datetime(access_until)
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    if sync_clients:
        sync_owned_clients_access_until(db, user, actor=actor, commit=commit)
    return user
