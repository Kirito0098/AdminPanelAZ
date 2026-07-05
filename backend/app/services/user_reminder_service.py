"""Self-service user reminders: cert expiry, traffic limit, temp block."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from pathlib import Path

from app.config import get_settings
from app.models import Node, User, VpnConfig, VpnType
from app.routers.maintenance import _get_setting
from app.services.access_policy import AccessPolicyService
from app.services.admin_notify import admin_notify_service
from app.services.feature_guards import get_feature_service
from app.services.node_manager import get_adapter_for_node, node_metadata_dict
from app.services.self_service import record_reminder_sent, reminder_recently_sent, self_service_reminder_enabled
from app.services.telegram import send_tg_message
from app.services.traffic_limit import human_bytes

logger = logging.getLogger(__name__)

REMINDER_CERT = "cert_expiry"
REMINDER_TRAFFIC = "traffic_limit"
REMINDER_TEMP_BLOCK = "temp_block"

OWNER_EVENT_MAP = {
    REMINDER_CERT: "cert_expiry_reminder",
    REMINDER_TRAFFIC: "traffic_limit_reminder",
    REMINDER_TEMP_BLOCK: "temp_block_reminder",
}

ADMIN_EVENT_MAP = {
    REMINDER_CERT: "user_cert_expiry_reminder",
    REMINDER_TRAFFIC: "user_traffic_limit_reminder",
    REMINDER_TEMP_BLOCK: "user_temp_block_reminder",
}


def _cert_threshold() -> int:
    return max(1, int(get_settings().self_service_reminder_cert_days_threshold))


def _traffic_warning_percent() -> int:
    return max(50, min(99, int(get_settings().self_service_traffic_warning_percent)))


def _traffic_warning(limit_bytes: int | None, consumed_bytes: int | None) -> bool:
    if not limit_bytes or limit_bytes <= 0:
        return False
    consumed = int(consumed_bytes or 0)
    return consumed >= int(limit_bytes * _traffic_warning_percent() / 100)


def _build_owner_message(reminder_type: str, config: VpnConfig, details: str) -> str:
    from app.services.admin_notify import (
        _format_notify_card,
        _fmt_when,
        _line_code,
        _line_text,
    )
    from app.services.notify_time import format_notify_when

    when = _fmt_when(format_notify_when(None))
    titles = {
        REMINDER_CERT: "⚠️ <b>Сертификат скоро истечёт</b>",
        REMINDER_TRAFFIC: "📊 <b>Лимит трафика</b>",
        REMINDER_TEMP_BLOCK: "⛔ <b>Временная блокировка</b>",
    }
    return _format_notify_card(
        titles[reminder_type],
        when,
        detail_lines=[
            _line_code("📁", "Клиент", config.client_name),
            _line_text("📋", "Детали", details),
        ],
    )


def _send_owner_reminder(
    db: Session,
    owner: User,
    reminder_type: str,
    config: VpnConfig,
    details: str,
    dedup_key: str,
) -> bool:
    if reminder_recently_sent(db, owner.id, reminder_type, dedup_key):
        return False

    owner_event = OWNER_EVENT_MAP[reminder_type]
    if owner.telegram_id and owner.has_tg_notify_event(owner_event):
        bot_token = _get_setting(db, "telegram_bot_token", "").strip()
        if bot_token and get_feature_service().is_enabled("telegram"):
            text = _build_owner_message(reminder_type, config, details)
            send_tg_message(bot_token, owner.telegram_id, text)

    admin_event = ADMIN_EVENT_MAP[reminder_type]
    admin_notify_service.send(
        db,
        admin_event,
        actor_username=owner.username,
        target_name=config.client_name,
        target_type=config.vpn_type.value,
        details=details,
        subject_name=owner.username,
        node_id=config.node_id,
    )

    record_reminder_sent(db, owner.id, reminder_type, dedup_key)
    return True


def _policy_for_config(svc: AccessPolicyService, config: VpnConfig) -> dict:
    if config.vpn_type == VpnType.openvpn:
        return svc.get_openvpn_policy(config.client_name)
    return svc.get_wg_policy(config.client_name)


def process_user_reminders(db: Session) -> int:
    if not self_service_reminder_enabled():
        return 0

    sent = 0
    threshold = _cert_threshold()
    nodes = db.query(Node).all()
    settings = get_settings()
    for node in nodes:
        try:
            adapter = get_adapter_for_node(node)
            meta = node_metadata_dict(node)
            az_path = Path(str(meta.get("antizapret_path") or settings.antizapret_path))
            svc = AccessPolicyService(
                db,
                antizapret_path=az_path,
                node_id=node.id,
                node_name=node.name,
                adapter=adapter,
            )
        except Exception:
            logger.exception("user_reminder: skip node %s", node.id)
            continue

        configs = (
            db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == node.id,
                VpnConfig.ha_primary_config_id.is_(None),
            )
            .all()
        )
        for config in configs:
            owner = db.get(User, config.owner_id)
            if not owner or owner.role.value == "admin":
                continue

            policy = _policy_for_config(svc, config)

            if config.vpn_type == VpnType.openvpn and config.cert_expire_days is not None:
                if config.cert_expire_days <= threshold:
                    dedup_key = f"config:{config.id}"
                    details = f"Осталось <b>{config.cert_expire_days}</b> дн."
                    if _send_owner_reminder(db, owner, REMINDER_CERT, config, details, dedup_key):
                        sent += 1

            if policy.get("block_mode") == "temp":
                dedup_key = f"config:{config.id}:temp"
                until = policy.get("block_until") or "—"
                details = f"До: <code>{until}</code>"
                if _send_owner_reminder(db, owner, REMINDER_TEMP_BLOCK, config, details, dedup_key):
                    sent += 1

            traffic_exceeded = bool(policy.get("traffic_limit_exceeded"))
            limit_human = policy.get("traffic_limit_human")
            consumed_human = policy.get("traffic_consumed_human")
            limit_bytes = policy.get("traffic_limit_bytes")
            consumed_bytes = policy.get("traffic_consumed_bytes")
            if traffic_exceeded or _traffic_warning(
                int(limit_bytes) if limit_bytes is not None else None,
                int(consumed_bytes) if consumed_bytes is not None else None,
            ):
                dedup_key = f"config:{config.id}:traffic"
                if traffic_exceeded:
                    details = f"Превышен лимит: {consumed_human or '—'} / {limit_human or '—'}"
                else:
                    details = f"Использовано {consumed_human or '—'} из {limit_human or '—'} ({_traffic_warning_percent()}%)"
                if _send_owner_reminder(db, owner, REMINDER_TRAFFIC, config, details, dedup_key):
                    sent += 1

    return sent
