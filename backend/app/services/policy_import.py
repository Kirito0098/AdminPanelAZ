"""Copy access policy rows between nodes (e.g. primary → replica after Push full)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Node, OpenVpnAccessPolicy, WgAccessPolicy

_OVPN_POLICY_FIELDS = (
    "is_temp_blocked",
    "is_permanent_blocked",
    "block_reason",
    "block_started_at",
    "block_days",
    "block_until",
    "traffic_limit_bytes",
    "traffic_limit_period_days",
    "updated_by",
)

_WG_POLICY_FIELDS = _OVPN_POLICY_FIELDS + ("expires_at",)


def _copy_policy_row(source, target, fields: tuple[str, ...]) -> None:
    for field in fields:
        setattr(target, field, getattr(source, field))


def _copy_policies_for_model(
    db: Session,
    model: type[OpenVpnAccessPolicy] | type[WgAccessPolicy],
    *,
    source_node_id: int,
    target_node_id: int,
    fields: tuple[str, ...],
) -> int:
    copied = 0
    for source in db.query(model).filter(model.node_id == source_node_id).all():
        target = (
            db.query(model)
            .filter(
                model.node_id == target_node_id,
                model.client_name == source.client_name,
            )
            .first()
        )
        if target is None:
            target = model(node_id=target_node_id, client_name=source.client_name)
            db.add(target)
            copied += 1
        _copy_policy_row(source, target, fields)
    return copied


def copy_access_policies_from_node(db: Session, source_node: Node, target_node: Node) -> int:
    """Copy OpenVPN/WG access policies from source node to target node (upsert by client_name)."""
    source_id = source_node.id
    target_id = target_node.id
    copied = _copy_policies_for_model(
        db,
        OpenVpnAccessPolicy,
        source_node_id=source_id,
        target_node_id=target_id,
        fields=_OVPN_POLICY_FIELDS,
    )
    copied += _copy_policies_for_model(
        db,
        WgAccessPolicy,
        source_node_id=source_id,
        target_node_id=target_id,
        fields=_WG_POLICY_FIELDS,
    )
    db.commit()
    return copied
