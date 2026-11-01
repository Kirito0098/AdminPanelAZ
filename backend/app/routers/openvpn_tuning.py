"""OpenVPN server tuning (duplicate-cn, detailed logs) and the install-state snapshot."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    OpenVpnDcoUpdate,
    OpenVpnMtuUpdate,
    OpenVpnPatchUpdate,
    OpenVpnProtocolsUpdate,
    OpenVpnTuningStateOut,
    OpenVpnTuningUpdate,
)
from app.services.action_log import log_action
from app.services.node_manager import get_active_adapter, get_adapter_for_node
from app.services.node_sync.groups import (
    find_sync_group_for_primary,
    get_replica_nodes,
    is_auto_sync_enabled,
    require_ha_primary_for_config_ops,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openvpn-tuning", tags=["openvpn-tuning"])


def _proxy_node_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Выберите VPN-узел: у прокси-узла нет OpenVPN",
    )


@router.get("", response_model=OpenVpnTuningStateOut)
def get_openvpn_tuning(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        state = get_active_adapter(db).get_openvpn_tuning()
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc
    return OpenVpnTuningStateOut(**state)


@router.put("", response_model=OpenVpnTuningStateOut)
def apply_openvpn_tuning(
    payload: OpenVpnTuningUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    adapter = get_active_adapter(db)
    try:
        result = adapter.apply_openvpn_tuning(duplicate=payload.duplicate, logs=payload.logs)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [
        *(result.get("warnings") or []),
        *_replicate_to_replicas(
            db,
            lambda adapter: adapter.apply_openvpn_tuning(duplicate=payload.duplicate, logs=payload.logs),
        ),
    ]
    log_action(
        db,
        action="openvpn_tuning",
        user_id=current_user.id,
        username=current_user.username,
        details=(
            f"duplicate={payload.duplicate};logs={payload.logs};"
            f"restarted={','.join(result.get('restarted') or [])}"
        ),
    )
    return OpenVpnTuningStateOut(**result)


def _replicate_to_replicas(db: Session, apply_to_replica) -> list[str]:
    """Применить то же изменение на репликах HA: server conf у каждого узла свой."""
    from app.services.node_manager import get_active_node

    group = find_sync_group_for_primary(db, get_active_node(db).id)
    if group is None or not is_auto_sync_enabled(group):
        return []
    warnings: list[str] = []
    for replica in get_replica_nodes(db, group):
        try:
            apply_to_replica(get_adapter_for_node(replica))
        except HTTPException as exc:
            warnings.append(f"Реплика «{replica.name}»: {exc.detail}")
        except Exception as exc:  # best-effort: одна реплика не должна ломать ответ панели
            logger.warning("openvpn tuning: реплика %s (%s): %s", replica.id, replica.name, exc)
            warnings.append(f"Реплика «{replica.name}»: {exc}")
    return warnings


@router.put("/mtu", response_model=OpenVpnTuningStateOut)
def apply_mtu(
    payload: OpenVpnMtuUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_mtu(
            openvpn_mtu=payload.openvpn, wireguard_mtu=payload.wireguard
        )
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [
        *(result.get("warnings") or []),
        *_replicate_to_replicas(
            db,
            lambda adapter: adapter.apply_mtu(openvpn_mtu=payload.openvpn, wireguard_mtu=payload.wireguard),
        ),
    ]
    log_action(
        db,
        action="openvpn_mtu",
        user_id=current_user.id,
        username=current_user.username,
        details=(
            f"openvpn={payload.openvpn or '—'};wireguard={payload.wireguard or '—'};"
            f"restarted={','.join(result.get('restarted') or [])}"
        ),
    )
    return OpenVpnTuningStateOut(**result)


@router.put("/dco", response_model=OpenVpnTuningStateOut)
def apply_dco(
    payload: OpenVpnDcoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_dco(payload.enabled)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    result["warnings"] = [
        *(result.get("warnings") or []),
        *_replicate_to_replicas(db, lambda adapter: adapter.apply_dco(payload.enabled)),
    ]
    log_action(
        db,
        action="openvpn_dco",
        user_id=current_user.id,
        username=current_user.username,
        details=f"enabled={payload.enabled};restarted={','.join(result.get('restarted') or [])}",
    )
    return OpenVpnTuningStateOut(**result)


@router.put("/protocols", response_model=OpenVpnTuningStateOut)
def apply_protocols(
    payload: OpenVpnProtocolsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_protocols(payload.units)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    log_action(
        db,
        action="openvpn_protocols",
        user_id=current_user.id,
        username=current_user.username,
        details=";".join(f"{unit}={enabled}" for unit, enabled in payload.units.items()),
    )
    return OpenVpnTuningStateOut(**result)


@router.post("/patch", response_model=OpenVpnTuningStateOut)
def apply_openvpn_patch(
    payload: OpenVpnPatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = get_active_adapter(db).apply_openvpn_patch(payload.algorithm)
    except NotImplementedError as exc:
        raise _proxy_node_error() from exc

    log_action(
        db,
        action="openvpn_patch",
        user_id=current_user.id,
        username=current_user.username,
        details=f"algorithm={payload.algorithm}",
    )
    return OpenVpnTuningStateOut(**result)
