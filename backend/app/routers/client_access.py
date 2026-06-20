import logging
import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import Node, User, VpnType
from app.schemas import NodeDefaultPolicyResponse, NodeDefaultPolicyUpdate, NodePolicySummary
from app.services.access_policy import (
    AccessPolicyService,
    build_policy_summary_by_node,
    clear_cooldown_ban,
    get_node_default_policy,
    register_cooldown_ban,
    set_node_default_policy,
)
from app.services.action_log import log_action
from app.services.admin_notify import admin_notify_service
from app.services.node_manager import (
    get_active_adapter,
    get_active_node,
    get_adapter_for_node,
    get_node_antizapret_path,
    node_metadata_dict,
)
from app.services.node_sync.groups import require_ha_primary_for_client_ops, require_ha_primary_node
from app.services.node_sync.client_ops_sync import maybe_replicate_openvpn_disconnect
from app.services.node_sync.policy_sync import (
    PolicyOp,
    maybe_replicate_node_default_policy,
    maybe_replicate_policy_op,
)
from app.services.notify_time import get_client_timezone_from_request
from app.services.traffic_limit import (
    TrafficLimitExceededError,
    parse_traffic_limit_bytes,
    parse_traffic_limit_period_days,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client-access", tags=["client-access"])
settings = get_settings()

# When kicking an OpenVPN session we briefly keep the client banned so its
# automatic reconnect fails (the VPN app shows an error) instead of silently
# re-establishing the tunnel. The ban is lifted automatically afterwards.
DISCONNECT_COOLDOWN_SECONDS = max(
    0, int(os.environ.get("OPENVPN_DISCONNECT_COOLDOWN_SECONDS", "15"))
)


def _node_antizapret_path(node: Node) -> Path:
    meta = node_metadata_dict(node)
    raw = meta.get("antizapret_path")
    return Path(str(raw)) if raw else settings.antizapret_path


def _schedule_disconnect_cooldown_release(node_id: int, client_name: str) -> None:
    """Lift the transient disconnect ban after the cooldown window."""

    def _worker() -> None:
        time.sleep(DISCONNECT_COOLDOWN_SECONDS)
        clear_cooldown_ban(node_id, client_name)
        db = SessionLocal()
        try:
            node = db.get(Node, node_id)
            if node is None:
                return
            svc = AccessPolicyService(
                db,
                antizapret_path=_node_antizapret_path(node),
                node_id=node.id,
                node_name=node.name,
                adapter=get_adapter_for_node(node),
            )
            svc.reconcile_openvpn(client_name)
        except Exception:
            logger.exception("disconnect cooldown release failed for %s", client_name)
        finally:
            db.close()

    threading.Thread(
        target=_worker, name=f"ovpn-cooldown-{client_name}", daemon=True
    ).start()


class BlockRequest(BaseModel):
    client_name: str
    days: int | None = Field(default=None, ge=1, le=3650)


class ExpiryRequest(BaseModel):
    client_name: str
    days: int = Field(ge=1, le=3650)
    extend: bool = False


class TrafficLimitRequest(BaseModel):
    client_name: str
    limit_value: float = Field(gt=0)
    limit_unit: str = "MB"
    limit_period_days: int | None = Field(default=None)


def _service(db: Session) -> AccessPolicyService:
    node = get_active_node(db)
    require_ha_primary_for_client_ops(db, node=node)
    return AccessPolicyService(
        db,
        antizapret_path=get_node_antizapret_path(db),
        node_id=node.id,
        node_name=node.name,
        adapter=get_active_adapter(db),
    )


def _client_ban_details(
    action: str,
    *,
    days: int | None = None,
    block_until: str | None = None,
) -> str:
    parts = [f"action={action}"]
    if days is not None:
        parts.append(f"days={days}")
    if block_until:
        parts.append(f"block_until={block_until}")
    return " ".join(parts)


def _replicate_policy_after_success(
    db: Session,
    *,
    client_name: str,
    vpn_type: VpnType,
    op: PolicyOp,
    actor: str,
    **kwargs,
) -> None:
    node = get_active_node(db)
    maybe_replicate_policy_op(
        db,
        node_id=node.id,
        client_name=client_name,
        vpn_type=vpn_type,
        op=op,
        actor=actor,
        **kwargs,
    )


def _notify_client_ban(
    db: Session,
    request: Request,
    user: User,
    *,
    client_name: str,
    target_type: str,
    action: str,
    days: int | None = None,
    block_until: str | None = None,
) -> None:
    node = get_active_node(db)
    admin_notify_service.send_client_ban(
        db,
        actor_username=user.username,
        target_name=client_name,
        target_type=target_type,
        details=_client_ban_details(action, days=days, block_until=block_until),
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )


@router.get("/policies")
def list_policies(
    clients: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    names = [c.strip() for c in clients.split(",") if c.strip()] if clients else []
    svc = _service(db)
    if not names:
        return {}
    return svc.get_all_policies(names)


@router.get("/policy-summary-by-node", response_model=list[NodePolicySummary])
def policy_summary_by_node(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return build_policy_summary_by_node(db)


@router.get("/node-defaults/{node_id}", response_model=NodeDefaultPolicyResponse)
def get_node_defaults(
    node_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        return get_node_default_policy(db, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/node-defaults/{node_id}", response_model=NodeDefaultPolicyResponse)
def update_node_defaults(
    node_id: int,
    payload: NodeDefaultPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    require_ha_primary_node(db, node_id)
    try:
        result = set_node_default_policy(
            db,
            node_id,
            route_mode=payload.route_mode,
            route_clear=payload.route_clear,
            openvpn_limit_value=payload.openvpn_limit_value,
            openvpn_limit_unit=payload.openvpn_limit_unit,
            openvpn_limit_period_days=payload.openvpn_limit_period_days,
            openvpn_clear_limit=payload.openvpn_clear_limit,
            wireguard_limit_value=payload.wireguard_limit_value,
            wireguard_limit_unit=payload.wireguard_limit_unit,
            wireguard_limit_period_days=payload.wireguard_limit_period_days,
            wireguard_clear_limit=payload.wireguard_clear_limit,
            actor=user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    log_action(
        db,
        action="node_default_policy_update",
        user_id=user.id,
        username=user.username,
        details=f"node_id={node_id}",
        remote_addr=request.client.host,
    )
    maybe_replicate_node_default_policy(db, node_id=node_id)
    return result


@router.get("/openvpn/{client_name}")
def get_openvpn_policy(client_name: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _service(db).get_openvpn_policy(client_name)


@router.post("/openvpn/temp-block")
def openvpn_temp_block(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if not payload.days:
        raise HTTPException(status_code=400, detail="Укажите срок блокировки")
    result = _service(db).openvpn_temp_block(payload.client_name, payload.days, actor=user.username)
    log_action(db, action="openvpn_temp_block", user_id=user.id, username=user.username,
               details=f"{payload.client_name} {payload.days}d", remote_addr=request.client.host)
    _notify_client_ban(
        db,
        request,
        user,
        client_name=payload.client_name,
        target_type="openvpn",
        action="temp_block",
        days=payload.days,
        block_until=result.get("block_until"),
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.openvpn,
        op="block_temp",
        actor=user.username,
        days=payload.days,
    )
    return result


@router.post("/openvpn/permanent-block")
def openvpn_perm_block(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).openvpn_permanent_block(payload.client_name, actor=user.username)
    log_action(db, action="openvpn_perm_block", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    _notify_client_ban(
        db,
        request,
        user,
        client_name=payload.client_name,
        target_type="openvpn",
        action="permanent_block",
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.openvpn,
        op="block_permanent",
        actor=user.username,
    )
    return result


@router.post("/openvpn/unblock")
def openvpn_unblock(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        result = _service(db).openvpn_unblock(payload.client_name, actor=user.username)
    except TrafficLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "error_code": exc.error_code},
        ) from exc
    log_action(db, action="openvpn_unblock", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    _notify_client_ban(
        db,
        request,
        user,
        client_name=payload.client_name,
        target_type="openvpn",
        action="unblock",
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.openvpn,
        op="unblock",
        actor=user.username,
    )
    return result


@router.post("/openvpn/disconnect")
def openvpn_disconnect(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    node = get_active_node(db)
    client_name = payload.client_name
    svc = _service(db)

    # Briefly ban the client so its automatic reconnect is rejected (VPN app
    # shows an error) instead of silently re-establishing the tunnel.
    cooldown = DISCONNECT_COOLDOWN_SECONDS
    if cooldown > 0:
        register_cooldown_ban(node.id, client_name, cooldown)
        svc.reconcile_openvpn(client_name)

    try:
        result = get_active_adapter(db).disconnect_openvpn_client(client_name)
    except Exception:
        if cooldown > 0:
            clear_cooldown_ban(node.id, client_name)
            svc.reconcile_openvpn(client_name)
        raise

    if not result.get("success"):
        if cooldown > 0:
            clear_cooldown_ban(node.id, client_name)
            svc.reconcile_openvpn(client_name)
        raise HTTPException(status_code=404, detail=result.get("message", "Не удалось отключить"))

    log_action(
        db,
        action="openvpn_disconnect",
        user_id=user.id,
        username=user.username,
        details=f"{client_name} ({result.get('profile', '')}) cooldown={cooldown}s",
        remote_addr=request.client.host,
    )
    maybe_replicate_openvpn_disconnect(db, node_id=node.id, client_name=client_name)
    if cooldown > 0:
        _schedule_disconnect_cooldown_release(node.id, client_name)
        result["cooldown_seconds"] = cooldown
    return result


@router.get("/wireguard/{client_name}")
def get_wg_policy(client_name: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _service(db).get_wg_policy(client_name)


@router.post("/wireguard/set-expiry")
def wg_set_expiry(payload: ExpiryRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).wg_set_expiry(payload.client_name, payload.days, extend=payload.extend, actor=user.username)
    log_action(db, action="wg_set_expiry", user_id=user.id, username=user.username,
               details=f"{payload.client_name} {payload.days}d", remote_addr=request.client.host)
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.wireguard,
        op="set_wg_expiry",
        actor=user.username,
        days=payload.days,
        extend=payload.extend,
    )
    return result


@router.post("/wireguard/temp-block")
def wg_temp_block(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if not payload.days:
        raise HTTPException(status_code=400, detail="Укажите срок блокировки")
    result = _service(db).wg_temp_block(payload.client_name, payload.days, actor=user.username)
    log_action(db, action="wg_temp_block", user_id=user.id, username=user.username,
               details=f"{payload.client_name} {payload.days}d", remote_addr=request.client.host)
    _notify_client_ban(
        db,
        request,
        user,
        client_name=payload.client_name,
        target_type="wireguard",
        action="temp_block",
        days=payload.days,
        block_until=result.get("block_until"),
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.wireguard,
        op="block_temp",
        actor=user.username,
        days=payload.days,
    )
    return result


@router.post("/wireguard/permanent-block")
def wg_perm_block(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).wg_permanent_block(payload.client_name, actor=user.username)
    log_action(db, action="wg_perm_block", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    _notify_client_ban(
        db,
        request,
        user,
        client_name=payload.client_name,
        target_type="wireguard",
        action="permanent_block",
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.wireguard,
        op="block_permanent",
        actor=user.username,
    )
    return result


@router.post("/wireguard/unblock")
def wg_unblock(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        result = _service(db).wg_unblock(payload.client_name, actor=user.username)
    except TrafficLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "error_code": exc.error_code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_action(db, action="wg_unblock", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    _notify_client_ban(
        db,
        request,
        user,
        client_name=payload.client_name,
        target_type="wireguard",
        action="unblock",
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.wireguard,
        op="unblock",
        actor=user.username,
    )
    return result


@router.post("/openvpn/set-traffic-limit")
def openvpn_set_traffic_limit(
    payload: TrafficLimitRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        limit_bytes = parse_traffic_limit_bytes(payload.limit_value, payload.limit_unit)
        period_days = parse_traffic_limit_period_days(payload.limit_period_days)
        result = _service(db).openvpn_set_traffic_limit(
            payload.client_name,
            limit_bytes,
            period_days=period_days,
            actor=user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_action(
        db,
        action="openvpn_traffic_limit_set",
        user_id=user.id,
        username=user.username,
        details=f"{payload.client_name} {payload.limit_value}{payload.limit_unit}",
        remote_addr=request.client.host,
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.openvpn,
        op="set_traffic_limit",
        actor=user.username,
        limit_bytes=limit_bytes,
        period_days=period_days,
    )
    return result


@router.post("/openvpn/clear-traffic-limit")
def openvpn_clear_traffic_limit(
    payload: BlockRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = _service(db).openvpn_clear_traffic_limit(payload.client_name, actor=user.username)
    log_action(
        db,
        action="openvpn_traffic_limit_clear",
        user_id=user.id,
        username=user.username,
        details=payload.client_name,
        remote_addr=request.client.host,
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.openvpn,
        op="clear_traffic_limit",
        actor=user.username,
    )
    return result


@router.post("/wireguard/set-traffic-limit")
def wg_set_traffic_limit(
    payload: TrafficLimitRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        limit_bytes = parse_traffic_limit_bytes(payload.limit_value, payload.limit_unit)
        period_days = parse_traffic_limit_period_days(payload.limit_period_days)
        result = _service(db).wg_set_traffic_limit(
            payload.client_name,
            limit_bytes,
            period_days=period_days,
            actor=user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_action(
        db,
        action="wg_traffic_limit_set",
        user_id=user.id,
        username=user.username,
        details=f"{payload.client_name} {payload.limit_value}{payload.limit_unit}",
        remote_addr=request.client.host,
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.wireguard,
        op="set_traffic_limit",
        actor=user.username,
        limit_bytes=limit_bytes,
        period_days=period_days,
    )
    return result


@router.post("/wireguard/clear-traffic-limit")
def wg_clear_traffic_limit(
    payload: BlockRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = _service(db).wg_clear_traffic_limit(payload.client_name, actor=user.username)
    log_action(
        db,
        action="wg_traffic_limit_clear",
        user_id=user.id,
        username=user.username,
        details=payload.client_name,
        remote_addr=request.client.host,
    )
    _replicate_policy_after_success(
        db,
        client_name=payload.client_name,
        vpn_type=VpnType.wireguard,
        op="clear_traffic_limit",
        actor=user.username,
    )
    return result
