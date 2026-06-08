from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.access_policy import AccessPolicyService
from app.services.action_log import log_action
from app.services.admin_notify import admin_notify_service
from app.services.node_manager import get_active_adapter, get_active_node, get_node_antizapret_path
from app.services.notify_time import get_client_timezone_from_request
from app.services.traffic_limit import (
    TrafficLimitExceededError,
    parse_traffic_limit_bytes,
    parse_traffic_limit_period_days,
)

router = APIRouter(prefix="/client-access", tags=["client-access"])
settings = get_settings()


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
    return AccessPolicyService(
        db,
        antizapret_path=get_node_antizapret_path(db),
        node_id=node.id,
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
    return result


@router.post("/openvpn/disconnect")
def openvpn_disconnect(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = get_active_adapter(db).disconnect_openvpn_client(payload.client_name)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "Не удалось отключить"))
    log_action(
        db,
        action="openvpn_disconnect",
        user_id=user.id,
        username=user.username,
        details=f"{payload.client_name} ({result.get('profile', '')})",
        remote_addr=request.client.host,
    )
    return result


@router.get("/wireguard/{client_name}")
def get_wg_policy(client_name: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _service(db).get_wg_policy(client_name)


@router.post("/wireguard/set-expiry")
def wg_set_expiry(payload: ExpiryRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).wg_set_expiry(payload.client_name, payload.days, extend=payload.extend, actor=user.username)
    log_action(db, action="wg_set_expiry", user_id=user.id, username=user.username,
               details=f"{payload.client_name} {payload.days}d", remote_addr=request.client.host)
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
    return result
