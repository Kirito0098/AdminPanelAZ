from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.models import VpnConfig, VpnType
from app.schemas import DashboardSummary, MonitoringOverview
from app.services.node_manager import get_active_adapter, get_active_node

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overview", response_model=MonitoringOverview)
def monitoring_overview(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return MonitoringOverview(
        services=adapter.get_service_status(),
        openvpn_clients=adapter.parse_openvpn_status(),
        wireguard_peers=adapter.parse_wireguard_status(),
        server_ip=adapter.get_server_ip(),
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
    )


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)

    query = db.query(VpnConfig)
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
