import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import Node, NodeStatus, User
from app.schemas import (
    ActiveNodeResponse,
    MessageResponse,
    NodeCreate,
    NodeHaContext,
    NodeHealthResponse,
    NodeMtlsDisableResponse,
    NodeMtlsEnableResponse,
    NodeMtlsStatusResponse,
    NodeResponse,
    NodeRotateKeyResponse,
    NodeUpdate,
    NodeUpdateRequest,
    NodeUpdateResult,
    NodeUpdateRollRequest,
    NodeUpdatesResponse,
    GeoRoutingHintResponse,
    ResourceHistoryPoint,
    ResourceHistoryResponse,
)
from app.services.resource_metrics import VALID_PERIODS, query_history
from app.services.node_key_rotation import rotate_node_api_key
from app.services.node_mtls_certs import get_panel_mtls_status
from app.services.node_mtls_provision import disable_mtls, enable_mtls
from app.services.node_manager import (
    check_node_health,
    clear_active_node_id,
    sync_local_node,
    get_active_node,
    get_active_node_id,
    get_adapter_for_node,
    get_api_key_plain,
    node_metadata_dict,
    set_active_node_id,
    store_api_key,
    update_node_from_health,
    validate_node_host,
)
from app.services.action_log import log_action
from app.services.ip_restriction import ip_restriction_service
from app.services.node_update_roll import enqueue_node_update_roll
from app.services.background_tasks import background_task_service
from app.services.geo_routing_hint import build_geo_routing_hint
from app.services.node_sync.groups import build_ha_node_context

router = APIRouter(prefix="/nodes", tags=["nodes"])
settings = get_settings()


@router.post("/update-roll")
def rolling_node_update(
    payload: NodeUpdateRollRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        task_id = enqueue_node_update_roll(db, node_ids=payload.node_ids, actor_username=admin.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    task = background_task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось создать задачу")

    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_update_roll_queued",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"nodes={','.join(str(x) for x in payload.node_ids)}",
        )

    return background_task_service.build_accepted_payload(
        task,
        f"Rolling update: {len(payload.node_ids)} узл(ов) в очереди",
    )


def _to_response(node: Node) -> NodeResponse:
    return NodeResponse(
        id=node.id,
        name=node.name,
        host=node.host,
        port=node.port,
        status=node.status,
        is_local=node.is_local,
        mtls_enabled=False if node.is_local else bool(node.mtls_enabled),
        last_seen_at=node.last_seen_at,
        metadata=node_metadata_dict(node),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def _active_node_response(db: Session, node: Node) -> ActiveNodeResponse:
    ha_data = build_ha_node_context(db, node.id)
    return ActiveNodeResponse(
        node=_to_response(node),
        ha=NodeHaContext(**ha_data) if ha_data else None,
    )


@router.get("", response_model=list[NodeResponse])
def list_nodes(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    sync_local_node(db)
    nodes = db.query(Node).order_by(Node.is_local.desc(), Node.name).all()
    return [_to_response(n) for n in nodes]


@router.get("/geo-routing-hint", response_model=GeoRoutingHintResponse)
def geo_routing_hint(
    request: Request,
    client_ip: str | None = Query(default=None, description="Публичный IP клиента (опционально)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resolved_ip = client_ip
    if not resolved_ip and request.client:
        resolved_ip = request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        resolved_ip = forwarded.split(",")[0].strip()
    return build_geo_routing_hint(db, client_ip=resolved_ip)


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(
    payload: NodeCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    host = validate_node_host(payload.host)
    if not payload.api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API-ключ обязателен для удалённого узла")

    key_hash, key_encrypted = store_api_key("", payload.api_key)
    node = Node(
        name=payload.name.strip(),
        host=host,
        port=payload.port,
        api_key_hash=key_hash,
        api_key_encrypted=key_encrypted,
        is_local=False,
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    if not get_active_node_id(db):
        set_active_node_id(db, node.id)
        db.commit()

    health = check_node_health(node, api_key_override=payload.api_key)
    update_node_from_health(node, health, db)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_create",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"name={node.name}, host={node.host}",
        )
    return _to_response(node)


def _should_skip_live_health_check(node: Node) -> bool:
    cache_seconds = max(0, int(settings.node_active_health_cache_seconds))
    if cache_seconds <= 0 or node.status == NodeStatus.unknown:
        return False
    if not node.last_seen_at:
        return False
    age = (datetime.utcnow() - node.last_seen_at).total_seconds()
    return age < cache_seconds


@router.get("/active", response_model=ActiveNodeResponse)
def get_active(
    force_check: bool = Query(False, description="Принудительная live-проверка node agent"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_local_node(db)
    node = get_active_node(db)
    if force_check or not _should_skip_live_health_check(node):
        health = check_node_health(node)
        update_node_from_health(node, health, db)
        db.refresh(node)
    return _active_node_response(db, node)


@router.get("/mtls/status", response_model=NodeMtlsStatusResponse)
def node_mtls_status(_: User = Depends(require_admin)):
    return NodeMtlsStatusResponse(**get_panel_mtls_status())


@router.get("/{node_id}", response_model=NodeResponse)
def get_node(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    return _to_response(node)


@router.put("/{node_id}", response_model=NodeResponse)
def update_node(
    node_id: int,
    payload: NodeUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")

    if payload.name is not None:
        node.name = payload.name.strip()
    if not node.is_local:
        if payload.host is not None:
            node.host = validate_node_host(payload.host)
        if payload.port is not None:
            node.port = payload.port
        if payload.api_key is not None:
            key_hash, key_encrypted = store_api_key("", payload.api_key)
            node.api_key_hash = key_hash
            node.api_key_encrypted = key_encrypted

    db.commit()
    db.refresh(node)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"name={node.name}, id={node.id}",
        )
    return _to_response(node)


@router.delete("/{node_id}", response_model=MessageResponse)
def delete_node(
    node_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    if node.is_local:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Локальный узел нельзя удалить")

    active_id = get_active_node_id(db)
    db.delete(node)
    db.commit()

    if active_id == node_id:
        fallback = sync_local_node(db)
        if fallback:
            set_active_node_id(db, fallback.id)
        else:
            other = db.query(Node).filter(Node.is_local.is_(False)).order_by(Node.id).first()
            if other:
                set_active_node_id(db, other.id)
            else:
                clear_active_node_id(db)
        db.commit()

    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_delete",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"name={node.name}, id={node_id}",
        )
    return MessageResponse(message=f"Узел '{node.name}' удалён")


@router.post("/{node_id}/health", response_model=NodeHealthResponse)
def health_check(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")

    health = check_node_health(node)
    update_node_from_health(node, health, db)
    return NodeHealthResponse(
        node_id=node.id,
        status=node.status,
        health=health,
        last_seen_at=node.last_seen_at,
    )


@router.post("/{node_id}/enable-mtls", response_model=NodeMtlsEnableResponse)
def enable_node_mtls(
    node_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    try:
        node = enable_mtls(db, node, admin)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось включить mTLS на узле: {exc}",
        ) from exc
    return NodeMtlsEnableResponse(
        message="mTLS успешно включён",
        node_id=node.id,
        mtls_enabled=True,
    )


@router.post("/{node_id}/disable-mtls", response_model=NodeMtlsDisableResponse)
def disable_node_mtls(
    node_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    try:
        node = disable_mtls(db, node)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return NodeMtlsDisableResponse(
        message="Флаг mTLS в панели сброшен",
        node_id=node.id,
        mtls_enabled=False,
        warning=(
            "Node agent по-прежнему работает с mTLS. Для полного отключения настройте узел вручную "
            "или переустановите node agent без mTLS."
        ),
    )


@router.post("/{node_id}/rotate-key", response_model=NodeRotateKeyResponse)
def rotate_node_key(
    node_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    if node.is_local:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Локальный узел не поддерживает ротацию ключа")
    try:
        rotate_node_api_key(db, node, actor_username=admin.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось обновить ключ на узле: {exc}",
        ) from exc
    return NodeRotateKeyResponse(message="API-ключ узла успешно обновлён", node_id=node.id)


@router.post("/{node_id}/activate", response_model=ActiveNodeResponse)
def activate_node(
    node_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")

    set_active_node_id(db, node.id)
    db.commit()
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.refresh(node)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_activate",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"name={node.name}, id={node.id}",
        )
    return _active_node_response(db, node)


def _get_node_or_404(node_id: int, db: Session) -> Node:
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    return node


@router.get("/{node_id}/resource-history", response_model=ResourceHistoryResponse)
def node_resource_history(
    node_id: int,
    period: str = "1d",
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period должен быть 1d, 7d или 30d",
        )
    node = _get_node_or_404(node_id, db)
    points, sample_count = query_history(db, node.id, period)
    return ResourceHistoryResponse(
        node_id=node.id,
        node_name=node.name,
        period=period,
        sample_count=sample_count,
        points=[ResourceHistoryPoint(**p) for p in points],
    )


@router.get("/{node_id}/updates", response_model=NodeUpdatesResponse)
def check_node_updates(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = _get_node_or_404(node_id, db)
    if node.status == NodeStatus.offline:
        health = check_node_health(node)
        update_node_from_health(node, health, db)
        if node.status == NodeStatus.offline:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Узел недоступен")

    adapter = get_adapter_for_node(node)
    updates = adapter.check_updates()
    return NodeUpdatesResponse(
        node_id=node.id,
        agent=updates.get("agent", {}),
    )


@router.post("/{node_id}/update", response_model=NodeUpdateResult)
def apply_node_update_endpoint(
    node_id: int,
    _payload: NodeUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = _get_node_or_404(node_id, db)
    if node.status == NodeStatus.offline:
        health = check_node_health(node)
        update_node_from_health(node, health, db)
        if node.status == NodeStatus.offline:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Узел недоступен")

    adapter = get_adapter_for_node(node)
    result = adapter.apply_update()

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(result.get("errors") or [result.get("message", "Ошибка обновления")]),
        )

    if not result.get("restarting"):
        health = check_node_health(node)
        update_node_from_health(node, health, db)

    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_update_apply",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node={node.name}",
        )
    return NodeUpdateResult(
        node_id=node.id,
        success=True,
        message=result.get("message", "Обновление выполнено"),
        restarting=bool(result.get("restarting")),
        before=result.get("before", {}),
        after=result.get("after", {}),
        detail=result.get("detail", {}),
        errors=result.get("errors", []),
    )
