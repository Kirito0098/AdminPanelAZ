import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.node_manager import get_active_adapter, get_active_node

router = APIRouter(prefix="/server-monitor", tags=["server-monitor"])
settings = get_settings()

# Live RX/TX via psutil sample — not full vnstat history (was ~2–10s of subprocess work).
_WS_THROUGHPUT_INTERVAL_S = 0.35
_WS_TICK_SLEEP_S = 2.0


def _is_server_monitor_enabled() -> bool:
    """Runtime gate — HTTP middleware does not cover WebSockets."""
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("server_monitor")


@router.get("/metrics")
def get_metrics(accurate: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_server_metrics(accurate_cpu=accurate)
    data["node_id"] = node.id
    data["node_name"] = node.name
    return data


@router.get("/bandwidth")
def get_bandwidth(
    iface: str = "eth0",
    range_key: str = "1d",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_server_bandwidth(iface, range_key)
    data["node_id"] = node.id
    data["node_name"] = node.name
    return data


@router.get("/interfaces")
def list_interfaces(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.list_server_interfaces()
    data["node_id"] = node.id
    data["node_name"] = node.name
    return data


@router.websocket("/ws")
async def monitor_ws(websocket: WebSocket):
    await websocket.accept()
    if not _is_server_monitor_enabled():
        await websocket.close(code=1008)
        return
    token = websocket.query_params.get("token", "")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        if not username:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return
    iface = (websocket.query_params.get("iface") or "eth0").strip() or "eth0"
    try:
        while True:
            if not _is_server_monitor_enabled():
                await websocket.close(code=1008)
                return

            from app.database import SessionLocal

            db = SessionLocal()
            try:
                adapter = get_active_adapter(db)
                metrics = adapter.get_server_metrics()
                live = adapter.get_server_live_throughput(
                    interval=_WS_THROUGHPUT_INTERVAL_S,
                    max_interfaces=1,
                    interface_names=[iface],
                )
            finally:
                db.close()

            payload = {
                "cpu_percent": metrics["cpu_percent"],
                "memory_percent": metrics["memory_percent"],
                "timestamp": metrics["timestamp"],
            }
            rows = live.get("interfaces") or []
            row = next((r for r in rows if r.get("name") == iface), rows[0] if rows else None)
            if row is not None:
                payload["bandwidth"] = {
                    "iface": row.get("name") or iface,
                    "rx_mbps_latest": float(row.get("rx_mbps") or 0),
                    "tx_mbps_latest": float(row.get("tx_mbps") or 0),
                    "live": True,
                }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(_WS_TICK_SLEEP_S)
    except WebSocketDisconnect:
        pass
