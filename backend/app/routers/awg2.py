"""AZ-AWG2 (AmneziaWG 2.0 parallel layer) admin API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import Awg2ObfuscationApply
from app.services.awg2 import Awg2NotInstalledError
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node
from app.services.node_sync.groups import find_sync_group_for_primary, get_replica_nodes
from app.services.node_sync.vpn_state_sync import sync_amneziawg2_state_from_primary

router = APIRouter(prefix="/awg2", tags=["awg2"])


def _node_meta(node) -> dict:
    return {"node_id": node.id, "node_name": node.name, "node_host": node.host}


def _ha_sync_awg2_from_active(db: Session) -> dict[str, Any]:
    """Best-effort HA push of AWG2 state to replicas. Never raises."""
    errors: list[dict[str, str | None]] = []
    try:
        node = get_active_node(db)
        group = find_sync_group_for_primary(db, node.id)
        if not group:
            return {"attempted": False, "errors": []}
        primary_adapter = get_active_adapter(db)
        replicas = get_replica_nodes(db, group)
        if not replicas:
            return {"attempted": True, "errors": []}
        for replica in replicas:
            try:
                replica_adapter = get_adapter_for_node(replica)
                sync_amneziawg2_state_from_primary(primary_adapter, replica_adapter)
            except Exception as exc:  # noqa: BLE001 — collect warnings, do not fail apply
                errors.append({"node_name": getattr(replica, "name", None), "error": str(exc)})
        return {"attempted": True, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        return {"attempted": True, "errors": [{"node_name": None, "error": str(exc)}]}


def _map_awg2_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, Awg2NotInstalledError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/health")
def awg2_health(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    data = get_active_adapter(db).get_awg2_health()
    return {**data, **_node_meta(node)}


@router.get("/status")
def awg2_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_status()
    except Awg2NotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {**data, **_node_meta(node)}


@router.get("/obfuscation")
def get_obfuscation(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_obfuscation()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    return {**data, **_node_meta(node)}


@router.post("/obfuscation/regenerate")
def regenerate_obfuscation(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        result = get_active_adapter(db).awg2_obfuscation_regenerate()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    ha = _ha_sync_awg2_from_active(db)
    return {**result, **_node_meta(node), "ha": ha, "reimport_required": True}


@router.post("/obfuscation/apply")
def apply_obfuscation(
    payload: Awg2ObfuscationApply,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    node = get_active_node(db)
    try:
        result = get_active_adapter(db).awg2_obfuscation_apply(**payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    ha = _ha_sync_awg2_from_active(db)
    return {**result, **_node_meta(node), "ha": ha, "reimport_required": True}


@router.get("/monitoring")
def get_monitoring(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_monitoring()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    return {**data, **_node_meta(node)}
