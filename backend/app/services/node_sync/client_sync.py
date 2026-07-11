"""Auto-sync VPN clients from primary to replicas in a sync group."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import VpnConfig
from app.services.node_sync.groups import find_sync_group_for_primary, is_auto_sync_enabled
from app.services.node_sync.manual_link import link_primary_config_to_group
from app.services.node_sync.replicate import ReplicateOperation, replicate_to_replicas
from app.services.node_sync.vpn_state_sync import replicate_primary_crypto_to_replicas


def format_ha_replicate_errors(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    errors = result.get("errors") or []
    if not errors:
        return None
    nodes = ", ".join(str(entry.get("node_name") or entry.get("node_id") or "?") for entry in errors)
    first_error = str(errors[0].get("error") or "неизвестная ошибка")
    return f"Не удалось синхронизировать VPN-ключи на реплику ({nodes}): {first_error}"


def replicate_client_create(
    db: Session,
    group,
    primary_config: VpnConfig,
) -> dict[str, Any]:
    """Create matching client on all replicas and linked VpnConfig rows."""
    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_CREATE,
        {"primary_config": primary_config},
    )
    return result.to_legacy_dict()


def replicate_client_delete(
    db: Session,
    group,
    primary_config: VpnConfig,
) -> dict[str, Any]:
    """Delete client from replicas and remove shadow VpnConfig rows."""
    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_DELETE,
        {"primary_config": primary_config},
    )
    return result.to_legacy_dict()


def maybe_replicate_create(db: Session, *, node_id: int, primary_config: VpnConfig) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if is_auto_sync_enabled(group):
        return replicate_client_create(db, group, primary_config)

    crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
    link_primary_config_to_group(db, group, primary_config)
    return {
        "replicated": crypto.get("successes") or [],
        "errors": crypto.get("errors") or [],
        "skipped": False,
        "linked": True,
        "crypto": crypto,
    }


def purge_ha_shadow_configs(db: Session, primary_config_id: int) -> int:
    """Remove replica VpnConfig rows pointing at a primary (FK safety before primary delete)."""
    return (
        db.query(VpnConfig)
        .filter(VpnConfig.ha_primary_config_id == primary_config_id)
        .delete(synchronize_session=False)
    )


def maybe_replicate_delete(db: Session, *, node_id: int, primary_config: VpnConfig) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if is_auto_sync_enabled(group):
        result = replicate_client_delete(db, group, primary_config)
        if not (result.get("deleted") or result.get("errors")):
            crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
            return {
                "deleted": crypto.get("successes") or [],
                "errors": crypto.get("errors") or [],
                "skipped": False,
                "crypto": crypto,
                "fallback": True,
            }
        return result

    crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
    return {
        "deleted": crypto.get("successes") or [],
        "errors": crypto.get("errors") or [],
        "skipped": False,
        "crypto": crypto,
    }


def maybe_replicate_cert_renew(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
    cert_expire_days: int,
) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group:
        return None
    if is_auto_sync_enabled(group):
        result = replicate_to_replicas(
            db,
            group,
            ReplicateOperation.CLIENT_RENEW_CERT,
            {"primary_config": primary_config, "cert_expire_days": cert_expire_days},
        )
        return result.to_legacy_dict()

    if primary_config.vpn_type.value != "openvpn":
        return None
    crypto = replicate_primary_crypto_to_replicas(db, group, primary_config)
    return {"successes": crypto.get("successes") or [], "errors": crypto.get("errors") or [], "crypto": crypto}


def maybe_replicate_config_metadata(
    db: Session,
    *,
    node_id: int,
    primary_config: VpnConfig,
) -> dict[str, Any] | None:
    group = find_sync_group_for_primary(db, node_id)
    if not group or not is_auto_sync_enabled(group):
        return None
    result = replicate_to_replicas(
        db,
        group,
        ReplicateOperation.CLIENT_METADATA_PATCH,
        {"primary_config": primary_config},
    )
    return result.to_legacy_dict()
