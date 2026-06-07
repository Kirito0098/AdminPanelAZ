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
    iface = websocket.query_params.get("iface", "eth0")
    try:
        while True:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                adapter = get_active_adapter(db)
                metrics = adapter.get_server_metrics()
                bw = adapter.get_server_bandwidth(iface, "1d")
            finally:
                db.close()
            payload = {
                "cpu_percent": metrics["cpu_percent"],
                "memory_percent": metrics["memory_percent"],
                "timestamp": metrics["timestamp"],
            }
            if "error" not in bw and bw.get("rx_mbps"):
                payload["bandwidth"] = {
                    "iface": bw.get("iface"),
                    "rx_mbps_latest": bw["rx_mbps"][-1] if bw["rx_mbps"] else 0,
                    "tx_mbps_latest": bw["tx_mbps"][-1] if bw["tx_mbps"] else 0,
                    "totals": bw.get("totals"),
                }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
