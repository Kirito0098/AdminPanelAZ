from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Node, NodeStatus, User
from app.schemas import (
    ActiveNodeResponse,
    MessageResponse,
    NodeCreate,
    NodeHealthResponse,
    NodeResponse,
    NodeUpdate,
)
from app.services.node_manager import (
    check_node_health,
    ensure_local_node,
    get_active_node,
    get_active_node_id,
    get_api_key_plain,
    node_metadata_dict,
    set_active_node_id,
    store_api_key,
    update_node_from_health,
    validate_node_host,
)

router = APIRouter(prefix="/nodes", tags=["nodes"])


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
    ensure_local_node(db)
    nodes = db.query(Node).order_by(Node.is_local.desc(), Node.name).all()
    return [_to_response(n) for n in nodes]


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
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

    health = check_node_health(node, api_key_override=payload.api_key)
    update_node_from_health(node, health, db)
    return _to_response(node)


@router.get("/active", response_model=ActiveNodeResponse)
def get_active(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_local_node(db)
    node = get_active_node(db)
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
    _: User = Depends(require_admin),
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
    return _to_response(node)


@router.delete("/{node_id}", response_model=MessageResponse)
def delete_node(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    if node.is_local:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Локальный узел нельзя удалить")

    active_id = get_active_node_id(db)
    db.delete(node)
    db.commit()

    if active_id == node_id:
        local = ensure_local_node(db)
        set_active_node_id(db, local.id)
        db.commit()

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


@router.post("/{node_id}/activate", response_model=ActiveNodeResponse)
def activate_node(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")

    set_active_node_id(db, node.id)
    db.commit()
    db.refresh(node)
    return ActiveNodeResponse(node=_to_response(node))
