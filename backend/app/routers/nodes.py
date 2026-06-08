import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import Node, NodeStatus, User
from app.schemas import (
    ActiveNodeResponse,
    MessageResponse,
    NodeCreate,
    NodeHealthResponse,
    NodeResponse,
    NodeRotateKeyResponse,
    NodeUpdate,
    NodeUpdateRequest,
    NodeUpdateResult,
    NodeUpdatesResponse,
    ResourceHistoryPoint,
    ResourceHistoryResponse,
)
from app.services.resource_metrics import VALID_PERIODS, query_history
from app.services.node_key_rotation import rotate_node_api_key
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

router = APIRouter(prefix="/nodes", tags=["nodes"])
settings = get_settings()


def _to_response(node: Node) -> NodeResponse:
    return NodeResponse(
        id=node.id,
        name=node.name,
        host=node.host,
        port=node.port,
        status=node.status,
        is_local=node.is_local,
        last_seen_at=node.last_seen_at,
        metadata=node_metadata_dict(node),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


@router.get("", response_model=list[NodeResponse])
def list_nodes(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    sync_local_node(db)
    nodes = db.query(Node).order_by(Node.is_local.desc(), Node.name).all()
    return [_to_response(n) for n in nodes]


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


@router.get("/active", response_model=ActiveNodeResponse)
def get_active(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sync_local_node(db)
    node = get_active_node(db)
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.refresh(node)
    return ActiveNodeResponse(node=_to_response(node))


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
    return ActiveNodeResponse(node=_to_response(node))


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
        antizapret=updates.get("antizapret", {}),
    )


@router.post("/{node_id}/update", response_model=NodeUpdateResult)
def apply_node_update_endpoint(
    node_id: int,
    payload: NodeUpdateRequest,
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

    meta = node_metadata_dict(node)
    adapter = get_adapter_for_node(node)
    result = adapter.apply_update(scope=payload.scope, run_doall=payload.run_doall)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(result.get("errors") or [result.get("message", "Ошибка обновления")]),
        )

    if not result.get("restarting"):
        health = check_node_health(node)
        update_node_from_health(node, health, db)
    else:
        after = result.get("after") or {}
        if after.get("antizapret_version"):
            meta["antizapret_version"] = after["antizapret_version"]
            node.node_metadata = json.dumps(meta)
            db.add(node)
            db.commit()

    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_update_apply",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node={node.name}, scope={payload.scope}",
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
