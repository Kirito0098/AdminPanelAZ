"""Middleware: throttled active web session touch on authenticated API requests."""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth import decode_access_token_username
from app.database import SessionLocal
from app.services.active_web_session import WEB_SESSION_ID_HEADER, active_web_session_service

logger = logging.getLogger(__name__)

_SKIP_PATHS = frozenset(
    {
        "/api/auth/refresh",
        "/api/session-heartbeat",
        "/api/health",
    }
)


class ActiveSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path.startswith("/api/") and path not in _SKIP_PATHS:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                username = decode_access_token_username(token)
                session_id = (request.headers.get(WEB_SESSION_ID_HEADER) or "").strip()
                if username and session_id:
                    db = SessionLocal()
                    try:
                        active_web_session_service.touch_active_web_session(
                            db,
                            username,
                            request=request,
                            session_id=session_id,
                            force=False,
                        )
                    except Exception as exc:
                        db.rollback()
                        logger.debug("Active session touch skipped: %s", exc)
                    finally:
                        db.close()

        return await call_next(request)
