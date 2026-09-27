"""AAAA answer switch (:: / NODATA) for the AntiZapret resolvers of the active node."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import DnsAaaaStateOut, DnsAaaaUpdate
from app.services.action_log import log_action
from app.services.file_editor import EDITABLE_FILES
from app.services.kresd_aaaa import AAAA_TARGETS, aaaa_mode, with_aaaa_nodata
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import require_ha_primary_for_config_ops

router = APIRouter(prefix="/dns-aaaa", tags=["dns-aaaa"])


def _state(adapter) -> DnsAaaaStateOut:
    modes = {target: aaaa_mode(adapter.read_config_file(EDITABLE_FILES[key])) for target, key in AAAA_TARGETS.items()}
    return DnsAaaaStateOut(**modes)


@router.get("", response_model=DnsAaaaStateOut)
def get_dns_aaaa(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _state(get_active_adapter(db))


@router.put("", response_model=DnsAaaaStateOut)
def set_dns_aaaa(
    payload: DnsAaaaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    adapter = get_active_adapter(db)
    key = AAAA_TARGETS[payload.target]
    filename = EDITABLE_FILES[key]
    content = adapter.read_config_file(filename)
    try:
        updated = with_aaaa_nodata(content, payload.nodata)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Блок AAAA в {filename} изменён вручную — поправьте его в Редакторе файлов",
        ) from exc
    if updated != content:
        adapter.write_config_file(filename, updated)
        maybe_replicate_config_files(
            db,
            node_id=get_active_node(db).id,
            file_keys=[key],
            run_doall=False,
            content_overrides={key: updated},
        )
        log_action(
            db,
            action="dns_aaaa_mode",
            user_id=current_user.id,
            username=current_user.username,
            details=f"target={payload.target};nodata={payload.nodata}",
        )
    return _state(adapter)
