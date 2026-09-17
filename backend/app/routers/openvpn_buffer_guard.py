from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Node, OpenVpnBufferGuardMode, User
from app.schemas import (
    OpenVpnBufferGuardEventOut,
    OpenVpnBufferGuardSettingsOut,
    OpenVpnBufferGuardSettingsUpdate,
)
from app.services.node_manager import get_adapter_for_node
from app.services.openvpn_buffer_guard import (
    _parse_watch_units,
    get_settings as get_guard_settings,
    list_events as list_guard_events,
    run_guard_pass,
    upsert_settings,
)


router = APIRouter(prefix="/openvpn-buffer-guard", tags=["openvpn-buffer-guard"])


class OpenVpnBufferGuardScanRequest(BaseModel):
    node_id: int


def _get_node_or_404(db: Session, node_id: int) -> Node:
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    return node


def _settings_to_response(row) -> OpenVpnBufferGuardSettingsOut:
    watch_units = _parse_watch_units(getattr(row, "watch_units_json", None))
    return OpenVpnBufferGuardSettingsOut(
        node_id=row.node_id,
        enabled=row.enabled,
        mode=row.mode,
        threshold_count=row.threshold_count,
        window_seconds=row.window_seconds,
        escalate_after_seconds=row.escalate_after_seconds,
        cooldown_minutes=row.cooldown_minutes,
        temp_ban_minutes=row.temp_ban_minutes,
        watch_units=watch_units,
        updated_at=row.updated_at,
    )


def _event_to_response(row) -> OpenVpnBufferGuardEventOut:
    try:
        raw_actions = json.loads(row.actions_json or "[]")
    except Exception:
        raw_actions = []

    actions: list[str] = []
    if isinstance(raw_actions, list):
        for item in raw_actions:
            action_type: str | None = None
            if isinstance(item, str):
                action_type = item.strip()
            elif isinstance(item, dict):
                action_type = str(item.get("type") or "").strip()
            if action_type and action_type not in actions:
                actions.append(action_type)

    return OpenVpnBufferGuardEventOut(
        id=row.id,
        node_id=row.node_id,
        created_at=row.created_at,
        unit=row.unit,
        common_name=row.common_name,
        real_address=row.real_address,
        error_count=row.error_count,
        window_seconds=row.window_seconds,
        mode=row.mode,
        actions=actions,
        result=row.result,
        detail=row.detail,
        manual=row.manual,
        ban_expires_at=row.ban_expires_at,
    )


@router.get("/settings", response_model=OpenVpnBufferGuardSettingsOut)
def get_openvpn_buffer_guard_settings(
    node_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _get_node_or_404(db, node_id)
    row = get_guard_settings(db, node_id)
    return _settings_to_response(row)


@router.put("/settings", response_model=OpenVpnBufferGuardSettingsOut)
def update_openvpn_buffer_guard_settings(
    payload: OpenVpnBufferGuardSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _get_node_or_404(db, payload.node_id)
    try:
        OpenVpnBufferGuardMode(payload.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый режим",
        ) from exc

    settings_row = upsert_settings(db, payload.node_id, payload.model_dump())
    return _settings_to_response(settings_row)


@router.get("/events", response_model=list[OpenVpnBufferGuardEventOut])
def list_openvpn_buffer_guard_events(
    node_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _get_node_or_404(db, node_id)
    safe_limit = max(1, min(int(limit or 20), 200))
    events = list_guard_events(db, node_id=node_id, limit=safe_limit)
    return [_event_to_response(event) for event in events]


@router.post("/scan", response_model=list[dict[str, Any]])
def scan_openvpn_buffer_guard(
    payload: OpenVpnBufferGuardScanRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    node = _get_node_or_404(db, payload.node_id)
    adapter = get_adapter_for_node(node)
    results = run_guard_pass(db, adapter, node.id, manual=True)
    return results


