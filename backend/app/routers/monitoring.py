import asyncio
import json

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
    ConnectionHistoryPoint,
    ConnectionHistoryResponse,
    DashboardSummary,
    GlobalDashboardSummary,
    MonitoringOverview,
    NocIncidentsResponse,
    PanelResourceCurrentResponse,
    PanelResourceHistoryPoint,
    PanelResourceHistoryResponse,
    ResourceHistoryPoint,
    ResourceHistoryResponse,
)
from app.services.connection_history import VALID_PERIODS as CONNECTION_VALID_PERIODS
from app.services.connection_history import query_connection_history
from app.services.monitoring_overview import (
    build_federated_monitoring_overview,
    build_global_dashboard_summary,
    build_monitoring_overview,
)
from app.services.noc_incidents import build_noc_incidents
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.wireguard_status import wireguard_peer_is_online
from app.services.node_remote_cache import (
    FEDERATED_OVERVIEW_CACHE_KEY,
    GLOBAL_DASHBOARD_CACHE_KEY,
    NODES_COMPARE_CACHE_KEY,
    get_cached_monitoring_overview,
)
from app.services.panel_resource_collector import collect_panel_metrics
from app.services.panel_resource_metrics import VALID_PERIODS as PANEL_VALID_PERIODS
from app.services.panel_resource_metrics import query_history as query_panel_history
from app.services.resource_metrics import VALID_PERIODS, query_history

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
_settings = get_settings()


def _monitoring_cache_ttl() -> int:
    return max(0, int(_settings.monitoring_overview_cache_ttl_seconds))


def _mark_cache_hit(overview: MonitoringOverview, served_from_cache: bool) -> MonitoringOverview:
    if not served_from_cache:
        return overview.model_copy(update={"served_from_cache": False})
    return overview.model_copy(update={"served_from_cache": True})


def _federated_cache_key(ha_mode: str) -> str:
    if ha_mode == "raw":
        return f"{FEDERATED_OVERVIEW_CACHE_KEY}:raw"
    return FEDERATED_OVERVIEW_CACHE_KEY


def _build_monitoring_overview(
    db: Session,
    scope: str = "node",
    *,
    ha_mode: str = "dedupe",
    bypass_cache: bool = False,
) -> MonitoringOverview:
    if scope == "all":
        ttl = 0 if bypass_cache else _monitoring_cache_ttl()
        overview, from_cache = get_cached_monitoring_overview(
            _federated_cache_key(ha_mode),
            ttl,
            lambda: build_federated_monitoring_overview(db, ha_mode=ha_mode),  # type: ignore[arg-type]
        )
        return _mark_cache_hit(overview, from_cache and not bypass_cache)
    return build_monitoring_overview(db)


@router.get("/global-summary", response_model=GlobalDashboardSummary)
def global_dashboard_summary(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        ttl = _monitoring_cache_ttl()
        overview, _from_cache = get_cached_monitoring_overview(
            GLOBAL_DASHBOARD_CACHE_KEY,
            ttl,
            lambda: build_global_dashboard_summary(db),
        )
        return overview
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сборки global dashboard: {exc}",
        ) from exc


@router.get("/nodes-compare", response_model=GlobalDashboardSummary)
def nodes_compare(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Side-by-side compare metrics for all nodes (same payload as global-summary)."""
    try:
        ttl = _monitoring_cache_ttl()
        overview, _from_cache = get_cached_monitoring_overview(
            NODES_COMPARE_CACHE_KEY,
            ttl,
            lambda: build_global_dashboard_summary(db),
        )
        return overview
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сборки сравнения узлов: {exc}",
        ) from exc


@router.get("/overview", response_model=MonitoringOverview)
def monitoring_overview(
    scope: str = Query(default="node", pattern="^(node|all)$"),
    ha_mode: str = Query(default="dedupe", pattern="^(dedupe|raw)$"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return _build_monitoring_overview(db, scope=scope, ha_mode=ha_mode)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сборки мониторинга: {exc}",
        ) from exc


@router.get("/incidents", response_model=NocIncidentsResponse)
def monitoring_incidents(
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return build_noc_incidents(db, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сборки инцидентов: {exc}",
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
    scope: str = Query(default="node", pattern="^(node|all)$"),
    ha_mode: str = Query(default="dedupe", pattern="^(dedupe|raw)$"),
):
    db = SessionLocal()
    try:
        user = _user_from_access_token(token, db)
        if user.role.value != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    finally:
        db.close()

    interval = max(5, int(_settings.monitoring_stream_interval_seconds))

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            db = SessionLocal()
            try:
                # Always fresh snapshots so client-side Mbps deltas are meaningful.
                overview = _build_monitoring_overview(
                    db, scope=scope, ha_mode=ha_mode, bypass_cache=True
                )
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
    _: User = Depends(require_admin),
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


@router.get("/connection-history", response_model=ConnectionHistoryResponse)
def connection_history(
    period: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    scope: str = Query(default="node", pattern="^(node|all)$"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if period not in CONNECTION_VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period должен быть 1h, 6h или 24h",
        )
    try:
        points, sample_count = query_connection_history(db, period=period, scope=scope)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка истории подключений: {exc}",
        ) from exc
    return ConnectionHistoryResponse(
        period=period,
        sample_count=sample_count,
        scope=scope,
        points=[ConnectionHistoryPoint(**p) for p in points],
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
    is_admin = current_user.role.value == "admin"

    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id)
    if not is_admin:
        query = query.filter(VpnConfig.owner_id == current_user.id)
    configs = query.all()

    if not is_admin:
        return DashboardSummary(
            total_configs=len(configs),
            openvpn_configs=sum(1 for c in configs if c.vpn_type == VpnType.openvpn),
            wireguard_configs=sum(1 for c in configs if c.vpn_type == VpnType.wireguard),
            connected_openvpn=0,
            connected_wireguard=0,
            active_services=0,
            total_services=0,
            server_ip="",
            node_name=node.name,
        )

    services = adapter.get_service_status()
    ovpn_clients = adapter.parse_openvpn_status()
    wg_peers = adapter.parse_wireguard_status()
    wg_active = sum(1 for p in wg_peers if wireguard_peer_is_online(p))

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
