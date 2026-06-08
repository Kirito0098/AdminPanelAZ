import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import QrDownloadAuditLog, User, UserActionLog
from app.services.node_manager import get_active_adapter

ACTION_LOG_CSV_HEADERS = ("id", "username", "action", "details", "remote_addr", "created_at")

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


def _iter_action_log_csv(rows: list[UserActionLog]):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ACTION_LOG_CSV_HEADERS)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.username or "",
                row.action,
                row.details or "",
                row.remote_addr or "",
                row.created_at.isoformat(),
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


@router.get("/action-logs/export")
def export_action_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = db.query(UserActionLog).order_by(UserActionLog.created_at.desc()).all()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"action-logs-{stamp}.csv"
    return StreamingResponse(
        _iter_action_log_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    ovpn_clients, openvpn_data_source = adapter.get_openvpn_status_snapshot()
    ovpn = [c.model_dump() for c in ovpn_clients]
    wg = [p.model_dump() for p in adapter.parse_wireguard_status()]
    return {
        "openvpn_clients": ovpn,
        "wireguard_peers": wg,
        "openvpn_data_source": openvpn_data_source,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/openvpn-events")
def openvpn_management_events(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent OpenVPN management log lines per profile (from Unix sockets)."""
    adapter = get_active_adapter(db)
    profiles = adapter.get_openvpn_management_events()
    return {
        "profiles": profiles,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/openvpn-sockets")
def openvpn_socket_status(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """OpenVPN management socket availability (admin diagnostics)."""
    adapter = get_active_adapter(db)
    return {
        "sockets": adapter.get_openvpn_socket_status(),
        "timestamp": datetime.utcnow().isoformat(),
    }
