from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, TrafficSessionState, User
from app.schemas import (
    MessageResponse,
    TrafficClientRow,
    TrafficClientSessionsResponse,
    TrafficHaContext,
    TrafficNeverConnectedResponse,
    TrafficNeverConnectedRow,
    TrafficNeverConnectedSummary,
    TrafficOverview,
    TrafficSummary,
)
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node
from app.models import Node
from app.services.config_access import accessible_client_names
from app.services.traffic.chart import fetch_traffic_chart
from app.services.traffic.collector import TrafficCollectorService
from app.services.traffic.ha_aggregate import resolve_traffic_scope
from app.services.traffic.sessions import fetch_client_sessions
from app.services.traffic.maintenance import (
    TrafficMaintenanceService,
    cleanup_openvpn_status_logs_now,
    normalize_traffic_client_identity,
    normalize_traffic_protocol_scope,
)
from app.services.antizapret_settings import is_openvpn_verbose_log_enabled
from app.services.node_adapter import LocalNodeAdapter
from app.services.wireguard_status import wireguard_peer_is_online

router = APIRouter(prefix="/traffic", tags=["traffic"])
settings = get_settings()

STATUS_CLEANUP_PERIODS = {
    "none": "Выключено",
    "daily": "Ежедневно",
    "weekly": "Еженедельно",
    "monthly": "Ежемесячно",
}


class TrafficResetRequest(BaseModel):
    scope: str = "all"


class TrafficDeleteClientRequest(BaseModel):
    client_name: str = Field(..., min_length=1)


class TrafficCleanupScheduleRequest(BaseModel):
    period: str = "none"


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _db_active_traffic_client_names(db: Session, node_id: int) -> set[str]:
    rows = (
        db.query(TrafficSessionState.common_name)
        .filter(TrafficSessionState.node_id == node_id, TrafficSessionState.is_active.is_(True))
        .distinct()
        .all()
    )
    return {name for (name,) in rows if name}


def _live_active_names_for_node(db: Session, node: Node) -> set[str]:
    active_names: set[str] = set()
    try:
        adapter = get_adapter_for_node(node)
        ovpn = adapter.parse_openvpn_status()
        wg = adapter.parse_wireguard_status()
        active_names = {c.common_name for c in ovpn}
        active_names.update(
            p.client_name for p in wg if p.client_name and wireguard_peer_is_online(p)
        )
    except Exception:
        active_names = set()

    if not active_names:
        active_names = _db_active_traffic_client_names(db, node.id)

    return active_names


def _active_traffic_client_names(db: Session, node_id: int) -> set[str]:
    node = db.get(Node, node_id) or get_active_node(db)
    return _live_active_names_for_node(db, node)


def _active_names_by_node(db: Session, node_ids: list[int], *, live: bool) -> dict[int, set[str]]:
    """Resolve active client names per node for an aggregation scope."""
    result: dict[int, set[str]] = {}
    for node_id in node_ids:
        if live:
            node = db.get(Node, node_id)
            result[node_id] = (
                _live_active_names_for_node(db, node) if node else _db_active_traffic_client_names(db, node_id)
            )
        else:
            result[node_id] = _db_active_traffic_client_names(db, node_id)
    return result


def _scoped_client_names(db: Session, user: User, node_id: int) -> set[str] | None:
    return accessible_client_names(db, user, node_id=node_id)


def _filter_client_names(names: set[str], allowed: set[str] | None) -> set[str]:
    if allowed is None:
        return names
    return {name for name in names if name in allowed}


def _openvpn_verbose_log_enabled(db: Session) -> bool:
    try:
        adapter = get_active_adapter(db)
        if isinstance(adapter, LocalNodeAdapter):
            return is_openvpn_verbose_log_enabled(adapter._service.base_path / "setup")
        data = adapter._request("GET", "/traffic/setup-openvpn-log")
        return bool(data.get("enabled"))
    except Exception:
        return False


@router.get("/active-clients")
def traffic_active_clients(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    node = get_active_node(db)
    allowed = _scoped_client_names(db, current_user, node.id)
    active_names = _filter_client_names(_active_traffic_client_names(db, node.id), allowed)
    return {
        "active_clients": sorted(active_names),
        "timestamp": datetime.utcnow(),
        "node_id": node.id,
        "node_name": node.name,
    }


@router.get("/overview", response_model=TrafficOverview)
def traffic_overview(
    live: bool = Query(True, description="Запрашивать live-статус онлайн с узла"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = get_active_node(db)
    allowed = _scoped_client_names(db, current_user, node.id)
    scope = resolve_traffic_scope(db, node.id)

    active_by_node = _active_names_by_node(db, scope.node_ids, live=live)
    merged_active: set[str] = set()
    for names in active_by_node.values():
        merged_active.update(names)
    merged_active = _filter_client_names(merged_active, allowed)

    collector = TrafficCollectorService(db, node.id)
    rows, summary = collector.get_summary(
        merged_active,
        settings.traffic_db_stale_seconds,
        node_ids=scope.node_ids,
        ha_info=scope.ha_info,
        node_names=scope.node_names,
        active_by_node=active_by_node,
    )
    if allowed is not None:
        rows = [row for row in rows if row.common_name in allowed]
        summary.users_count = len(rows)
        summary.active_users_count = sum(1 for row in rows if row.is_active)
        summary.total_received = sum(row.total_received for row in rows)
        summary.total_sent = sum(row.total_sent for row in rows)
        summary.total_received_vpn = sum(row.total_received_vpn for row in rows)
        summary.total_sent_vpn = sum(row.total_sent_vpn for row in rows)
        summary.total_received_antizapret = sum(row.total_received_antizapret for row in rows)
        summary.total_sent_antizapret = sum(row.total_sent_antizapret for row in rows)

    ha_context = None
    if scope.is_ha and scope.ha_info is not None:
        ha_context = TrafficHaContext(
            sync_group_id=scope.ha_info.sync_group_id,
            group_name=scope.group_name or scope.ha_info.shared_domain,
            shared_domain=scope.ha_info.shared_domain,
            node_count=scope.ha_info.node_count,
            member_node_ids=scope.node_ids,
        )

    return TrafficOverview(
        rows=rows,
        summary=summary,
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
        ha_context=ha_context,
    )


@router.get("/deleted-clients")
def deleted_client_traffic(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = get_active_node(db)
    service = TrafficMaintenanceService(db, node.id)
    rows, summary = service.get_deleted_persisted_traffic_rows()
    return {"rows": rows, "summary": summary, "node_id": node.id, "node_name": node.name}


@router.get("/never-connected-clients", response_model=TrafficNeverConnectedResponse)
def never_connected_client_traffic(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = get_active_node(db)
    allowed = _scoped_client_names(db, current_user, node.id)
    service = TrafficMaintenanceService(db, node.id)
    rows, summary = service.get_never_connected_config_rows(allowed)
    return TrafficNeverConnectedResponse(
        rows=[TrafficNeverConnectedRow(**row) for row in rows],
        summary=TrafficNeverConnectedSummary(**summary),
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
    )


@router.get("/chart")
def traffic_chart(
    client: str = Query(...),
    range: str = Query(default="7d", alias="range"),
    protocol: str = Query(default="all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = get_active_node(db)
    allowed = _scoped_client_names(db, current_user, node.id)
    if allowed is not None and client not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    scope = resolve_traffic_scope(db, node.id)
    result = fetch_traffic_chart(db, scope.node_ids, client, range, protocol)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.get("/client-sessions", response_model=TrafficClientSessionsResponse)
def traffic_client_sessions(
    client: str = Query(..., min_length=1),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = get_active_node(db)
    allowed = _scoped_client_names(db, current_user, node.id)
    if allowed is not None and client not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    scope = resolve_traffic_scope(db, node.id)
    result = fetch_client_sessions(
        db, scope.node_ids, client, recent_limit=limit, node_names=scope.node_names
    )
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return TrafficClientSessionsResponse(
        **result,
        node_id=node.id,
        node_name=node.name,
    )


@router.post("/reset", response_model=MessageResponse)
def reset_traffic(
    payload: TrafficResetRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope = normalize_traffic_protocol_scope(payload.scope)
    node = get_active_node(db)
    adapter = get_active_adapter(db)
    service = TrafficMaintenanceService(db, node.id)
    ok, message, detail = service.reset_persisted_traffic_data(scope, adapter)
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
    return MessageResponse(message=message, detail=detail)


@router.post("/delete-deleted-client", response_model=MessageResponse)
def delete_deleted_client_traffic(
    payload: TrafficDeleteClientRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = get_active_node(db)
    service = TrafficMaintenanceService(db, node.id)
    client_identity = normalize_traffic_client_identity(payload.client_name)
    existing = service.collect_existing_config_client_names()
    if client_identity in existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"У клиента '{payload.client_name}' есть актуальный конфиг. Удаление статистики отменено.",
        )
    ok, message = service.delete_client_traffic_stats(payload.client_name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return MessageResponse(message=message)


@router.post("/cleanup-status-logs", response_model=MessageResponse)
def cleanup_status_logs_now(_: User = Depends(require_admin)):
    ok, message = cleanup_openvpn_status_logs_now()
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
    return MessageResponse(message=message)


@router.get("/cleanup-status-schedule")
def get_cleanup_status_schedule(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    period = _get_setting(db, "traffic_status_log_cleanup_period", "none")
    if period not in STATUS_CLEANUP_PERIODS:
        period = "none"
    openvpn_log_enabled = _openvpn_verbose_log_enabled(db)
    return {
        "period": period,
        "label": STATUS_CLEANUP_PERIODS[period],
        "available_periods": STATUS_CLEANUP_PERIODS,
        "openvpn_log_enabled": openvpn_log_enabled,
    }


@router.post("/cleanup-status-schedule", response_model=MessageResponse)
def set_cleanup_status_schedule(
    payload: TrafficCleanupScheduleRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    period = (payload.period or "none").strip().lower()
    if period not in STATUS_CLEANUP_PERIODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period: none, daily, weekly, monthly")
    _set_setting(db, "traffic_status_log_cleanup_period", period)
    db.commit()
    label = STATUS_CLEANUP_PERIODS[period]
    if period == "none":
        return MessageResponse(message="Расписание очистки *.log (кроме *-status.log) отключено")
    return MessageResponse(message=f"Расписание очистки *.log сохранено: {label}")
