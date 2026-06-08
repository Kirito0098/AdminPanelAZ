"""Active browser session tracking for nightly idle restart (ported from AdminAntizapret)."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ActiveWebSession
from app.services.ip_restriction import ip_restriction_service

WEB_SESSION_ID_HEADER = "X-Web-Session-Id"

_touch_cache: dict[str, int] = {}
_touch_cache_lock = Lock()


class ActiveWebSessionService:
    def is_enabled(self) -> bool:
        return get_settings().active_web_session_tracking_enabled

    def get_ttl_and_touch_interval(self) -> tuple[int, int]:
        settings = get_settings()
        ttl = max(30, int(settings.active_web_session_ttl_seconds))
        touch = max(1, int(settings.active_web_session_touch_interval_seconds))
        return ttl, touch

    def generate_session_id(self) -> str:
        return secrets.token_hex(16)

    def get_session_id_from_request(self, request: Request) -> str:
        return (request.headers.get(WEB_SESSION_ID_HEADER) or "").strip()

    def cleanup_stale_active_web_sessions(self, db: Session, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        ttl_seconds, _ = self.get_ttl_and_touch_interval()
        cutoff = now - timedelta(seconds=max(int(ttl_seconds) * 2, 300))
        db.query(ActiveWebSession).filter(ActiveWebSession.last_seen_at < cutoff).delete(
            synchronize_session=False
        )

    def touch_active_web_session(
        self,
        db: Session,
        username: str,
        *,
        request: Request,
        session_id: str,
        force: bool = False,
    ) -> None:
        if not self.is_enabled():
            return

        username = (username or "").strip()
        session_id = (session_id or "").strip()
        if not username or not session_id:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        now_ts = int(time.time())
        _, touch_interval_seconds = self.get_ttl_and_touch_interval()

        if not force and int(touch_interval_seconds) > 0:
            with _touch_cache_lock:
                last_touch_ts = int(_touch_cache.get(session_id) or 0)
                if last_touch_ts and (now_ts - last_touch_ts) < int(touch_interval_seconds):
                    return

        remote_addr = ip_restriction_service.get_client_ip(request)
        user_agent = (request.headers.get("User-Agent") or "")[:255]

        row = db.query(ActiveWebSession).filter(ActiveWebSession.session_id == session_id).first()
        if row is None:
            db.add(
                ActiveWebSession(
                    session_id=session_id,
                    username=username,
                    remote_addr=remote_addr,
                    user_agent=user_agent,
                    created_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.username = username
            row.remote_addr = remote_addr
            row.user_agent = user_agent
            row.last_seen_at = now

        self.cleanup_stale_active_web_sessions(db, now=now)
        db.commit()

        with _touch_cache_lock:
            _touch_cache[session_id] = now_ts

    def remove_active_web_session(self, db: Session, session_id: str) -> None:
        session_id = (session_id or "").strip()
        if not session_id:
            return
        db.query(ActiveWebSession).filter(ActiveWebSession.session_id == session_id).delete(
            synchronize_session=False
        )
        db.commit()
        with _touch_cache_lock:
            _touch_cache.pop(session_id, None)

    def count_active_sessions(self, db: Session) -> int:
        if not self.is_enabled():
            return 0
        ttl_seconds, _ = self.get_ttl_and_touch_interval()
        cutoff = datetime.utcnow() - timedelta(seconds=ttl_seconds)
        return (
            db.query(ActiveWebSession)
            .filter(ActiveWebSession.last_seen_at >= cutoff)
            .count()
        )

    def cleanup_stale_for_nightly(self, db: Session) -> None:
        ttl_seconds, _ = self.get_ttl_and_touch_interval()
        stale_seconds = max(ttl_seconds * 8, 86400)
        cutoff = datetime.utcnow() - timedelta(seconds=stale_seconds)
        db.query(ActiveWebSession).filter(ActiveWebSession.last_seen_at < cutoff).delete(
            synchronize_session=False
        )
        db.commit()


active_web_session_service = ActiveWebSessionService()
