from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import QrDownloadAuditLog, User, UserActionLog
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/actions")
def action_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = db.query(UserActionLog).order_by(UserActionLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "username": r.username,
            "action": r.action,
            "details": r.details,
            "remote_addr": r.remote_addr,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/qr-downloads")
def qr_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = db.query(QrDownloadAuditLog).order_by(QrDownloadAuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "event_type": r.event_type,
            "actor_username": r.actor_username,
            "remote_addr": r.remote_addr,
            "details": r.details,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/connections")
def connection_snapshot(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Live connection snapshot (complements traffic page with real-time status)."""
    adapter = get_active_adapter(db)
    ovpn = [c.model_dump() for c in adapter.parse_openvpn_status()]
    wg = [p.model_dump() for p in adapter.parse_wireguard_status()]
    return {
        "openvpn_clients": ovpn,
        "wireguard_peers": wg,
        "timestamp": datetime.utcnow().isoformat(),
    }
