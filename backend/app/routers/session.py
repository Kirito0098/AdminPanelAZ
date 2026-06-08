"""Session heartbeat API (ported from AdminAntizapret /api/session-heartbeat)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.active_web_session import active_web_session_service

router = APIRouter(tags=["session"])


@router.get("/session-heartbeat")
def session_heartbeat(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session_id = active_web_session_service.get_session_id_from_request(request)
    if session_id:
        try:
            active_web_session_service.touch_active_web_session(
                db,
                current_user.username,
                request=request,
                session_id=session_id,
                force=True,
            )
        except Exception:
            db.rollback()
            return {"success": False}
    return {"success": True}
