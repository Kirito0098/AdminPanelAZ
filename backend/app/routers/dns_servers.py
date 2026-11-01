"""Upstream DNS choice for the AntiZapret resolvers of the active node."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import DnsServersStateOut, DnsServersUpdate
from app.services.action_log import log_action
from app.services.kresd_dns_choice import DnsServersUnsupportedError
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node
from app.services.node_sync.groups import (
    find_sync_group_for_primary,
    get_replica_nodes,
    is_auto_sync_enabled,
    require_ha_primary_for_config_ops,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dns-servers", tags=["dns-servers"])


def _proxy_node_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Выберите VPN-узел: у прокси-узла нет DNS-резолверов",
    )


@router.get("", response_model=DnsServersStateOut)
def get_dns_servers(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        state = get_active_adapter(db).get_dns_servers()
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc
    return DnsServersStateOut(**state)


@router.put("", response_model=DnsServersStateOut)
def apply_dns_servers(
    payload: DnsServersUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    node = get_active_node(db)
    try:
        result: dict[str, Any] = get_active_adapter(db).apply_dns_servers(
            antizapret=payload.antizapret, vpn=payload.vpn
        )
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [*(result.get("warnings") or []), *_replicate_to_replicas(db, node.id, payload)]
    log_action(
        db,
        action="dns_servers_choice",
        user_id=current_user.id,
        username=current_user.username,
        details=(
            f"antizapret={payload.antizapret};vpn={payload.vpn};"
            f"restarted={','.join(result.get('restarted') or [])}"
        ),
    )
    return DnsServersStateOut(**result)


def _replicate_to_replicas(db: Session, node_id: int, payload: DnsServersUpdate) -> list[str]:
    """Apply the same choice on HA replicas (kresd.conf is not part of the config-file sync)."""
    group = find_sync_group_for_primary(db, node_id)
    if group is None or not is_auto_sync_enabled(group):
        return []
    warnings: list[str] = []
    for replica in get_replica_nodes(db, group):
        try:
            get_adapter_for_node(replica).apply_dns_servers(antizapret=payload.antizapret, vpn=payload.vpn)
        except (DnsServersUnsupportedError, HTTPException) as exc:
            warnings.append(f"Реплика «{replica.name}»: {getattr(exc, 'detail', exc)}")
        except Exception as exc:  # best-effort: одна реплика не должна ломать ответ панели
            logger.warning("dns_servers: реплика %s (%s): %s", replica.id, replica.name, exc)
            warnings.append(f"Реплика «{replica.name}»: {exc}")
    return warnings
