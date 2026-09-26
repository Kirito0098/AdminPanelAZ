"""Middleware: throttled active web session touch on authenticated API requests."""

from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth import get_active_user_from_access_token
from app.database import SessionLocal
from app.services.active_web_session import WEB_SESSION_ID_HEADER, active_web_session_service
from app.services.notify_time import get_client_timezone_from_request, remember_client_timezone

logger = logging.getLogger(__name__)

_SKIP_PATHS = frozenset(
    {
        "/api/auth/refresh",
        "/api/session-heartbeat",
        "/api/health",
    }
)


def _touch_session(request: Request, token: str, session_id: str, client_tz: str | None) -> None:
    db = SessionLocal()
    try:
        user = get_active_user_from_access_token(db, token)
        if user is not None:
            if client_tz:
                remember_client_timezone(db, user, client_tz)
            if session_id:
                active_web_session_service.touch_active_web_session(
                    db,
                    user.username,
                    request=request,
                    session_id=session_id,
                    force=False,
                )
    except Exception as exc:
        db.rollback()
        logger.debug("Active session touch skipped: %s", exc)
    finally:
        db.close()


class ActiveSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path.startswith("/api/") and path not in _SKIP_PATHS:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                session_id = (request.headers.get(WEB_SESSION_ID_HEADER) or "").strip()
                client_tz = get_client_timezone_from_request(request)
                if token and (session_id or client_tz):
                    # Runs on every authenticated API request: SQLite must not block the event loop.
                    await run_in_threadpool(_touch_session, request, token, session_id, client_tz)

        return await call_next(request)
