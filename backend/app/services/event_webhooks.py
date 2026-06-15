"""HTTP event webhooks for UserActionLog events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppSetting, UserActionLog, WebhookDelivery
from app.services.audit_stream import AUDIT_STREAM_KEYS, audit_stream_service

logger = logging.getLogger(__name__)

WEBHOOK_SETTING_KEYS = {
    "url": "event_webhook_url",
    "secret": "event_webhook_secret",
    "enabled": "event_webhook_enabled",
    "events": "event_webhook_events",
}

DEFAULT_WEBHOOK_EVENTS = [
    "login_success",
    "login_failed",
    "config_create",
    "config_download",
    "node_create",
    "node_update_apply",
    "node_offline",
    "backup_restore",
    "security_settings_update",
]

WEBHOOK_EVENT_LABELS: dict[str, str] = {
    "login_success": "Успешный вход",
    "login_failed": "Неудачный вход",
    "config_create": "Создание клиента",
    "config_download": "Скачивание конфига",
    "node_create": "Создание узла",
    "node_update_apply": "Обновление узла",
    "node_offline": "Узел offline",
    "backup_restore": "Восстановление бэкапа",
    "security_settings_update": "Изменение безопасности",
    "user_create": "Создание пользователя",
    "user_delete": "Удаление пользователя",
    "telegram_link": "Привязка Telegram",
    "openvpn_temp_block": "Временная блокировка OVPN",
    "openvpn_perm_block": "Постоянная блокировка OVPN",
    "wg_temp_block": "Временная блокировка WG",
    "wg_perm_block": "Постоянная блокировка WG",
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


class EventWebhookService:
    def get_settings(self, db: Session) -> dict[str, Any]:
        events_raw = _get_setting(db, WEBHOOK_SETTING_KEYS["events"], "[]")
        try:
            enabled_events = json.loads(events_raw)
            if not isinstance(enabled_events, list):
                enabled_events = []
        except json.JSONDecodeError:
            enabled_events = []

        enabled_set = {str(item) for item in enabled_events}
        catalog = [
            {
                "key": key,
                "label": WEBHOOK_EVENT_LABELS.get(key, key),
                "enabled": key in enabled_set,
            }
            for key in sorted(set(DEFAULT_WEBHOOK_EVENTS) | set(WEBHOOK_EVENT_LABELS))
        ]

        return {
            "url": _get_setting(db, WEBHOOK_SETTING_KEYS["url"]),
            "secret_configured": bool(_get_setting(db, WEBHOOK_SETTING_KEYS["secret"])),
            "enabled": _get_setting(db, WEBHOOK_SETTING_KEYS["enabled"], "false").lower() in {"1", "true", "yes"},
            "events": catalog,
        }

    def update_settings(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        if "url" in payload and payload["url"] is not None:
            _set_setting(db, WEBHOOK_SETTING_KEYS["url"], str(payload["url"]).strip())
        if "secret" in payload and payload["secret"] is not None:
            _set_setting(db, WEBHOOK_SETTING_KEYS["secret"], str(payload["secret"]))
        if "enabled" in payload and payload["enabled"] is not None:
            _set_setting(db, WEBHOOK_SETTING_KEYS["enabled"], "true" if payload["enabled"] else "false")
        if payload.get("events") is not None:
            merged = self.get_settings(db)
            current = {item["key"]: item["enabled"] for item in merged["events"]}
            for item in payload["events"]:
                if isinstance(item, dict) and "key" in item:
                    current[str(item["key"])] = bool(item.get("enabled"))
            enabled_keys = [key for key, enabled in current.items() if enabled]
            _set_setting(db, WEBHOOK_SETTING_KEYS["events"], json.dumps(enabled_keys))
        db.commit()
        return self.get_settings(db)

    def _is_event_enabled(self, db: Session, action: str) -> bool:
        settings = self.get_settings(db)
        if not settings["enabled"] or not settings["url"]:
            return False
        enabled_keys = {item["key"] for item in settings["events"] if item["enabled"]}
        return action in enabled_keys

    def _sign_payload(self, secret: str, body: bytes) -> str:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def _build_payload(self, log_row: UserActionLog) -> dict[str, Any]:
        return {
            "event": log_row.action,
            "timestamp": log_row.created_at.isoformat() if log_row.created_at else None,
            "user_id": log_row.user_id,
            "username": log_row.username,
            "details": log_row.details,
            "remote_addr": log_row.remote_addr,
            "log_id": log_row.id,
        }

    def _enqueue_delivery(self, db: Session, *, action: str, payload: dict[str, Any], url: str) -> None:
        db.add(
            WebhookDelivery(
                event_action=action,
                payload_json=json.dumps(payload, ensure_ascii=False),
                url=url,
                destination_type="http",
                status="pending",
                attempts=0,
                next_retry_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    def _delivery_body_and_secret(self, db: Session, row: WebhookDelivery) -> tuple[bytes, str]:
        raw = json.loads(row.payload_json or "{}")
        if isinstance(raw, dict) and "payload" in raw and "format" in raw:
            message = audit_stream_service.format_message(raw["payload"], str(raw["format"]))
            secret = _get_setting(db, AUDIT_STREAM_KEYS["secret"])
            return message.encode("utf-8"), secret
        body = (row.payload_json or "{}").encode("utf-8")
        secret = _get_setting(db, WEBHOOK_SETTING_KEYS["secret"])
        return body, secret

    def _deliver_row(self, db: Session, row: WebhookDelivery, secret: str) -> tuple[bool, int | None, str | None]:
        if (row.destination_type or "http") == "syslog":
            raw = json.loads(row.payload_json or "{}")
            if isinstance(raw, dict) and "payload" in raw:
                message = audit_stream_service.format_message(raw["payload"], str(raw.get("format", "json")))
            else:
                message = row.payload_json or "{}"
            ok, error = audit_stream_service.send_syslog(row.url, message)
            return ok, 200 if ok else None, error
        body, row_secret = self._delivery_body_and_secret(db, row)
        return self._post_once(row.url, body, row_secret or secret)

    def dispatch_after_log(self, log_row: UserActionLog, db: Session | None = None) -> None:
        own_session = False
        if db is None:
            db = SessionLocal()
            own_session = True
        try:
            if not self._is_event_enabled(db, log_row.action):
                return
            url = _get_setting(db, WEBHOOK_SETTING_KEYS["url"]).strip()
            if not url:
                return
            payload = self._build_payload(log_row)
            self._enqueue_delivery(db, action=log_row.action, payload=payload, url=url)
        except Exception:
            logger.exception("Failed to enqueue webhook for action %s", log_row.action)
        finally:
            if own_session:
                db.close()

    def _post_once(self, url: str, body: bytes, secret: str) -> tuple[bool, int | None, str | None]:
        headers = {"Content-Type": "application/json", "User-Agent": "AdminPanelAZ-Webhook/1.0"}
        if secret:
            headers["X-Webhook-Signature"] = self._sign_payload(secret, body)
        settings = get_settings()
        try:
            with httpx.Client(timeout=settings.event_webhook_timeout_seconds) as client:
                response = client.post(url, content=body, headers=headers)
            if 200 <= response.status_code < 300:
                return True, response.status_code, None
            if response.status_code >= 500:
                return False, response.status_code, response.text[:500]
            return True, response.status_code, None
        except Exception as exc:
            return False, None, str(exc)

    def process_pending_deliveries(self, *, limit: int = 20) -> int:
        db = SessionLocal()
        processed = 0
        try:
            now = datetime.now(timezone.utc)
            rows = (
                db.query(WebhookDelivery)
                .filter(
                    WebhookDelivery.status == "pending",
                    WebhookDelivery.next_retry_at <= now,
                )
                .order_by(WebhookDelivery.created_at)
                .limit(limit)
                .all()
            )
            secret = _get_setting(db, WEBHOOK_SETTING_KEYS["secret"])
            max_attempts = max(1, int(get_settings().event_webhook_max_attempts))
            retry_interval = max(5, int(get_settings().event_webhook_retry_interval_seconds))

            for row in rows:
                ok, status_code, error = self._deliver_row(db, row, secret)
                row.attempts = int(row.attempts or 0) + 1
                row.last_status_code = status_code
                row.last_error = error
                if ok:
                    row.status = "delivered"
                    row.delivered_at = datetime.now(timezone.utc)
                elif row.attempts >= max_attempts:
                    row.status = "failed"
                else:
                    row.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=retry_interval)
                processed += 1
            if rows:
                db.commit()
            self._purge_delivered(db)
        except Exception:
            db.rollback()
            logger.exception("Webhook delivery worker failed")
        finally:
            db.close()
        return processed

    def _purge_delivered(self, db: Session, *, days: int = 7) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        (
            db.query(WebhookDelivery)
            .filter(WebhookDelivery.status == "delivered", WebhookDelivery.delivered_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()


event_webhook_service = EventWebhookService()


def run_webhook_delivery_loop(stop_event: threading.Event | None = None) -> None:
    while True:
        if stop_event and stop_event.is_set():
            return
        try:
            event_webhook_service.process_pending_deliveries()
        except Exception:
            logger.exception("Webhook loop iteration failed")
        if stop_event and stop_event.is_set():
            return
        time.sleep(max(5, int(get_settings().event_webhook_retry_interval_seconds)))
