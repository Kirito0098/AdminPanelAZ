import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import User
from app.models import VpnConfig, VpnType
from app.schemas import (
    DashboardSummary,
    MonitoringOverview,
    PanelResourceCurrentResponse,
    PanelResourceHistoryPoint,
    PanelResourceHistoryResponse,
    ResourceHistoryPoint,
    ResourceHistoryResponse,
)
from app.services.monitoring_overview import build_federated_monitoring_overview, build_monitoring_overview
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.panel_resource_collector import collect_panel_metrics
from app.services.panel_resource_metrics import VALID_PERIODS as PANEL_VALID_PERIODS
from app.services.panel_resource_metrics import query_history as query_panel_history
from app.services.resource_metrics import VALID_PERIODS, query_history

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
_settings = get_settings()


def _build_monitoring_overview(db: Session, scope: str = "node") -> MonitoringOverview:
    if scope == "all":
        return build_federated_monitoring_overview(db)
    return build_monitoring_overview(db)


@router.get("/overview", response_model=MonitoringOverview)
def monitoring_overview(
    scope: str = Query(default="node", pattern="^(node|all)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _build_monitoring_overview(db, scope=scope)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сборки мониторинга: {exc}",
        ) from exc


def _user_from_access_token(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный токен авторизации",
    )
    try:
        payload = jwt.decode(token, _settings.secret_key, algorithms=[_settings.algorithm])
        if payload.get("type") not in (None, "access"):
            raise credentials_exception
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


@router.get("/stream")
async def monitoring_stream(
    request: Request,
    token: str = Query(..., description="JWT access token"),
):
    db = SessionLocal()
    try:
        _user_from_access_token(token, db)
    finally:
        db.close()

    interval = max(5, int(_settings.monitoring_overview_cache_ttl_seconds))

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            db = SessionLocal()
            try:
                overview = _build_monitoring_overview(db)
                payload = overview.model_dump(mode="json")
                yield f"data: {json.dumps(payload, default=str)}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)}, default=str)}\n\n"
            finally:
                db.close()
            await asyncio.sleep(interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/resource-history", response_model=ResourceHistoryResponse)
def resource_history(
    period: str = "1d",
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period должен быть 1d, 7d или 30d",
        )
    node = get_active_node(db)
    points, sample_count = query_history(db, node.id, period)
    return ResourceHistoryResponse(
        node_id=node.id,
        node_name=node.name,
        period=period,
        sample_count=sample_count,
        points=[ResourceHistoryPoint(**p) for p in points],
    )


@router.get("/panel-resource-history", response_model=PanelResourceHistoryResponse)
def panel_resource_history(
    period: str = "1d",
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if period not in PANEL_VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period должен быть 1d, 7d или 30d",
        )
    points, sample_count = query_panel_history(db, period)
    return PanelResourceHistoryResponse(
        period=period,
        sample_count=sample_count,
        points=[PanelResourceHistoryPoint(**p) for p in points],
    )


@router.get("/panel-resource-current", response_model=PanelResourceCurrentResponse)
def panel_resource_current(_: User = Depends(require_admin)):
    return PanelResourceCurrentResponse(**collect_panel_metrics())


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)

    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id)
    if current_user.role.value != "admin":
        query = query.filter(VpnConfig.owner_id == current_user.id)
    configs = query.all()

    services = adapter.get_service_status()
    ovpn_clients = adapter.parse_openvpn_status()
    wg_peers = adapter.parse_wireguard_status()
    wg_active = sum(1 for p in wg_peers if p.latest_handshake)

    return DashboardSummary(
        total_configs=len(configs),
        openvpn_configs=sum(1 for c in configs if c.vpn_type == VpnType.openvpn),
        wireguard_configs=sum(1 for c in configs if c.vpn_type == VpnType.wireguard),
        connected_openvpn=len(ovpn_clients),
        connected_wireguard=wg_active,
        active_services=sum(1 for s in services if s.active),
        total_services=len(services),
        server_ip=adapter.get_server_ip(),
        node_name=node.name,
    )
