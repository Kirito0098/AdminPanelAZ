"""Node Sync Group API — HA failover pairs."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import NodeSyncGroup, SyncStatus, User
from app.schemas import (
    MessageResponse,
    NodeSyncGroupCreate,
    NodeSyncGroupResponse,
    NodeSyncGroupStatusResponse,
    NodeSyncGroupUpdate,
    NodeSyncPushFullResponse,
    NodeSyncVerifyResponse,
)
from app.services.antizapret_settings import shared_domain_conflicts_with_panel_domain
from app.services.background_tasks import background_task_service
from app.services.env_file import EnvFileService
from app.services.node_sync.groups import (
    apply_group_fields,
    effective_openvpn_domain,
    effective_wireguard_domain,
    group_to_dict,
    is_auto_sync_enabled,
    parse_replica_node_ids,
    raise_if_preflight_errors,
    validate_sync_group_payload,
)
from app.services.node_sync.dissolve import clear_shadow_links_for_group, dissolve_sync_group
from app.services.node_sync.manual_link import link_primary_configs_to_group
from app.services.node_sync.setup import make_group_setup_callable
from app.services.node_sync.shadow_link import link_shadow_configs_for_group
from app.services.node_sync.shared_domain import make_shared_domain_callable
from app.services.node_sync.verify import verify_sync_group

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

router = APIRouter(prefix="/nodes/sync-groups", tags=["node-sync"])


def _to_response(group: NodeSyncGroup, db: Session) -> NodeSyncGroupResponse:
    return NodeSyncGroupResponse(**group_to_dict(group, db))


def _reject_shared_domains_panel_conflict(*domains: str | None) -> None:
    panel_domain = EnvFileService(_ENV_FILE).get_env_value("DOMAIN", "")
    for domain in domains:
        if domain is None:
            continue
        conflict = shared_domain_conflicts_with_panel_domain(domain, panel_domain)
        if conflict:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=conflict)


def _normalize_wireguard_domain(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


@router.get("", response_model=list[NodeSyncGroupResponse])
def list_sync_groups(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    groups = db.query(NodeSyncGroup).order_by(NodeSyncGroup.name).all()
    return [_to_response(group, db) for group in groups]


@router.post("", response_model=NodeSyncGroupResponse, status_code=status.HTTP_201_CREATED)
def create_sync_group(
    payload: NodeSyncGroupCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    errors = validate_sync_group_payload(
        db,
        primary_node_id=payload.primary_node_id,
        replica_node_ids=payload.replica_node_ids,
    )
    raise_if_preflight_errors(errors)
    openvpn_domain = payload.shared_domain.strip()
    wireguard_domain = _normalize_wireguard_domain(payload.shared_domain_wireguard)
    _reject_shared_domains_panel_conflict(openvpn_domain, wireguard_domain or openvpn_domain)
    group = NodeSyncGroup(
        name=payload.name.strip(),
        shared_domain=openvpn_domain,
        shared_domain_wireguard=wireguard_domain or openvpn_domain,
        primary_node_id=payload.primary_node_id,
        replica_node_ids=json.dumps(sorted(set(payload.replica_node_ids))),
        sync_mode=payload.sync_mode or "manual_full",
        sync_status=SyncStatus.unknown,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    if is_auto_sync_enabled(group):
        link_shadow_configs_for_group(db, group)
        db.commit()
    else:
        link_primary_configs_to_group(db, group)
    return _to_response(group, db)


@router.get("/{group_id}", response_model=NodeSyncGroupResponse)
def get_sync_group(
    group_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")
    return _to_response(group, db)


@router.put("/{group_id}", response_model=NodeSyncGroupResponse)
def update_sync_group(
    group_id: int,
    payload: NodeSyncGroupUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")

    primary_id = payload.primary_node_id if payload.primary_node_id is not None else group.primary_node_id
    replica_ids = payload.replica_node_ids
    if replica_ids is None:
        replica_ids = parse_replica_node_ids(group.replica_node_ids)

    errors = validate_sync_group_payload(
        db,
        primary_node_id=primary_id,
        replica_node_ids=replica_ids,
        exclude_group_id=group.id,
    )
    raise_if_preflight_errors(errors)
    if payload.shared_domain is not None:
        _reject_shared_domains_panel_conflict(payload.shared_domain)
    if payload.shared_domain_wireguard is not None:
        wg = _normalize_wireguard_domain(payload.shared_domain_wireguard)
        ovpn = (
            payload.shared_domain.strip()
            if payload.shared_domain is not None
            else effective_openvpn_domain(group)
        )
        _reject_shared_domains_panel_conflict(wg or ovpn)

    previous_sync_mode = group.sync_mode
    apply_group_fields(
        group,
        name=payload.name,
        shared_domain=payload.shared_domain,
        shared_domain_wireguard=payload.shared_domain_wireguard,
        primary_node_id=payload.primary_node_id,
        replica_node_ids=payload.replica_node_ids,
        sync_mode=payload.sync_mode,
    )
    db.commit()
    db.refresh(group)
    new_mode = str(group.sync_mode or "").strip().lower()
    prev_mode = str(previous_sync_mode or "").strip().lower()
    if prev_mode == "auto" and new_mode == "manual_full":
        clear_shadow_links_for_group(db, group)
        db.commit()
    if is_auto_sync_enabled(group) and prev_mode != "auto":
        link_shadow_configs_for_group(db, group)
        db.commit()
    return _to_response(group, db)


@router.delete("/{group_id}", response_model=MessageResponse)
def delete_sync_group(
    group_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")
    dissolve_sync_group(db, group)
    db.delete(group)
    db.commit()
    return MessageResponse(
        message="Sync group расформирована: узлы независимы, конфиги и файлы на каждом сервере сохранены"
    )


@router.get("/{group_id}/status", response_model=NodeSyncGroupStatusResponse)
def sync_group_status(
    group_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")

    progress_percent = None
    progress_stage = None
    if group.last_sync_task_id and group.sync_status == SyncStatus.pending:
        task = background_task_service.get_task(group.last_sync_task_id)
        if task:
            progress_percent = task.progress_percent
            progress_stage = task.progress_stage

    return NodeSyncGroupStatusResponse(
        group_id=group.id,
        sync_status=group.sync_status,
        last_sync_at=group.last_sync_at,
        last_verify_at=group.last_verify_at,
        last_sync_task_id=group.last_sync_task_id,
        last_sync_error=group.last_sync_error,
        progress_percent=progress_percent,
        progress_stage=progress_stage,
    )


@router.post(
    "/{group_id}/setup",
    response_model=NodeSyncPushFullResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def setup_sync_group(
    group_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """One-shot HA bring-up: shared domain → full push to replicas → verify (single task)."""
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")
    if group.sync_status == SyncStatus.pending:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Синхронизация уже выполняется",
                "last_sync_task_id": group.last_sync_task_id,
            },
        )

    errors = validate_sync_group_payload(
        db,
        primary_node_id=group.primary_node_id,
        replica_node_ids=parse_replica_node_ids(group.replica_node_ids),
        exclude_group_id=group.id,
    )
    raise_if_preflight_errors(errors)

    group.sync_status = SyncStatus.pending
    group.last_sync_error = None

    task = background_task_service.enqueue_background_task(
        "node_sync_setup",
        make_group_setup_callable(group.id),
        created_by_username=admin.username,
        queued_message="Настройка HA-группы поставлена в очередь",
    )
    group.last_sync_task_id = task.id
    db.commit()

    payload = background_task_service.build_accepted_payload(
        task,
        "Настройка HA запущена в фоне (домен → полная синхронизация → проверка)",
    )
    return NodeSyncPushFullResponse(
        task_id=task.id,
        group_id=group.id,
        message=str(payload.get("message") or "Настройка HA запущена"),
        queued=bool(payload.get("queued", True)),
        status_url=payload.get("status_url"),
    )


@router.post(
    "/{group_id}/apply-shared-domain",
    response_model=NodeSyncPushFullResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_shared_domain_endpoint(
    group_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Write shared_domain → OPENVPN_HOST/WIREGUARD_HOST on all members, then doall.sh + client.sh 7."""
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")
    if group.sync_status == SyncStatus.pending:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Синхронизация уже выполняется",
                "last_sync_task_id": group.last_sync_task_id,
            },
        )

    errors = validate_sync_group_payload(
        db,
        primary_node_id=group.primary_node_id,
        replica_node_ids=parse_replica_node_ids(group.replica_node_ids),
        exclude_group_id=group.id,
    )
    raise_if_preflight_errors(errors)
    _reject_shared_domains_panel_conflict(
        effective_openvpn_domain(group),
        effective_wireguard_domain(group),
    )

    group.sync_status = SyncStatus.pending
    group.last_sync_error = None

    task = background_task_service.enqueue_background_task(
        "node_sync_shared_domain",
        make_shared_domain_callable(group.id),
        created_by_username=admin.username,
        queued_message="Применение shared domain поставлено в очередь",
    )
    group.last_sync_task_id = task.id
    db.commit()

    payload = background_task_service.build_accepted_payload(
        task,
        "Применение shared domain запущено в фоне (setup + doall.sh + client.sh 7)",
    )
    return NodeSyncPushFullResponse(
        task_id=task.id,
        group_id=group.id,
        message=str(payload.get("message") or "Применение shared domain запущено"),
        queued=bool(payload.get("queued", True)),
        status_url=payload.get("status_url"),
    )


@router.post("/{group_id}/verify", response_model=NodeSyncVerifyResponse)
def verify_sync_group_endpoint(
    group_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync group не найдена")
    result = verify_sync_group(db, group)
    return NodeSyncVerifyResponse(**result)
