from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.access_policy import AccessPolicyService
from app.services.action_log import log_action

router = APIRouter(prefix="/client-access", tags=["client-access"])
settings = get_settings()


class BlockRequest(BaseModel):
    client_name: str
    days: int | None = Field(default=None, ge=1, le=3650)


class ExpiryRequest(BaseModel):
    client_name: str
    days: int = Field(ge=1, le=3650)
    extend: bool = False


def _service(db: Session) -> AccessPolicyService:
    return AccessPolicyService(db, antizapret_path=settings.antizapret_path)


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
    return result


@router.post("/openvpn/permanent-block")
def openvpn_perm_block(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).openvpn_permanent_block(payload.client_name, actor=user.username)
    log_action(db, action="openvpn_perm_block", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    return result


@router.post("/openvpn/unblock")
def openvpn_unblock(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).openvpn_unblock(payload.client_name, actor=user.username)
    log_action(db, action="openvpn_unblock", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
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
    return result


@router.post("/wireguard/permanent-block")
def wg_perm_block(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = _service(db).wg_permanent_block(payload.client_name, actor=user.username)
    log_action(db, action="wg_perm_block", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    return result


@router.post("/wireguard/unblock")
def wg_unblock(payload: BlockRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        result = _service(db).wg_unblock(payload.client_name, actor=user.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_action(db, action="wg_unblock", user_id=user.id, username=user.username,
               details=payload.client_name, remote_addr=request.client.host)
    return result
