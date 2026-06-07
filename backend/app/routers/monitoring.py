from datetime import datetime

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models import User
from app.schemas import MonitoringOverview
from app.services.antizapret import antizapret_service

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overview", response_model=MonitoringOverview)
def monitoring_overview(_: User = Depends(get_current_user)):
    return MonitoringOverview(
        services=antizapret_service.get_service_status(),
        openvpn_clients=antizapret_service.parse_openvpn_status(),
        wireguard_peers=antizapret_service.parse_wireguard_status(),
        server_ip=antizapret_service.get_server_ip(),
        timestamp=datetime.utcnow(),
    )
