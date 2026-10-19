"""provision_config / deprovision_config — extracted from POST /configs and DELETE /configs/{id}.

Both take an explicit node and use ``get_adapter_for_node(node)`` instead of the active node.
The routers stay thin wrappers and behave exactly as before.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, User, VpnConfig, VpnType
from app.services.access_policy import AccessPolicyService, forget_deleted_openvpn_client
from app.services.admin_notify import admin_notify_service
from app.services.awg2 import compute_expires_at, require_awg2_installed
from app.services.client_names import (
    assert_name_not_reserved_by_other_user,
    validate_new_client_name,
)
from app.services.client_portal import cleanup_deleted_client_records
from app.services.feature_guards import get_feature_service, require_vpn_type
from app.services.node_manager import get_adapter_for_node, node_metadata_dict
from app.services.node_sync.client_sync import (
    format_ha_replicate_errors,
    maybe_replicate_create,
    maybe_replicate_delete,
    purge_ha_shadow_configs,
)
from app.services.node_sync.groups import find_sync_group_for_primary
from app.services.notify_time import get_client_timezone_from_request
from app.services.openvpn_cert import refresh_config_cert_expiry
from app.services.openvpn_profile_repair import recreate_openvpn_profiles_after_admin_change
from app.services.profile_delivery import load_node_remote_hosts
from app.services.traffic.maintenance import purge_traffic_history_for_reused_name
from app.services.user_subscription import (
    apply_owner_access_until_to_config,
    replicate_inherited_access_until,
)
from app.services.vpn_profile_visibility import enforce_can_create_vpn_type

_VPN_PROTOCOLS = {
    VpnType.openvpn: "openvpn",
    VpnType.wireguard: "wireguard",
    VpnType.amneziawg2: "amneziawg2",
}


def provision_config(
    db: Session,
    *,
    node: Node,
    client_name: str,
    vpn_type: VpnType,
    owner: User,
    actor: User,
    notify: bool,
    cert_expire_days: int | None = None,
    ttl: int | None = None,
    description: str | None = None,
) -> tuple[VpnConfig, str | None]:
    """Create a client profile on an explicit node.

    Returns ``(config, ha_replicate_warning)``. Never consults the active node.
    """
    existing = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node.id,
            VpnConfig.client_name == client_name,
            VpnConfig.vpn_type == vpn_type,
        )
        .first()
    )
    if existing:
        raise ValueError("Конфигурация уже существует")
    validate_new_client_name(db, node_id=node.id, client_name=client_name, owner_id=owner.id)
    assert_name_not_reserved_by_other_user(db, client_name, owner_id=owner.id)

    require_vpn_type(vpn_type.value, service=get_feature_service())
    enforce_can_create_vpn_type(db, actor, vpn_type)
    adapter = get_adapter_for_node(node)

    awg2_expires_at = None
    if vpn_type == VpnType.openvpn:
        adapter.add_openvpn_client(client_name, cert_expire_days)
        recreate_openvpn_profiles_after_admin_change(
            adapter,
            client_names=[client_name],
            hosts=load_node_remote_hosts(db, node.id),
        )
    elif vpn_type == VpnType.wireguard:
        adapter.add_wireguard_client(client_name)
    elif vpn_type == VpnType.amneziawg2:
        require_awg2_installed(adapter)
        try:
            awg2_expires_at = compute_expires_at(ttl)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if ttl:
            adapter.awg2_add_client(client_name, ttl=ttl)
        else:
            adapter.awg2_add_client(client_name)
    else:
        raise ValueError("Неизвестный тип VPN")

    config = VpnConfig(
        node_id=node.id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=owner.id,
        cert_expire_days=cert_expire_days,
        expires_at=awg2_expires_at,
        description=description,
    )
    refresh_config_cert_expiry(config, adapter)
    purge_traffic_history_for_reused_name(db, node_id=node.id, client_name=client_name)
    db.add(config)
    db.commit()
    db.refresh(config)

    inherit = apply_owner_access_until_to_config(
        db, config, actor=actor.username, commit=True, replicate=False
    )

    # Stage 3: a config created for a suspended / traffic-limited owner inherits the sticky block.
    owner = config.owner
    if owner is not None:
        protocol = _VPN_PROTOCOLS.get(config.vpn_type)
        if protocol is not None:
            if owner.suspended_at is not None:
                reason = "user_suspended"
            elif owner.traffic_limit_blocked:
                reason = "user_traffic_limit"
            else:
                reason = None
            if reason is not None:
                antizapret_path = Path(
                    str(node_metadata_dict(node).get("antizapret_path") or get_settings().antizapret_path)
                )
                svc = AccessPolicyService(
                    db,
                    antizapret_path=antizapret_path,
                    node_id=node.id,
                    node_name=node.name,
                    adapter=adapter,
                )
                svc.set_reason_block(protocol, config.client_name, reason, actor=actor.username)

    ha_replicate_warning: str | None = None
    group = find_sync_group_for_primary(db, node_id=node.id)
    if group:
        replicate_result = maybe_replicate_create(db, node_id=node.id, primary_config=config)
        ha_replicate_warning = format_ha_replicate_errors(replicate_result)
        inherit = replicate_inherited_access_until(db, config, inherit, actor=actor.username)

    if inherit.get("warning"):
        if ha_replicate_warning:
            ha_replicate_warning = f"{ha_replicate_warning}; {inherit['warning']}"
        else:
            ha_replicate_warning = inherit["warning"]

    if notify:
        admin_notify_service.send_config_create(
            db,
            actor_username=actor.username,
            target_name=config.client_name,
            target_type=config.vpn_type.value,
            node_id=node.id,
            node_name=node.name,
            client_timezone=get_client_timezone_from_request(None),
        )
    return config, ha_replicate_warning


def deprovision_config(
    db: Session,
    *,
    config: VpnConfig,
    actor: User,
    notify: bool,
    request: Request | None = None,
) -> None:
    """Delete a client profile on its own node. Never consults the active node."""
    node = db.get(Node, config.node_id)
    adapter = get_adapter_for_node(node)
    if config.vpn_type == VpnType.openvpn:
        adapter.delete_openvpn_client(config.client_name)
        forget_deleted_openvpn_client(db, adapter, node_id=config.node_id, client_name=config.client_name)
    elif config.vpn_type == VpnType.amneziawg2:
        adapter.awg2_delete_client(config.client_name)
    else:
        adapter.delete_wireguard_client(config.client_name)

    client_name = config.client_name
    vpn_type = config.vpn_type.value

    sync_group = find_sync_group_for_primary(db, node.id)
    if sync_group:
        maybe_replicate_delete(db, node_id=node.id, primary_config=config)

    purge_ha_shadow_configs(db, config.id)
    db.delete(config)
    cleanup_deleted_client_records(db, config)
    db.commit()

    if notify:
        admin_notify_service.send_config_delete(
            db,
            actor_username=actor.username,
            target_name=client_name,
            target_type=vpn_type,
            node_id=node.id,
            node_name=node.name,
            client_timezone=get_client_timezone_from_request(request),
        )
