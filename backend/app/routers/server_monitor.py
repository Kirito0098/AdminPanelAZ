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
    return {"interfaces": monitor.list_interfaces()}


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
    try:
        while True:
            metrics = monitor.get_metrics()
            await websocket.send_text(json.dumps({
                "cpu_percent": metrics["cpu_percent"],
                "memory_percent": metrics["memory_percent"],
                "timestamp": metrics["timestamp"],
            }))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
