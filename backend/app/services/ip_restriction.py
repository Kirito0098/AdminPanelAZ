"""IP restriction, scanner detection, and dwell tracking (ported from AdminAntizapret)."""

from __future__ import annotations

import ipaddress
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.panel_paths import get_ip_blocked_paths, with_access_path
from app.services.scanner_firewall_store import scanner_firewall_store
from app.services.security import SecurityService

settings = get_settings()
LOGIN_ATTEMPTS: dict[str, dict[str, Any]] = {}
LOGIN_LOCK = threading.Lock()


class IpRestrictionService:
    def __init__(self):
        self._scanner_lock = threading.Lock()
        self._firewall = scanner_firewall_store
        self._security = SecurityService()
        self.scanner_window_seconds = 60
        self.block_ip_blocked_dwell = True
        self.ip_blocked_dwell_seconds = 120

    def _normalize_remote_ip(self, remote_ip: str) -> str:
        ip = (remote_ip or "").strip()
        if ip.startswith("::ffff:"):
            ip = ip[7:]
        return ip

    def _remote_is_trusted_proxy(self, remote_ip: str) -> bool:
        from app.config import get_settings

        normalized = self._normalize_remote_ip(remote_ip)
        if not normalized:
            return False
        return normalized in set(get_settings().trusted_proxy_ip_list)

    def get_client_ip(self, request) -> str:
        remote_ip = (request.client.host if request.client else "") or ""
        remote_ip = self._normalize_remote_ip(remote_ip)
        if self._remote_is_trusted_proxy(remote_ip):
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip() or remote_ip
        return remote_ip

    def _normalize_ip(self, ip_str: str) -> str | None:
        ip_str = (ip_str or "").strip()
        if not ip_str:
            return None
        try:
            return str(ipaddress.ip_address(ip_str))
        except ValueError:
            return None

    def is_ip_allowed(self, db: Session, client_ip: str) -> bool:
        return self._security.is_ip_allowed(db, client_ip)

    def get_settings(self, db: Session) -> dict:
        return self._security.get_settings(db)

    def _scanner_runtime_settings(self, db: Session) -> dict:
        settings = self.get_settings(db)
        return {
            "scanner_window_seconds": max(
                10,
                min(3600, int(settings.get("scanner_window_seconds") or self.scanner_window_seconds)),
            ),
            "block_ip_blocked_dwell": bool(
                settings.get("block_ip_blocked_dwell", self.block_ip_blocked_dwell)
            ),
            "ip_blocked_dwell_seconds": max(
                30,
                min(3600, int(settings.get("ip_blocked_dwell_seconds") or self.ip_blocked_dwell_seconds)),
            ),
        }

    def is_scanner_banned(self, db: Session, client_ip: str) -> bool:
        if self.is_ip_allowed(db, client_ip):
            return False
        ip_key = self._normalize_ip(client_ip)
        return bool(ip_key and self._firewall.is_banned(ip_key))

    def should_hard_deny(self, db: Session, client_ip: str) -> bool:
        settings = self.get_settings(db)
        if not settings["ip_restriction_enabled"]:
            return False
        if self.is_ip_allowed(db, client_ip):
            return False
        return self.is_scanner_banned(db, client_ip)

    def should_count_denied_access(self, path: str) -> bool:
        blocked_paths = get_ip_blocked_paths(settings)
        assets_prefix = f"{with_access_path(settings, '/assets')}"
        if path in blocked_paths or path.startswith(f"{assets_prefix}/") or path == assets_prefix:
            return False
        return True

    def record_denied_access(self, db: Session, client_ip: str) -> bool:
        settings = self.get_settings(db)
        if not settings.get("block_scanners"):
            return False
        scanner_settings = self._scanner_runtime_settings(db)
        ip_key = self._normalize_ip(client_ip)
        if not ip_key or self._firewall.is_in_unban_grace(ip_key):
            return False
        now = time.time()
        with self._scanner_lock:
            if self._firewall.is_banned(ip_key, now=now):
                return True
            attempt_count = self._firewall.record_attempt(
                ip_key,
                scanner_settings["scanner_window_seconds"],
                now=now,
            )
            if attempt_count >= int(settings.get("scanner_max_attempts") or 5):
                ban_info = self._firewall.register_ban(
                    ip_key,
                    reason="rate_limit",
                    short_ban_seconds=int(settings.get("scanner_ban_seconds") or 3600),
                    now=now,
                )
                return ban_info is not None
        return False

    def touch_ip_blocked_presence(self, db: Session, client_ip: str) -> dict:
        settings = self.get_settings(db)
        scanner_settings = self._scanner_runtime_settings(db)
        if not settings.get("ip_restriction_enabled") or not scanner_settings["block_ip_blocked_dwell"]:
            return {"banned": False, "tracking": False}
        ip_key = self._normalize_ip(client_ip)
        if not ip_key:
            return {"banned": False, "tracking": False}
        now = time.time()
        with self._scanner_lock:
            if self._firewall.is_banned(ip_key, now=now):
                ban_until = self._firewall.get_ban_until(ip_key)
                return {
                    "banned": True,
                    "tracking": True,
                    "ban_remaining_seconds": max(0, int(ban_until - now)),
                    "server_block": True,
                }
            first_seen = self._firewall.touch_ip_blocked(ip_key, now=now)
            if first_seen is None:
                return {"banned": False, "tracking": False}
            if self._firewall.is_in_unban_grace(ip_key, now=now):
                return {
                    "banned": False,
                    "tracking": True,
                    "grace": True,
                    "elapsed_seconds": int(now - first_seen),
                    "dwell_seconds": scanner_settings["ip_blocked_dwell_seconds"],
                }
            elapsed = now - first_seen
            limit = scanner_settings["ip_blocked_dwell_seconds"]
            if elapsed >= limit:
                ban_info = self._firewall.register_ban(
                    ip_key,
                    reason="ip_blocked_dwell",
                    short_ban_seconds=int(settings.get("scanner_ban_seconds") or 3600),
                    now=now,
                )
                return {
                    "banned": True,
                    "tracking": True,
                    "dwell_exceeded": True,
                    "dwell_seconds": limit,
                    "server_block": True,
                    "long_term": bool(ban_info and ban_info.get("long_term")),
                }
            return {
                "banned": False,
                "tracking": True,
                "elapsed_seconds": int(elapsed),
                "dwell_seconds": limit,
                "remaining_seconds": max(0, int(limit - elapsed)),
            }

    def get_active_bans(self) -> list[dict]:
        return self._firewall.get_active_bans()

    def unban_ip(self, ip: str) -> bool:
        with self._scanner_lock:
            return self._firewall.unban_ip(ip, clear_strikes=True)

    def clear_all_bans(self) -> None:
        with self._scanner_lock:
            self._firewall.clear_all()

    def sync_firewall(self) -> None:
        self._firewall.sync_firewall_from_store()

    def sync_whitelist_port_firewall(self, db: Session) -> bool:
        return self._security.sync_whitelist_port_firewall(db)

    def record_login_attempt(self, client_ip: str, success: bool) -> int:
        with LOGIN_LOCK:
            entry = LOGIN_ATTEMPTS.setdefault(client_ip, {"count": 0, "last": 0})
            if success:
                entry["count"] = 0
                return 0
            entry["count"] = int(entry.get("count") or 0) + 1
            entry["last"] = time.time()
            return entry["count"]

    def login_needs_captcha(self, client_ip: str) -> bool:
        with LOGIN_LOCK:
            entry = LOGIN_ATTEMPTS.get(client_ip) or {}
            return int(entry.get("count") or 0) > 2


ip_restriction_service = IpRestrictionService()
