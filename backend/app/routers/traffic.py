from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import MessageResponse, TrafficOverview
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.traffic.chart import fetch_traffic_chart
from app.services.traffic.collector import TrafficCollectorService

router = APIRouter(prefix="/traffic", tags=["traffic"])
settings = get_settings()


class TrafficResetRequest(BaseModel):
    scope: str = "all"


@router.get("/overview", response_model=TrafficOverview)
def traffic_overview(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    node = get_active_node(db)
    adapter = get_active_adapter(db)

    ovpn = adapter.parse_openvpn_status()
    wg = adapter.parse_wireguard_status()
    active_names = {c.common_name for c in ovpn}
    active_names.update(p.client_name for p in wg if p.client_name)

    collector = TrafficCollectorService(db, node.id)
    rows, summary = collector.get_summary(active_names, settings.traffic_db_stale_seconds)

    return TrafficOverview(
        rows=rows,
        summary=summary,
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
    )


@router.get("/chart")
def traffic_chart(
    client: str = Query(...),
    range: str = Query(default="7d", alias="range"),
    protocol: str = Query(default="all"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = get_active_node(db)
    result = fetch_traffic_chart(db, node.id, client, range, protocol)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.post("/reset", response_model=MessageResponse)
def reset_traffic(
    payload: TrafficResetRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope = payload.scope
    if scope not in ("all", "openvpn", "wireguard"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope: all, openvpn, wireguard")

    node = get_active_node(db)
    deleted = TrafficCollectorService(db, node.id).reset_traffic(scope)
    return MessageResponse(message=f"Статистика трафика сброшена ({scope})", detail={"deleted_samples": deleted})
