"""AZ-AWG2 (AmneziaWG 2.0 parallel layer) admin API — health/status shell."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.awg2 import Awg2NotInstalledError
from app.services.node_manager import get_active_adapter, get_active_node

router = APIRouter(prefix="/awg2", tags=["awg2"])


def _node_meta(node) -> dict:
    return {"node_id": node.id, "node_name": node.name, "node_host": node.host}


@router.get("/health")
def awg2_health(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    data = get_active_adapter(db).get_awg2_health()
    return {**data, **_node_meta(node)}


@router.get("/status")
def awg2_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_status()
    except Awg2NotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {**data, **_node_meta(node)}
