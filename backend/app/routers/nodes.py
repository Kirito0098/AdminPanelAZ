from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import Node, NodeStatus, User
from app.schemas import (
    ActiveNodeResponse,
    MessageResponse,
    NodeAllowFirstRemoteHostResponse,
    NodeCreate,
    NodeHaContext,
    NodeHealthResponse,
    NodeMtlsDisableResponse,
    NodeMtlsEnableResponse,
    NodeMtlsStatusResponse,
    NodeRemoteHostsBody,
    NodeRemoteHostsResponse,
    NodeResponse,
    NodeRotateKeyResponse,
    NodeUpdate,
    NodeUpdateRequest,
    NodeUpdateResult,
    NodeUpdateRollRequest,
    NodeUpdatesResponse,
    GeoRoutingHintResponse,
    ProxyDestinationBody,
    ProxyMappingsResponse,
    ProxyStatusResponse,
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
    get_proxy_adapter,
    node_metadata_dict,
    purge_node_related,
    set_active_node_id,
    store_api_key,
    update_node_from_health,
    validate_node_host,
)
from app.services.action_log import log_action
from app.services.feature_guards import module_disabled_message
from app.services.feature_toggles import is_proxy_nodes_enabled
from app.services.ip_restriction import ip_restriction_service
from app.services.node_update_roll import enqueue_node_update_roll
from app.services.background_tasks import background_task_service
from app.services.geo_routing_hint import build_geo_routing_hint
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import build_ha_node_context, find_group_for_node
from app.services.openvpn_remote_hosts import (
    RemoteHostsError,
    append_host_to_allow_ips,
    hosts_to_json,
    normalize_hosts,
    parse_hosts_json,
    sync_openvpn_host_from_remotes,
)

NODE_KIND_VPN = "vpn"
NODE_KIND_PROXY = "proxy"
PROXY_DEFAULT_PORT = 9101
VPN_DEFAULT_PORT = 9100

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
        node_kind=getattr(node, "node_kind", None) or NODE_KIND_VPN,
        status=node.status,
        is_local=node.is_local,
        mtls_enabled=False if node.is_local else bool(node.mtls_enabled),
        destination_ip=getattr(node, "destination_ip", None),
        linked_vpn_node_id=getattr(node, "linked_vpn_node_id", None),
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

    kind = (payload.node_kind or NODE_KIND_VPN).strip().lower()
    if kind not in (NODE_KIND_VPN, NODE_KIND_PROXY):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="node_kind должен быть vpn или proxy",
        )
    # /api/nodes is ALWAYS_ALLOWED — enforce proxy_nodes toggle at handler level.
    if kind == NODE_KIND_PROXY and not is_proxy_nodes_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("proxy_nodes"),
        )

    if payload.port is not None:
        port = payload.port
    elif kind == NODE_KIND_PROXY:
        port = PROXY_DEFAULT_PORT
    else:
        port = VPN_DEFAULT_PORT

    linked_vpn_node_id = payload.linked_vpn_node_id
    if linked_vpn_node_id is not None:
        linked = db.query(Node).filter(Node.id == linked_vpn_node_id).first()
        if not linked or (getattr(linked, "node_kind", None) or NODE_KIND_VPN) != NODE_KIND_VPN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="linked_vpn_node_id должен ссылаться на существующий VPN-узел",
            )

    key_hash, key_encrypted = store_api_key("", payload.api_key)
    node = Node(
        name=payload.name.strip(),
        host=host,
        port=port,
        api_key_hash=key_hash,
        api_key_encrypted=key_encrypted,
        is_local=False,
        node_kind=kind,
        destination_ip=(payload.destination_ip or None),
        linked_vpn_node_id=linked_vpn_node_id,
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    # Proxy nodes must never become the active VPN node.
    if kind == NODE_KIND_VPN and not get_active_node_id(db):
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
            details=f"name={node.name}, host={node.host}, kind={kind}",
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

    group = find_group_for_node(db, node.id)
    if group:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Узел «{node.name}» входит в HA-группу «{group.name}». "
                f"Сначала расформируйте группу (Sync Groups → удалить)."
            ),
        )

    active_id = get_active_node_id(db)
    node_name = node.name
    try:
        purge_node_related(db, node.id)
        db.delete(node)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Не удалось удалить узел «{node_name}»: на него ссылаются связанные данные. "
                f"Если узел входит в HA-группу — сначала расформируйте группу "
                f"(Узлы → Группы синхронизации)."
            ),
        ) from exc

    if active_id == node_id:
        fallback = sync_local_node(db)
        if fallback:
            set_active_node_id(db, fallback.id)
        else:
            # Active node is VPN-only; never promote a proxy remote.
            other = (
                db.query(Node)
                .filter(Node.is_local.is_(False), Node.node_kind == "vpn")
                .order_by(Node.id)
                .first()
            )
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
            details=f"name={node_name}, id={node_id}",
        )
    return MessageResponse(message=f"Узел '{node_name}' удалён")


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


def _require_proxy_node(node_id: int, db: Session) -> Node:
    """Admin proxy routes: toggle on, node exists, node_kind=proxy (else 404)."""
    # /api/nodes is ALWAYS_ALLOWED — enforce proxy_nodes toggle at handler level.
    if not is_proxy_nodes_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("proxy_nodes"),
        )
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    kind = (getattr(node, "node_kind", None) or NODE_KIND_VPN).strip().lower()
    if kind != NODE_KIND_PROXY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не является прокси")
    return node


def _sync_destination_ip(node: Node, status_payload: dict, db: Session) -> None:
    dest = status_payload.get("destination_ip") if isinstance(status_payload, dict) else None
    if dest is None:
        return
    if getattr(node, "destination_ip", None) == dest:
        return
    node.destination_ip = dest
    node.updated_at = datetime.utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)


@router.get("/{node_id}/proxy/status", response_model=ProxyStatusResponse)
def get_proxy_status(
    node_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = _require_proxy_node(node_id, db)
    adapter = get_proxy_adapter(node)
    payload = adapter.proxy_status()
    return ProxyStatusResponse(
        installed=bool(payload.get("installed")),
        destination_ip=payload.get("destination_ip"),
        detail=payload.get("detail"),
    )


@router.put("/{node_id}/proxy/status", response_model=ProxyStatusResponse)
def refresh_proxy_status(
    node_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Refresh status from proxy_agent and sync cached destination_ip."""
    node = _require_proxy_node(node_id, db)
    adapter = get_proxy_adapter(node)
    payload = adapter.proxy_status()
    _sync_destination_ip(node, payload, db)
    return ProxyStatusResponse(
        installed=bool(payload.get("installed")),
        destination_ip=payload.get("destination_ip"),
        detail=payload.get("detail"),
    )


@router.put("/{node_id}/proxy/destination", response_model=ProxyStatusResponse)
def put_proxy_destination(
    node_id: int,
    payload: ProxyDestinationBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = _require_proxy_node(node_id, db)
    adapter = get_proxy_adapter(node)
    status_payload = adapter.set_destination(payload.destination_ip.strip())
    _sync_destination_ip(node, status_payload, db)
    # Always persist requested IP on success (agent may return same status shape).
    if getattr(node, "destination_ip", None) != payload.destination_ip.strip():
        node.destination_ip = payload.destination_ip.strip()
        node.updated_at = datetime.utcnow()
        db.add(node)
        db.commit()
        db.refresh(node)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="proxy_destination_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node_id={node_id} destination_ip={payload.destination_ip.strip()}",
        )
    return ProxyStatusResponse(
        installed=bool(status_payload.get("installed")),
        destination_ip=status_payload.get("destination_ip"),
        detail=status_payload.get("detail"),
    )


@router.get("/{node_id}/proxy/mappings", response_model=ProxyMappingsResponse)
def get_proxy_mappings(
    node_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = _require_proxy_node(node_id, db)
    adapter = get_proxy_adapter(node)
    payload = adapter.mappings()
    raw = payload.get("mappings") if isinstance(payload, dict) else []
    if not isinstance(raw, list):
        raw = []
    return ProxyMappingsResponse(mappings=raw)


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


@router.get("/{node_id}/remote-hosts", response_model=NodeRemoteHostsResponse)
def get_remote_hosts(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    return NodeRemoteHostsResponse(hosts=parse_hosts_json(node.openvpn_remote_hosts))


@router.put("/{node_id}/remote-hosts", response_model=NodeRemoteHostsResponse)
def put_remote_hosts(
    node_id: int,
    payload: NodeRemoteHostsBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    try:
        hosts = normalize_hosts(payload.hosts)
    except RemoteHostsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    node.openvpn_remote_hosts = hosts_to_json(hosts) if hosts else None
    node.updated_at = datetime.utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)
    warnings = sync_openvpn_host_from_remotes(lambda: get_adapter_for_node(node), hosts)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_remote_hosts_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node_id={node_id} hosts={hosts}",
        )
    return NodeRemoteHostsResponse(hosts=hosts, warnings=warnings)


@router.post(
    "/{node_id}/remote-hosts/allow-first",
    response_model=NodeAllowFirstRemoteHostResponse,
)
def allow_first_remote_host(
    node_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Append the first saved remote host to allow-ips.txt on the VPN node."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")
    hosts = parse_hosts_json(node.openvpn_remote_hosts)
    if not hosts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала задайте адреса подключения",
        )
    first = hosts[0]
    adapter = get_adapter_for_node(node)
    content = adapter.read_config_file("allow-ips.txt")
    new_content, added = append_host_to_allow_ips(content, first)
    if not added:
        return NodeAllowFirstRemoteHostResponse(added=False, host=first, detail="уже есть")

    adapter.write_config_file("allow-ips.txt", new_content)
    warnings: list[str] = []
    try:
        adapter.apply_config_changes()
    except Exception as exc:  # noqa: BLE001 — best-effort; file already written
        detail = getattr(exc, "detail", None) or str(exc)
        warnings.append(f"Файл сохранён, но doall.sh ошибка: {detail}")

    # Same HA post-save path as edit_files PUT allow_ips.
    maybe_replicate_config_files(
        db,
        node_id=node_id,
        file_keys=["allow_ips"],
        run_doall=True,
        content_overrides={"allow_ips": new_content},
    )

    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_remote_hosts_allow_first",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node_id={node_id} host={first}",
        )
    return NodeAllowFirstRemoteHostResponse(added=True, host=first, warnings=warnings)


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

    if (getattr(node, "node_kind", None) or NODE_KIND_VPN) == NODE_KIND_PROXY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Прокси-узел нельзя сделать активным для VPN",
        )

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


@router.post("/{node_id}/restart-agent", response_model=NodeUpdateResult)
def restart_node_agent_endpoint(
    node_id: int,
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
    result = adapter.restart_agent()

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Ошибка перезапуска node agent"),
        )

    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_restart_agent",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node={node.name}",
        )
    return NodeUpdateResult(
        node_id=node.id,
        success=True,
        message=result.get("message", "Перезапуск node agent запланирован"),
        restarting=bool(result.get("restarting", True)),
    )
