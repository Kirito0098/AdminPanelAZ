"""Shared helpers for user-level VPN blocks: apply_user_block / lift_user_block.

Blocks every owned primary config with a sticky reason (user_suspended /
user_traffic_limit) and HA-replicates the op. Offline nodes are counted as
skipped, not failed.

Stacked-reasons contract (one block_reason per policy row):
- lifting user_suspended clears the User suspend fields; if
  traffic_limit_blocked is still true, immediately applies user_traffic_limit.
- lifting user_traffic_limit clears only that flag/reason; user_suspended stays.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, NodeStatus, User, VpnConfig, VpnType
from app.services.access_policy import USER_LEVEL_BLOCK_REASONS, AccessPolicyService
from app.services.node_manager import get_adapter_for_node, is_vpn_node, node_metadata_dict
from app.services.node_sync.policy_sync import maybe_replicate_policy_op

logger = logging.getLogger(__name__)

_VPN_PROTOCOLS = {
    VpnType.openvpn: "openvpn",
    VpnType.wireguard: "wireguard",
    VpnType.amneziawg2: "amneziawg2",
}


def _policy_service(db: Session, node: Node) -> AccessPolicyService:
    meta = node_metadata_dict(node)
    path = Path(str(meta.get("antizapret_path") or get_settings().antizapret_path))
    return AccessPolicyService(
        db,
        antizapret_path=path,
        node_id=node.id,
        node_name=node.name,
        adapter=get_adapter_for_node(node),
    )


def _owned_primary_configs(db: Session, user_id: int) -> list[VpnConfig]:
    return (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user_id, VpnConfig.ha_primary_config_id.is_(None))
        .order_by(VpnConfig.node_id, VpnConfig.client_name, VpnConfig.vpn_type)
        .all()
    )


def _replicate(
    db: Session,
    *,
    node_id: int,
    client_name: str,
    vpn_type: VpnType,
    op: str,
    reason: str,
    actor: str,
) -> None:
    maybe_replicate_policy_op(
        db,
        node_id=node_id,
        client_name=client_name,
        vpn_type=vpn_type,
        op=op,  # type: ignore[arg-type]
        reason=reason,
        actor=actor,
    )


def apply_user_block(db: Session, user: User, reason: str, *, actor: str) -> dict:
    """Block every owned primary config with sticky reason; HA replicate.

    Offline nodes are counted as skipped. Returns
    {"blocked": int, "skipped_offline": int, "errors": list}.
    """
    if reason not in USER_LEVEL_BLOCK_REASONS:
        raise ValueError(f"unsupported reason: {reason}")
    blocked = skipped_offline = 0
    errors: list[dict] = []
    for config in _owned_primary_configs(db, user.id):
        node = db.get(Node, config.node_id)
        if node is None or not is_vpn_node(node):
            continue
        if node.status != NodeStatus.online:
            skipped_offline += 1
            continue
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        try:
            svc = _policy_service(db, node)
            svc.set_reason_block(protocol, config.client_name, reason, actor=actor)
            _replicate(
                db,
                node_id=node.id,
                client_name=config.client_name,
                vpn_type=config.vpn_type,
                op="set_block_reason",
                reason=reason,
                actor=actor,
            )
            blocked += 1
        except Exception as exc:  # one config must not abort the whole user
            logger.warning("apply_user_block failed user=%s config=%s: %s", user.id, config.id, exc)
            errors.append({"config_id": config.id, "error": str(exc)})
    return {"blocked": blocked, "skipped_offline": skipped_offline, "errors": errors}


def lift_user_block(db: Session, user: User, reason: str, *, actor: str) -> dict:
    """Lift only the matching reason on every owned primary config; HA replicate.

    Returns {"lifted": int, "skipped_offline": int, "errors": list}.
    """
    if reason not in USER_LEVEL_BLOCK_REASONS:
        raise ValueError(f"unsupported reason: {reason}")
    lifted = skipped_offline = 0
    errors: list[dict] = []
    for config in _owned_primary_configs(db, user.id):
        node = db.get(Node, config.node_id)
        if node is None or not is_vpn_node(node):
            continue
        if node.status != NodeStatus.online:
            skipped_offline += 1
            continue
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is None:
            continue
        try:
            svc = _policy_service(db, node)
            svc.lift_reason_block(protocol, config.client_name, reason, actor=actor)
            _replicate(
                db,
                node_id=node.id,
                client_name=config.client_name,
                vpn_type=config.vpn_type,
                op="lift_block_reason",
                reason=reason,
                actor=actor,
            )
            lifted += 1
        except Exception as exc:
            logger.warning("lift_user_block failed user=%s config=%s: %s", user.id, config.id, exc)
            errors.append({"config_id": config.id, "error": str(exc)})

    # Stacked-reasons contract: lift of suspend re-applies traffic block when still needed.
    if reason == "user_suspended":
        user.suspended_at = None
        user.suspend_reason = None
        user.suspend_reason_visible = False
        db.add(user)
        if user.traffic_limit_blocked:
            for config in _owned_primary_configs(db, user.id):
                node = db.get(Node, config.node_id)
                if node is None or not is_vpn_node(node) or node.status != NodeStatus.online:
                    continue
                protocol = _VPN_PROTOCOLS.get(config.vpn_type)
                if protocol is None:
                    continue
                try:
                    svc = _policy_service(db, node)
                    svc.set_reason_block(protocol, config.client_name, "user_traffic_limit", actor=actor)
                    _replicate(
                        db,
                        node_id=node.id,
                        client_name=config.client_name,
                        vpn_type=config.vpn_type,
                        op="set_block_reason",
                        reason="user_traffic_limit",
                        actor=actor,
                    )
                    lifted += 1
                except Exception as exc:
                    logger.warning(
                        "lift_user_block re-apply traffic failed user=%s config=%s: %s",
                        user.id,
                        config.id,
                        exc,
                    )
                    errors.append({"config_id": config.id, "error": str(exc)})
    elif reason == "user_traffic_limit":
        user.traffic_limit_blocked = False
        db.add(user)

    db.commit()
    return {"lifted": lifted, "skipped_offline": skipped_offline, "errors": errors}
