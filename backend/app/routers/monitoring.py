from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
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
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.panel_resource_collector import collect_panel_metrics
from app.services.panel_resource_metrics import VALID_PERIODS as PANEL_VALID_PERIODS
from app.services.panel_resource_metrics import query_history as query_panel_history
from app.services.resource_metrics import VALID_PERIODS, query_history

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overview", response_model=MonitoringOverview)
def monitoring_overview(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    ovpn_clients, openvpn_data_source = adapter.get_openvpn_status_snapshot()
    return MonitoringOverview(
        services=adapter.get_service_status(),
        openvpn_clients=ovpn_clients,
        wireguard_peers=adapter.parse_wireguard_status(),
        server_ip=adapter.get_server_ip(),
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
        openvpn_data_source=openvpn_data_source,
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
