"""HA auto-sync for client access policies (primary → replicas)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, NodeSyncGroup, OpenVpnAccessPolicy, VpnConfig, VpnType, WgAccessPolicy
from app.services.access_policy import NODE_DEFAULT_POLICY_CLIENT, AccessPolicyService, is_node_default_policy_client
from app.services.node_manager import get_adapter_for_node, node_metadata_dict
from app.services.node_sync.groups import find_sync_group_for_primary, get_replica_nodes, is_auto_sync_enabled
from app.services.node_sync.replicate import ReplicateOperation, ReplicateResult, finalize_replicate_outcome, get_shadow_configs
from app.services.policy_import import copy_access_policies_from_node, copy_single_client_policy

logger = logging.getLogger(__name__)

PolicyOp = Literal[
    "block_temp",
    "block_permanent",
    "unblock",
    "set_traffic_limit",
    "clear_traffic_limit",
    "set_wg_expiry",
]

_LIMIT_OPS = frozenset({"set_traffic_limit", "clear_traffic_limit"})


def _antizapret_path_for_node(node: Node) -> Path:
    meta = node_metadata_dict(node)
    raw = meta.get("antizapret_path")
    if raw:
        return Path(str(raw))
    return get_settings().antizapret_path


def _policy_service(db: Session, node: Node, adapter) -> AccessPolicyService:
    return AccessPolicyService(
        db,
        antizapret_path=_antizapret_path_for_node(node),
        node_id=node.id,
        node_name=node.name,
        adapter=adapter,
    )


def _apply_policy_op(
    svc: AccessPolicyService,
    primary_config: VpnConfig,
    op: PolicyOp,
    **kwargs: Any,
) -> dict:
    client_name = primary_config.client_name
    actor = kwargs.get("actor")

    if primary_config.vpn_type == VpnType.openvpn:
        if op == "block_temp":
            return svc.openvpn_temp_block(client_name, int(kwargs["days"]), actor=actor)
        if op == "block_permanent":
            return svc.openvpn_permanent_block(client_name, actor=actor)
        if op == "unblock":
            return svc.openvpn_unblock(client_name, actor=actor)
        if op == "set_traffic_limit":
            return svc.openvpn_set_traffic_limit(
                client_name,
                int(kwargs["limit_bytes"]),
                period_days=kwargs.get("period_days"),
                actor=actor,
            )
        if op == "clear_traffic_limit":
            return svc.openvpn_clear_traffic_limit(client_name, actor=actor)
        raise ValueError(f"Unsupported OpenVPN policy op: {op}")

    if op == "set_wg_expiry":
        return svc.wg_set_expiry(
            client_name,
            int(kwargs["days"]),
            extend=bool(kwargs.get("extend", False)),
            actor=actor,
        )
    if op == "block_temp":
        return svc.wg_temp_block(client_name, int(kwargs["days"]), actor=actor)
    if op == "block_permanent":
        return svc.wg_permanent_block(client_name, actor=actor)
    if op == "unblock":
        return svc.wg_unblock(client_name, actor=actor)
    if op == "set_traffic_limit":
        return svc.wg_set_traffic_limit(
            client_name,
            int(kwargs["limit_bytes"]),
            period_days=kwargs.get("period_days"),
            actor=actor,
        )
    if op == "clear_traffic_limit":
        return svc.wg_clear_traffic_limit(client_name, actor=actor)
    raise ValueError(f"Unsupported WireGuard policy op: {op}")


def _validate_policy_op(primary_config: VpnConfig, op: PolicyOp) -> None:
    if op == "set_wg_expiry" and primary_config.vpn_type != VpnType.wireguard:
        raise ValueError("set_wg_expiry applies only to WireGuard clients")


def replicate_policy_op(
    db: Session,
    group: NodeSyncGroup,
    primary_config: VpnConfig,
    op: PolicyOp,
    **kwargs: Any,
) -> dict[str, Any]:
    """Apply the same access-policy operation on all replica shadows (sync, blocking)."""
    if not is_auto_sync_enabled(group):
        return {"applied": [], "errors": [], "skipped": True}
    if not get_settings().node_sync_auto_replicate_policies:
        return {"applied": [], "errors": [], "skipped": True}

    _validate_policy_op(primary_config, op)

    primary_node = db.get(Node, group.primary_node_id)
    if primary_node is None:
        raise ValueError(f"Primary node {group.primary_node_id} not found")

    shadow_by_node_id = {shadow.node_id: shadow for shadow in get_shadow_configs(db, group, primary_config)}
    result = ReplicateResult(operation=ReplicateOperation.POLICY_APPLY)

    for replica_node in get_replica_nodes(db, group):
        shadow = shadow_by_node_id.get(replica_node.id)
        if shadow is None:
            message = (
                f"shadow VpnConfig not found for client {primary_config.client_name} "
                f"on replica {replica_node.name}"
            )
            logger.warning("HA policy sync skipped replica %s: %s", replica_node.name, message)
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": message}
            )
            continue

        adapter = get_adapter_for_node(replica_node)
        try:
            if op in _LIMIT_OPS:
                copy_single_client_policy(
                    db,
                    primary_node,
                    replica_node,
                    primary_config.client_name,
                    vpn_type=primary_config.vpn_type,
                )
            svc = _policy_service(db, replica_node, adapter)
            _apply_policy_op(svc, primary_config, op, **kwargs)
        except Exception as exc:
            logger.warning(
                "HA policy sync %s failed on replica %s: %s",
                op,
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue

        result.successes.append({"node_id": replica_node.id, "config_id": shadow.id})

    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"primary_config": primary_config, "policy_op": op},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return {"applied": result.successes, "errors": result.errors, "skipped": False}


def maybe_replicate_policy_op(
    db: Session,
    *,
    node_id: int,
    client_name: str,
    vpn_type: VpnType,
    op: PolicyOp,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Replicate a policy op to HA replicas when active node is primary in auto sync group."""
    group = find_sync_group_for_primary(db, node_id)
    if not group or not is_auto_sync_enabled(group):
        return None

    primary_config = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == client_name,
            VpnConfig.vpn_type == vpn_type,
        )
        .first()
    )
    if primary_config is None:
        return None

    return replicate_policy_op(db, group, primary_config, op, **kwargs)


def replicate_node_default_policy(
    db: Session,
    group: NodeSyncGroup,
    primary_node_id: int,
) -> dict[str, Any]:
    """Copy __node_default__ policy rows from primary to all HA replicas."""
    if not is_auto_sync_enabled(group):
        return {"applied": [], "errors": [], "skipped": True}
    if not get_settings().node_sync_auto_replicate_policies:
        return {"applied": [], "errors": [], "skipped": True}

    primary_node = db.get(Node, primary_node_id)
    if primary_node is None:
        raise ValueError(f"Primary node {primary_node_id} not found")

    result = ReplicateResult(operation=ReplicateOperation.POLICY_COPY_ALL)

    for replica_node in get_replica_nodes(db, group):
        try:
            copy_single_client_policy(
                db,
                primary_node,
                replica_node,
                NODE_DEFAULT_POLICY_CLIENT,
                vpn_type=VpnType.openvpn,
            )
            copy_single_client_policy(
                db,
                primary_node,
                replica_node,
                NODE_DEFAULT_POLICY_CLIENT,
                vpn_type=VpnType.wireguard,
            )
        except Exception as exc:
            logger.warning(
                "HA node-default sync failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue

        result.successes.append({"node_id": replica_node.id})

    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"node_id": primary_node_id},
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    )
    return {"applied": result.successes, "errors": result.errors, "skipped": False}


def heal_policy_drift(db: Session, group: NodeSyncGroup) -> dict[str, Any]:
    """Incremental reconcile heal: copy all access policies from primary to replicas."""
    if not is_auto_sync_enabled(group):
        return {"success": False, "skipped": True, "errors": [], "applied": []}
    if not get_settings().node_sync_auto_replicate_policies:
        return {"success": False, "skipped": True, "errors": [], "applied": []}

    primary_node = db.get(Node, group.primary_node_id)
    if primary_node is None:
        return {
            "success": False,
            "skipped": False,
            "errors": [{"error": f"Primary node {group.primary_node_id} not found"}],
            "applied": [],
        }

    result = ReplicateResult(operation=ReplicateOperation.POLICY_COPY_ALL)
    for replica_node in get_replica_nodes(db, group):
        try:
            copy_access_policies_from_node(db, primary_node, replica_node)
            adapter = get_adapter_for_node(replica_node)
            svc = _policy_service(db, replica_node, adapter)
            for row in db.query(OpenVpnAccessPolicy).filter_by(node_id=replica_node.id).all():
                if is_node_default_policy_client(row.client_name):
                    continue
                svc.reconcile_openvpn(row.client_name)
            for row in db.query(WgAccessPolicy).filter_by(node_id=replica_node.id).all():
                if is_node_default_policy_client(row.client_name):
                    continue
                svc.reconcile_wg(row.client_name, apply_runtime=True)
        except Exception as exc:
            logger.warning(
                "HA policy heal failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue
        result.successes.append({"node_id": replica_node.id, "node_name": replica_node.name})

    finalize_replicate_outcome(
        db,
        group,
        result,
        payload={"heal": "policy_drift"},
        set_synced_on_success=False,
        audit_on_partial_failure=True,
    )
    return {
        "success": not result.errors,
        "skipped": False,
        "errors": result.errors,
        "applied": result.successes,
    }


def maybe_replicate_node_default_policy(
    db: Session,
    *,
    node_id: int,
) -> dict[str, Any] | None:
    """Replicate node default policy when node_id is primary in an auto-sync HA group."""
    group = find_sync_group_for_primary(db, node_id)
    if not group or not is_auto_sync_enabled(group):
        return None
    return replicate_node_default_policy(db, group, node_id)
