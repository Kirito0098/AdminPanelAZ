"""Helpers for protocol access-until policy management."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AmneziaWg2AccessPolicy, Node, OpenVpnAccessPolicy, WgAccessPolicy
from app.services.access_policy import AccessPolicyService
from app.services.node_manager import get_adapter_for_node, node_metadata_dict

Protocol = Literal["openvpn", "wireguard", "amneziawg2"]


def _deadline_column(protocol: Protocol):
    model = _policy_model(protocol)
    return model.expires_at if protocol == "wireguard" else model.access_until


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


def _normalized_client_name(protocol: Protocol, client_name: str) -> str:
    name = client_name.strip()
    if protocol in {"wireguard", "amneziawg2"}:
        return name.lower()
    return name


def _policy_model(protocol: Protocol):
    if protocol == "openvpn":
        return OpenVpnAccessPolicy
    if protocol == "wireguard":
        return WgAccessPolicy
    if protocol == "amneziawg2":
        return AmneziaWg2AccessPolicy
    raise ValueError(f"Unsupported protocol: {protocol}")


def _row_access_until(protocol: Protocol, row) -> datetime | None:
    if row is None:
        return None
    if protocol == "wireguard":
        return _as_utc(row.expires_at)
    return _as_utc(row.access_until)


def _set_row_access_until(protocol: Protocol, row, access_until: datetime | None) -> None:
    value = _to_db_datetime(access_until)
    if protocol == "wireguard":
        row.expires_at = value
        return
    row.access_until = value


def _policy_service_for_node(db: Session, node: Node) -> AccessPolicyService:
    settings = get_settings()
    meta = node_metadata_dict(node)
    antizapret_path = Path(str(meta.get("antizapret_path") or settings.antizapret_path))
    return AccessPolicyService(
        db,
        antizapret_path=antizapret_path,
        node_id=node.id,
        node_name=node.name,
        adapter=get_adapter_for_node(node),
    )


def _get_row(db: Session, protocol: Protocol, node_id: int, client_name: str):
    model = _policy_model(protocol)
    normalized = _normalized_client_name(protocol, client_name)
    return (
        db.query(model)
        .filter_by(node_id=node_id, client_name=normalized if protocol != "openvpn" else normalized)
        .first()
    )


def get_access_until(db: Session, protocol: Protocol, node_id: int, client_name: str) -> datetime | None:
    row = _get_row(db, protocol, node_id, client_name)
    return _row_access_until(protocol, row)


def effective_access_until_for_client(db: Session, node_id: int, client_name: str) -> datetime | None:
    values = [
        get_access_until(db, "openvpn", node_id, client_name),
        get_access_until(db, "wireguard", node_id, client_name),
        get_access_until(db, "amneziawg2", node_id, client_name),
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return min(values)


def _reconcile_access_until(service: AccessPolicyService, protocol: Protocol, client_name: str) -> None:
    if protocol == "openvpn":
        service.reconcile_openvpn(client_name)
    elif protocol == "wireguard":
        service.reconcile_wg(client_name, force_runtime=True)
    elif protocol == "amneziawg2":
        service.reconcile_awg2(client_name, force_runtime=True)
    else:  # pragma: no cover - guarded by typing and protocol validation
        raise ValueError(f"Unsupported protocol: {protocol}")


def _policy_state(service: AccessPolicyService, protocol: Protocol, client_name: str) -> dict:
    if protocol == "openvpn":
        return service.get_openvpn_policy(client_name)
    if protocol == "wireguard":
        return service.get_wg_policy(client_name)
    if protocol == "amneziawg2":
        return service.get_awg2_policy(client_name)
    raise ValueError(f"Unsupported protocol: {protocol}")


def set_access_until(
    db: Session,
    protocol: Protocol,
    node_id: int,
    client_name: str,
    access_until: datetime | None,
    *,
    actor: str,
    commit: bool = True,
    require_deadline_lte: datetime | None = None,
) -> dict | None:
    """Set access deadline.

    When ``require_deadline_lte`` is set (access-expiry worker), the write is an
    atomic claim: UPDATE … WHERE deadline is still due. Concurrent redeem/PATCH
    that extends the deadline makes the claim miss, so the worker cannot clobber
    the extension (important under SQLite snapshot isolation).
    """
    normalized = _normalized_client_name(protocol, client_name)
    node = db.get(Node, node_id)
    if node is None:
        raise ValueError("Узел не найден")

    model = _policy_model(protocol)

    if require_deadline_lte is not None:
        deadline_col = _deadline_column(protocol)
        cutoff = _to_db_datetime(require_deadline_lte)
        claimed = (
            db.query(model)
            .filter(
                model.node_id == node_id,
                model.client_name == normalized,
                deadline_col.isnot(None),
                deadline_col <= cutoff,
                or_(model.block_reason.is_(None), model.block_reason != "access_expired"),
            )
            .update({model.updated_by: actor}, synchronize_session="fetch")
        )
        if claimed != 1:
            return None
        if commit:
            db.commit()
        else:
            db.flush()
        service = _policy_service_for_node(db, node)
        if commit:
            _reconcile_access_until(service, protocol, normalized)
        return _policy_state(service, protocol, normalized)

    row = _get_row(db, protocol, node_id, normalized)
    if row is None:
        row = model(node_id=node_id, client_name=normalized)
        db.add(row)
        db.flush()

    _set_row_access_until(protocol, row, access_until)
    row.updated_by = actor
    if commit:
        db.commit()
    else:
        db.flush()

    service = _policy_service_for_node(db, node)
    if commit:
        _reconcile_access_until(service, protocol, normalized)
    return _policy_state(service, protocol, normalized)


def apply_due_access_blocks(db: Session) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    counts = {
        "openvpn": 0,
        "wireguard": 0,
        "amneziawg2": 0,
        "blocked": 0,
        "skipped": 0,
        "errors": 0,
    }

    due_targets: list[tuple[Protocol, int, str]] = []
    for row in db.query(OpenVpnAccessPolicy).filter(OpenVpnAccessPolicy.access_until.isnot(None)).all():
        access_until = _row_access_until("openvpn", row)
        if access_until is not None and access_until <= now and row.block_reason != "access_expired":
            due_targets.append(("openvpn", row.node_id, row.client_name))
    for row in db.query(WgAccessPolicy).filter(WgAccessPolicy.expires_at.isnot(None)).all():
        access_until = _row_access_until("wireguard", row)
        if access_until is not None and access_until <= now and row.block_reason != "access_expired":
            due_targets.append(("wireguard", row.node_id, row.client_name))
    for row in db.query(AmneziaWg2AccessPolicy).filter(AmneziaWg2AccessPolicy.access_until.isnot(None)).all():
        access_until = _row_access_until("amneziawg2", row)
        if access_until is not None and access_until <= now and row.block_reason != "access_expired":
            due_targets.append(("amneziawg2", row.node_id, row.client_name))

    # End the read snapshot so claim UPDATEs observe concurrent redeem/PATCH commits.
    db.commit()

    for protocol, node_id, client_name in due_targets:
        try:
            result = set_access_until(
                db,
                protocol,
                node_id,
                client_name,
                None,
                actor="access_expiry_worker",
                require_deadline_lte=now,
            )
            if result is None:
                counts["skipped"] += 1
                continue
        except Exception:
            counts["errors"] += 1
            continue
        counts[protocol] += 1
        counts["blocked"] += 1

    counts["rows_due"] = len(due_targets)
    return counts
