"""Central HA auto-sync dispatcher: replicate operations from primary to replicas."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, NodeSyncGroup, SyncStatus, VpnConfig, VpnType
from app.services.action_log import log_action
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import get_replica_nodes, is_auto_sync_enabled
from app.services.node_sync.vpn_state_sync import (
    sync_openvpn_pki_from_primary,
    sync_vpn_crypto_from_primary,
)

logger = logging.getLogger(__name__)


class ReplicateOperation(str, Enum):
    CLIENT_CREATE = "client_create"
    CLIENT_DELETE = "client_delete"
    CLIENT_RENEW_CERT = "client_renew_cert"
    CLIENT_METADATA_PATCH = "client_metadata_patch"
    POLICY_APPLY = "policy_apply"
    POLICY_COPY_ALL = "policy_copy_all"
    CONFIG_FILES_WRITE = "config_files_write"
    ANTIZAPRET_SETTINGS_PATCH = "antizapret_settings_patch"
    ROUTING_APPLY = "routing_apply"
    CIDR_DEPLOY_FILES = "cidr_deploy_files"
    OPENVPN_DISCONNECT = "openvpn_disconnect"


@dataclass
class ReplicateResult:
    operation: ReplicateOperation
    skipped: bool = False
    successes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_legacy_dict(self) -> dict[str, Any]:
        if self.operation == ReplicateOperation.CLIENT_CREATE:
            return {"replicated": self.successes, "errors": self.errors, "skipped": self.skipped}
        if self.operation == ReplicateOperation.CLIENT_DELETE:
            return {"deleted": self.successes, "errors": self.errors, "skipped": self.skipped}
        return {
            "operation": self.operation.value,
            "successes": self.successes,
            "errors": self.errors,
            "skipped": self.skipped,
        }


@dataclass(frozen=True)
class _OperationSpec:
    handler: Callable[[Session, NodeSyncGroup, dict[str, Any]], ReplicateResult] | None
    set_synced_on_success: bool = True
    audit_on_partial_failure: bool = False


def get_shadow_configs(db: Session, group: NodeSyncGroup, primary_config: VpnConfig) -> list[VpnConfig]:
    """Return replica VpnConfig rows linked to the primary config."""
    replica_ids = {node.id for node in get_replica_nodes(db, group)}
    if not replica_ids:
        return []
    shadows = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.ha_primary_config_id == primary_config.id,
            VpnConfig.node_id.in_(replica_ids),
        )
        .all()
    )
    return shadows


def iter_replica_adapters(db: Session, group: NodeSyncGroup) -> Iterator[tuple[Node, Any]]:
    for replica_node in get_replica_nodes(db, group):
        yield replica_node, get_adapter_for_node(replica_node)


def _primary_adapter(db: Session, group: NodeSyncGroup):
    primary_node = db.get(Node, group.primary_node_id)
    if primary_node is None:
        raise ValueError(f"Primary node {group.primary_node_id} not found")
    return get_adapter_for_node(primary_node)


def _handle_client_create(db: Session, group: NodeSyncGroup, payload: dict[str, Any]) -> ReplicateResult:
    primary_config: VpnConfig = payload["primary_config"]
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_CREATE)
    primary_adapter = _primary_adapter(db, group)

    for replica_node, adapter in iter_replica_adapters(db, group):
        try:
            sync_vpn_crypto_from_primary(
                primary_adapter,
                adapter,
                primary_config.vpn_type,
            )
        except Exception as exc:
            logger.warning(
                "HA auto-sync create failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue

        existing = (
            db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == replica_node.id,
                VpnConfig.client_name == primary_config.client_name,
                VpnConfig.vpn_type == primary_config.vpn_type,
            )
            .first()
        )
        if existing:
            existing.sync_group_id = group.id
            existing.ha_primary_config_id = primary_config.id
            shadow = existing
        else:
            shadow = VpnConfig(
                node_id=replica_node.id,
                client_name=primary_config.client_name,
                vpn_type=primary_config.vpn_type,
                owner_id=primary_config.owner_id,
                cert_expire_days=primary_config.cert_expire_days,
                description=primary_config.description,
                sync_group_id=group.id,
                ha_primary_config_id=primary_config.id,
            )
            db.add(shadow)
        db.flush()
        result.successes.append({"node_id": replica_node.id, "config_id": shadow.id})

    primary_config.sync_group_id = group.id
    primary_config.ha_primary_config_id = None
    return result


def _handle_client_delete(db: Session, group: NodeSyncGroup, payload: dict[str, Any]) -> ReplicateResult:
    primary_config: VpnConfig = payload["primary_config"]
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_DELETE)
    primary_adapter = _primary_adapter(db, group)

    for shadow in get_shadow_configs(db, group, primary_config):
        replica_node = db.get(Node, shadow.node_id)
        if not replica_node:
            db.delete(shadow)
            continue
        adapter = get_adapter_for_node(replica_node)
        try:
            sync_vpn_crypto_from_primary(primary_adapter, adapter, shadow.vpn_type)
        except Exception as exc:
            logger.warning(
                "HA auto-sync delete failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue
        result.successes.append({"node_id": replica_node.id, "config_id": shadow.id})
        db.delete(shadow)

    return result


def _handle_client_renew_cert(db: Session, group: NodeSyncGroup, payload: dict[str, Any]) -> ReplicateResult:
    primary_config: VpnConfig = payload["primary_config"]
    cert_expire_days = int(payload["cert_expire_days"])
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_RENEW_CERT)

    if primary_config.vpn_type != VpnType.openvpn:
        result.errors.append({"error": "cert renew applies only to OpenVPN clients"})
        return result

    primary_adapter = _primary_adapter(db, group)
    shadow_by_node_id = {shadow.node_id: shadow for shadow in get_shadow_configs(db, group, primary_config)}
    for replica_node in get_replica_nodes(db, group):
        shadow = shadow_by_node_id.get(replica_node.id)
        if shadow is None:
            message = (
                f"shadow VpnConfig not found for client {primary_config.client_name} "
                f"on replica {replica_node.name}"
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": message}
            )
            continue
        adapter = get_adapter_for_node(replica_node)
        try:
            sync_openvpn_pki_from_primary(primary_adapter, adapter)
            shadow.cert_expire_days = cert_expire_days
            db.flush()
        except Exception as exc:
            logger.warning(
                "HA auto-sync cert renew failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": str(exc)}
            )
            continue
        result.successes.append({"node_id": replica_node.id, "config_id": shadow.id})

    return result


def _handle_client_metadata_patch(db: Session, group: NodeSyncGroup, payload: dict[str, Any]) -> ReplicateResult:
    primary_config: VpnConfig = payload["primary_config"]
    result = ReplicateResult(operation=ReplicateOperation.CLIENT_METADATA_PATCH)
    shadow_by_node_id = {shadow.node_id: shadow for shadow in get_shadow_configs(db, group, primary_config)}

    for replica_node in get_replica_nodes(db, group):
        shadow = shadow_by_node_id.get(replica_node.id)
        if shadow is None:
            message = (
                f"shadow VpnConfig not found for client {primary_config.client_name} "
                f"on replica {replica_node.name}"
            )
            result.errors.append(
                {"node_id": replica_node.id, "node_name": replica_node.name, "error": message}
            )
            continue
        shadow.description = primary_config.description
        shadow.owner_id = primary_config.owner_id
        db.flush()
        result.successes.append({"node_id": replica_node.id, "config_id": shadow.id})

    return result


def _stub_not_implemented(
    db: Session,
    group: NodeSyncGroup,
    payload: dict[str, Any],
    *,
    operation: ReplicateOperation,
) -> ReplicateResult:
    del db, group, payload
    return ReplicateResult(
        operation=operation,
        errors=[{"error": f"{operation.value} is not implemented yet"}],
    )


_OPERATION_REGISTRY: dict[ReplicateOperation, _OperationSpec] = {
    ReplicateOperation.CLIENT_CREATE: _OperationSpec(
        handler=_handle_client_create,
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    ),
    ReplicateOperation.CLIENT_DELETE: _OperationSpec(
        handler=_handle_client_delete,
        set_synced_on_success=False,
    ),
    ReplicateOperation.CLIENT_RENEW_CERT: _OperationSpec(
        handler=_handle_client_renew_cert,
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    ),
    ReplicateOperation.CLIENT_METADATA_PATCH: _OperationSpec(
        handler=_handle_client_metadata_patch,
        set_synced_on_success=True,
        audit_on_partial_failure=True,
    ),
    ReplicateOperation.POLICY_APPLY: _OperationSpec(handler=None),
    ReplicateOperation.POLICY_COPY_ALL: _OperationSpec(handler=None),
    ReplicateOperation.CONFIG_FILES_WRITE: _OperationSpec(handler=None),
    ReplicateOperation.ANTIZAPRET_SETTINGS_PATCH: _OperationSpec(handler=None),
    ReplicateOperation.ROUTING_APPLY: _OperationSpec(handler=None),
    ReplicateOperation.CIDR_DEPLOY_FILES: _OperationSpec(handler=None),
}


def _resolve_operation(operation: ReplicateOperation | str) -> ReplicateOperation:
    if isinstance(operation, ReplicateOperation):
        return operation
    return ReplicateOperation(str(operation).strip())


def _audit_subject_for_result(result: ReplicateResult, payload: dict[str, Any]) -> str | None:
    if result.operation == ReplicateOperation.ANTIZAPRET_SETTINGS_PATCH:
        filtered = payload.get("filtered_updates")
        if isinstance(filtered, dict):
            keys = ",".join(sorted(filtered.keys())) or "-"
            return f"settings_keys={keys}"
        return "settings_keys=-"

    if result.operation == ReplicateOperation.CIDR_DEPLOY_FILES:
        filename = payload.get("filename")
        if filename:
            return f"provider={filename}"
        filenames = payload.get("filenames")
        if isinstance(filenames, list) and filenames:
            return f"providers={','.join(str(name) for name in filenames)}"
        return "providers=-"

    client_name = payload.get("client_name")
    if client_name and result.operation == ReplicateOperation.OPENVPN_DISCONNECT:
        return f"client={client_name}, op=openvpn_disconnect"

    primary_config = payload.get("primary_config")
    if primary_config is not None:
        if result.operation == ReplicateOperation.CLIENT_CREATE:
            return f"client={primary_config.client_name}"
        if result.operation == ReplicateOperation.POLICY_APPLY:
            policy_op = payload.get("policy_op") or "unknown"
            return f"client={primary_config.client_name}, op={policy_op}"
        if result.operation in {
            ReplicateOperation.CLIENT_RENEW_CERT,
            ReplicateOperation.CLIENT_METADATA_PATCH,
        }:
            return f"client={primary_config.client_name}, op={result.operation.value}"
    return None


def finalize_replicate_outcome(
    db: Session,
    group: NodeSyncGroup,
    result: ReplicateResult,
    *,
    payload: dict[str, Any] | None = None,
    set_synced_on_success: bool = True,
    audit_on_partial_failure: bool = False,
) -> None:
    """Apply sync_status, commit, and optional partial-failure audit."""
    payload = payload or {}

    if result.errors:
        group.sync_status = SyncStatus.failed
        group.last_sync_error = result.errors[0]["error"]
    elif set_synced_on_success:
        group.sync_status = SyncStatus.synced
        group.last_sync_error = None
    else:
        group.last_sync_error = None

    db.commit()

    if not result.errors or not audit_on_partial_failure or not get_settings().audit_log_enabled:
        return

    audit_subject = _audit_subject_for_result(result, payload)
    if not audit_subject:
        return

    successful_names: list[str] = []
    for entry in result.successes:
        node = db.get(Node, entry["node_id"])
        if node:
            successful_names.append(node.name)
    failed_names = [entry["node_name"] for entry in result.errors if entry.get("node_name")]
    log_action(
        db,
        action="ha_replicate_partial_failure",
        details=(
            f"{audit_subject}, "
            f"successful_replicas={','.join(successful_names) or '-'}, "
            f"failed_replicas={','.join(failed_names)}"
        ),
    )


def replicate_to_replicas(
    db: Session,
    group: NodeSyncGroup,
    operation: ReplicateOperation | str,
    payload: dict[str, Any],
) -> ReplicateResult:
    operation = _resolve_operation(operation)

    if not is_auto_sync_enabled(group):
        return ReplicateResult(operation=operation, skipped=True)

    spec = _OPERATION_REGISTRY.get(operation)
    if spec is None:
        result = ReplicateResult(
            operation=operation,
            errors=[{"error": f"unknown replicate operation: {operation.value}"}],
        )
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload=payload,
            set_synced_on_success=False,
        )
        return result

    if spec.handler is None:
        result = _stub_not_implemented(db, group, payload, operation=operation)
        finalize_replicate_outcome(
            db,
            group,
            result,
            payload=payload,
            set_synced_on_success=False,
        )
        return result

    result = spec.handler(db, group, payload)
    finalize_replicate_outcome(
        db,
        group,
        result,
        payload=payload,
        set_synced_on_success=spec.set_synced_on_success,
        audit_on_partial_failure=spec.audit_on_partial_failure,
    )
    return result
