import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.auth import require_admin
from app.config import get_settings
from app.models import User
from app.services.server_monitor import ServerMonitorService

router = APIRouter(prefix="/server-monitor", tags=["server-monitor"])
settings = get_settings()
monitor = ServerMonitorService()


@router.get("/metrics")
def get_metrics(accurate: bool = False, _: User = Depends(require_admin)):
    return monitor.get_metrics(accurate_cpu=accurate)


@router.get("/bandwidth")
def get_bandwidth(iface: str = "eth0", range_key: str = "1d", _: User = Depends(require_admin)):
    return monitor.get_bandwidth(iface, range_key)


@router.get("/interfaces")
def list_interfaces(_: User = Depends(require_admin)):
    return monitor.list_interfaces()


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
            metrics = monitor.get_metrics()
            bw = monitor.get_bandwidth(iface, "1d")
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
