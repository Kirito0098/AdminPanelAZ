"""Session heartbeat API (ported from AdminAntizapret /api/session-heartbeat)."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import access_token_session_id, get_current_user, oauth2_scheme, require_admin
from app.database import get_db
from app.models import User
from app.schemas import StreamTicketRequest, StreamTicketResponse
from app.services.active_web_session import active_web_session_service
from app.services.stream_ticket import STREAM_TICKET_TTL, issue_stream_ticket

logger = logging.getLogger(__name__)
router = APIRouter(tags=["session"])


@router.get("/session-heartbeat")
def session_heartbeat(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    session_id = access_token_session_id(token)
    if session_id:
        if active_web_session_service.is_session_revoked(db, session_id):
            return {"success": False, "revoked": True}
        try:
            active_web_session_service.touch_active_web_session(
                db,
                current_user.username,
                request=request,
                session_id=session_id,
                force=True,
            )
        except Exception as exc:
            logger.warning("session heartbeat touch failed for %s: %s", current_user.username, exc)
            db.rollback()
            return {"success": False}
    return {"success": True}


@router.post("/stream-ticket", response_model=StreamTicketResponse)
def create_stream_ticket(payload: StreamTicketRequest, current_user: User = Depends(require_admin)):
    return StreamTicketResponse(
        ticket=issue_stream_ticket(current_user, payload.stream),
        expires_in_seconds=int(STREAM_TICKET_TTL.total_seconds()),
    )
