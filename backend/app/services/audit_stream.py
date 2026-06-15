"""Full audit stream to HTTP collectors and syslog/SIEM."""

from __future__ import annotations

import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AppSetting, UserActionLog, WebhookDelivery

logger = logging.getLogger(__name__)

AUDIT_STREAM_KEYS = {
    "enabled": "audit_stream_enabled",
    "mode": "audit_stream_mode",
    "http_url": "audit_stream_http_url",
    "secret": "audit_stream_http_secret",
    "syslog_host": "audit_stream_syslog_host",
    "syslog_port": "audit_stream_syslog_port",
    "syslog_protocol": "audit_stream_syslog_protocol",
    "format": "audit_stream_format",
}


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value is not None else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


class AuditStreamService:
    def get_settings(self, db: Session) -> dict[str, Any]:
        return {
            "enabled": _truthy(_get_setting(db, AUDIT_STREAM_KEYS["enabled"], "false")),
            "mode": _get_setting(db, AUDIT_STREAM_KEYS["mode"], "http") or "http",
            "http_url": _get_setting(db, AUDIT_STREAM_KEYS["http_url"]),
            "secret_configured": bool(_get_setting(db, AUDIT_STREAM_KEYS["secret"])),
            "syslog_host": _get_setting(db, AUDIT_STREAM_KEYS["syslog_host"]),
            "syslog_port": int(_get_setting(db, AUDIT_STREAM_KEYS["syslog_port"], "514") or "514"),
            "syslog_protocol": _get_setting(db, AUDIT_STREAM_KEYS["syslog_protocol"], "udp") or "udp",
            "format": _get_setting(db, AUDIT_STREAM_KEYS["format"], "json") or "json",
        }

    def update_settings(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("enabled") is not None:
            _set_setting(db, AUDIT_STREAM_KEYS["enabled"], "true" if payload["enabled"] else "false")
        if payload.get("mode") is not None:
            mode = str(payload["mode"]).strip().lower()
            if mode not in {"http", "syslog", "both"}:
                raise ValueError("mode must be http, syslog, or both")
            _set_setting(db, AUDIT_STREAM_KEYS["mode"], mode)
        if payload.get("http_url") is not None:
            _set_setting(db, AUDIT_STREAM_KEYS["http_url"], str(payload["http_url"]).strip())
        if payload.get("secret") is not None:
            _set_setting(db, AUDIT_STREAM_KEYS["secret"], str(payload["secret"]))
        if payload.get("syslog_host") is not None:
            _set_setting(db, AUDIT_STREAM_KEYS["syslog_host"], str(payload["syslog_host"]).strip())
        if payload.get("syslog_port") is not None:
            _set_setting(db, AUDIT_STREAM_KEYS["syslog_port"], str(int(payload["syslog_port"])))
        if payload.get("syslog_protocol") is not None:
            protocol = str(payload["syslog_protocol"]).strip().lower()
            if protocol not in {"udp", "tcp"}:
                raise ValueError("syslog_protocol must be udp or tcp")
            _set_setting(db, AUDIT_STREAM_KEYS["syslog_protocol"], protocol)
        if payload.get("format") is not None:
            fmt = str(payload["format"]).strip().lower()
            if fmt not in {"json", "cef"}:
                raise ValueError("format must be json or cef")
            _set_setting(db, AUDIT_STREAM_KEYS["format"], fmt)
        db.commit()
        return self.get_settings(db)

    def build_payload(self, log_row: UserActionLog) -> dict[str, Any]:
        ts = log_row.created_at.isoformat() if log_row.created_at else None
        return {
            "@timestamp": ts,
            "event": log_row.action,
            "event.action": log_row.action,
            "timestamp": ts,
            "user_id": log_row.user_id,
            "user.name": log_row.username,
            "username": log_row.username,
            "details": log_row.details,
            "source.ip": log_row.remote_addr,
            "remote_addr": log_row.remote_addr,
            "log_id": log_row.id,
            "message": f"{log_row.action}: {log_row.details or ''}".strip(": "),
        }

    def format_message(self, payload: dict[str, Any], fmt: str) -> str:
        if fmt == "cef":
            action = str(payload.get("event.action") or payload.get("event") or "audit")
            src = payload.get("source.ip") or "unknown"
            user = payload.get("user.name") or "unknown"
            msg = str(payload.get("message") or action).replace("|", "\\|")
            return (
                f"CEF:0|AdminPanelAZ|AdminPanel|1.0|{action}|{msg}|5|"
                f"src={src} suser={user} msg={msg}"
            )
        return json.dumps(payload, ensure_ascii=False)

    def _enqueue(
        self,
        db: Session,
        *,
        action: str,
        payload: dict[str, Any],
        destination_type: str,
        destination: str,
        fmt: str,
    ) -> None:
        envelope = {"format": fmt, "payload": payload}
        db.add(
            WebhookDelivery(
                event_action=action,
                payload_json=json.dumps(envelope, ensure_ascii=False),
                url=destination,
                destination_type=destination_type,
                status="pending",
                attempts=0,
                next_retry_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    def dispatch_after_log(self, log_row: UserActionLog, db: Session | None = None) -> None:
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            settings = self.get_settings(db)
            if not settings["enabled"]:
                return
            mode = settings["mode"]
            payload = self.build_payload(log_row)
            fmt = settings["format"]
            if mode in {"http", "both"}:
                url = settings["http_url"].strip()
                if url:
                    self._enqueue(
                        db,
                        action=log_row.action,
                        payload=payload,
                        destination_type="http",
                        destination=url,
                        fmt=fmt,
                    )
            if mode in {"syslog", "both"}:
                host = settings["syslog_host"].strip()
                if host:
                    port = int(settings["syslog_port"] or 514)
                    protocol = settings["syslog_protocol"] or "udp"
                    destination = f"{protocol}://{host}:{port}"
                    self._enqueue(
                        db,
                        action=log_row.action,
                        payload=payload,
                        destination_type="syslog",
                        destination=destination,
                        fmt=fmt,
                    )
        except Exception:
            logger.exception("Failed to enqueue audit stream for action %s", log_row.action)
        finally:
            if own_session:
                db.close()

    def send_syslog(self, destination: str, message: str) -> tuple[bool, str | None]:
        try:
            protocol, rest = destination.split("://", 1)
            host, port_raw = rest.rsplit(":", 1)
            port = int(port_raw)
            data = message.encode("utf-8")
            if protocol == "tcp":
                with socket.create_connection((host, port), timeout=5) as sock:
                    sock.sendall(data + b"\n")
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(5)
                    sock.sendto(data, (host, port))
            return True, None
        except Exception as exc:
            return False, str(exc)

    def build_test_payload(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "@timestamp": now,
            "event": "audit_stream_test",
            "event.action": "audit_stream_test",
            "timestamp": now,
            "user_id": None,
            "user.name": "system",
            "username": "system",
            "details": "test event",
            "source.ip": "127.0.0.1",
            "remote_addr": "127.0.0.1",
            "log_id": 0,
            "message": "audit_stream_test: test event",
        }


audit_stream_service = AuditStreamService()
