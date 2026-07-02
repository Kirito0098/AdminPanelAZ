"""Admin Telegram notifications (ported from AdminAntizapret admin_notify.py)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, User
from app.services.admin_notify_settings_text import (
    parse_mini_details_kv,
    user_action_tg_action_line,
)
from app.services.feature_guards import get_feature_service
from app.services.notify_time import format_notify_when
from app.services.notify_backends import dispatch_admin_notify, register_notify_backend
from app.services.telegram import send_tg_message
from app.services.resource_alert_sustained import SustainedMetricSource
from app.services.traffic_limit import (
    format_traffic_limit_period_label,
    format_traffic_limit_unblock_at,
)

logger = logging.getLogger(__name__)

TG_NOTIFY_EVENT_LABELS: list[tuple[str, str]] = [
    ("login_success", "Успешный вход"),
    ("login_failed", "Неверный пароль"),
    ("tg_unlinked", "Вход с непривязанным TG ID"),
    ("config_create", "Создание / пересоздание конфига"),
    ("config_delete", "Удаление конфига"),
    ("user_create", "Добавление пользователя"),
    ("user_delete", "Удаление пользователя"),
    ("client_ban", "Блокировка / разблокировка клиента"),
    ("traffic_limit", "Лимит трафика (блок / авторазблокировка)"),
    ("cert_expiry_reminder", "Напоминание: срок сертификата"),
    ("traffic_limit_reminder", "Напоминание: лимит трафика"),
    ("temp_block_reminder", "Напоминание: временная блокировка"),
    ("user_cert_expiry_reminder", "Пользователь: срок сертификата"),
    ("user_traffic_limit_reminder", "Пользователь: лимит трафика"),
    ("user_temp_block_reminder", "Пользователь: временная блокировка"),
    ("settings_change", "Изменение настроек"),
    ("high_cpu", "Высокая нагрузка CPU"),
    ("high_ram", "Высокая нагрузка RAM"),
    ("cidr_deploy_failed", "Ошибка развёртывания CIDR"),
    ("cidr_ingest_partial", "Частичное обновление CIDR БД"),
    ("noc_report", "NOC: ежедневная/еженедельная сводка"),
    ("alert_rule", "Alert rule: срабатывание порога"),
]

CLIENT_BLOCK_NOTIFY_EVENTS = frozenset({
    "openvpn_client_block_toggle",
    "openvpn_temp_block",
    "openvpn_perm_block",
    "openvpn_unblock",
    "wg_client_temp_block_set",
    "wg_client_permanent_block_set",
    "wg_client_block_clear",
    "wg_temp_block",
    "wg_perm_block",
    "wg_unblock",
})

SETTINGS_CHANGE_NOTIFY = frozenset({
    "settings_port_update",
    "settings_telegram_auth_update",
    "settings_nightly_update",
    "settings_backup_update",
    "settings_backup_create",
    "settings_backup_restore",
    "settings_backup_delete",
    "settings_restart_service",
    "settings_user_password_update",
    "settings_user_role_update",
    "settings_cidr_update_queued",
    "settings_cidr_rollback_queued",
    "settings_cidr_db_refresh_queued",
    "settings_cidr_db_clear",
    "settings_cidr_generate_from_db",
    "settings_antifilter_refresh",
    "settings_run_doall",
    "settings_vpn_network_publish",
})

SETTINGS_TG_TITLES = {
    "settings_port_update": "Порт панели",
    "settings_telegram_auth_update": "Авторизация Telegram",
    "settings_nightly_update": "Ночной рестарт",
    "settings_backup_update": "Бэкапы",
    "settings_backup_create": "Бэкапы",
    "settings_backup_restore": "Бэкапы",
    "settings_backup_delete": "Бэкапы",
    "settings_restart_service": "Перезапуск сервиса",
    "settings_user_password_update": "Пароль пользователя",
    "settings_user_role_update": "Роль пользователя",
    "settings_cidr_update_queued": "Обновление CIDR",
    "settings_cidr_rollback_queued": "Откат CIDR",
    "settings_cidr_db_refresh_queued": "База CIDR",
    "settings_cidr_db_clear": "База CIDR",
    "settings_cidr_generate_from_db": "Генерация CIDR",
    "settings_antifilter_refresh": "AntiFilter",
    "settings_run_doall": "Применение изменений",
    "settings_vpn_network_publish": "Публикация панели",
}

SETTINGS_ACTION_EVENTS = frozenset({
    "settings_restart_service",
    "settings_backup_create",
    "settings_backup_restore",
    "settings_backup_delete",
    "settings_run_doall",
    "settings_vpn_network_publish",
    "settings_cidr_update_queued",
    "settings_cidr_rollback_queued",
    "settings_cidr_db_refresh_queued",
    "settings_cidr_db_clear",
    "settings_cidr_generate_from_db",
    "settings_antifilter_refresh",
})

_PREF_KEY_MAP = {
    "tg_login_unlinked": "tg_unlinked",
    "tg_mini_login_unlinked": "tg_unlinked",
    "config_recreate": "config_create",
    "traffic_limit_block": "traffic_limit",
    "traffic_limit_unblock": "traffic_limit",
}


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _mini_protocol_label(raw_value: str | None) -> str:
    value = (raw_value or "").strip().lower()
    if value in {"openvpn", "ovpn"}:
        return "OpenVPN"
    if value in {"wireguard", "wg"}:
        return "WireGuard"
    if value in {"amneziawg", "amnezia"}:
        return "AmneziaWG"
    return "неизвестно"


def _fmt_code(value: str | None) -> str:
    text = str(value or "").strip()
    return f"<code>{text or '—'}</code>"


def _fmt_protocol(target_type: str | None) -> str:
    kind = str(target_type or "").strip().lower()
    if kind in {"wireguard", "wg", "amneziawg", "amnezia"}:
        if kind in {"wireguard", "wg"}:
            return _mini_protocol_label("wg")
        return _mini_protocol_label("amneziawg")
    label = _mini_protocol_label(kind)
    if label != "неизвестно":
        return label
    return ""


def _protocol_emoji(target_type: str | None) -> str:
    kind = str(target_type or "").strip().lower()
    if kind in {"openvpn", "ovpn"}:
        return "🔐"
    if kind in {"wireguard", "wg"}:
        return "🛡️"
    if kind in {"amneziawg", "amnezia"}:
        return "🌀"
    return "📄"


def _fmt_config_object(target_type: str | None, target_name: str | None) -> str:
    protocol = _fmt_protocol(target_type)
    emoji = _protocol_emoji(target_type)
    name = _fmt_code(target_name)
    if protocol:
        return f"{emoji} {protocol} 📁 {name}"
    return f"📁 {name}"


def _fmt_action_config(verb: str, target_type: str | None, target_name: str | None) -> str:
    verb_text = (verb or "").strip()
    if verb_text:
        verb_text = verb_text[0].upper() + verb_text[1:]
    return f"{verb_text} конфигурацию {_fmt_config_object(target_type, target_name)}"


def _format_notify(title: str, actor_line: str | None, action_line: str, when: str) -> str:
    lines = [title]
    if actor_line:
        lines.append(actor_line)
    lines.append(action_line)
    lines.append(when)
    return "\n".join(lines)


def _format_notify_system(title: str, action_line: str, when: str) -> str:
    return f"{title}\n{action_line}\n{when}"


def _fmt_actor(actor_username: str | None, *, as_admin: bool = False) -> str:
    icon = "👨‍💼" if as_admin else "👤"
    role = "Администратор" if as_admin else "Пользователь"
    return f"{icon} {role} {_fmt_code(actor_username)}"


def _fmt_ip(remote_addr: str | None) -> str:
    return f"🌐 IP {_fmt_code(remote_addr)}"


def _fmt_when(now: str) -> str:
    return f"🕐 {now}"


def _prepend_node_context(
    text: str,
    *,
    node_id: int | None = None,
    node_name: str | None = None,
) -> str:
    if not node_id and not node_name:
        return text
    label = (node_name or "—").strip()
    id_part = f" (#{node_id})" if node_id is not None else ""
    return f"📡 Узел: <code>{label}</code>{id_part}\n{text}"


def _resolve_client_block_action(details: str | None) -> str:
    detail_map = parse_mini_details_kv(details)
    action = str(detail_map.get("action") or "").strip().lower()
    if action in {"temp_block", "permanent_block", "unblock"}:
        return action
    if detail_map.get("manual_unblock") == "1":
        return "unblock"
    if detail_map.get("manual_permanent") == "1":
        return "permanent_block"
    if detail_map.get("days") and detail_map.get("blocked") not in {"0", "1"}:
        return "temp_block"
    blocked = detail_map.get("blocked")
    if blocked == "0":
        return "unblock"
    if blocked == "1":
        return "permanent_block"
    return ""


def _human_bytes_from_details(raw_value: str | None) -> str:
    try:
        size = float(raw_value or 0)
    except (TypeError, ValueError):
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    precision = 0 if idx == 0 else (2 if size < 10 else 1)
    return f"{size:.{precision}f} {units[idx]}"


def _build_traffic_limit_message(
    *,
    title: str,
    target_type: str | None,
    target_name: str | None,
    details: str | None,
    when: str,
    action_line: str,
    show_unblock_hint: bool = True,
) -> str:
    detail_map = parse_mini_details_kv(details)
    client = _fmt_config_object(target_type, target_name)
    lines = [title, action_line.replace("{client}", client)]

    limit_bytes = detail_map.get("limit_bytes")
    consumed_bytes = detail_map.get("consumed_bytes")
    if limit_bytes or consumed_bytes:
        limit_human = _human_bytes_from_details(limit_bytes)
        consumed_human = _human_bytes_from_details(consumed_bytes)
        period_days_raw = detail_map.get("period_days")
        period_label = None
        if period_days_raw:
            try:
                period_label = format_traffic_limit_period_label(int(period_days_raw))
            except (TypeError, ValueError):
                period_label = None
        if period_label:
            lines.append(f"📏 Лимит: <code>{limit_human}</code> ({period_label})")
        else:
            lines.append(f"📏 Лимит: <code>{limit_human}</code>")
        lines.append(f"📈 Использовано: <code>{consumed_human}</code>")

    if show_unblock_hint:
        period_days_raw = detail_map.get("period_days")
        unblock_label = None
        if period_days_raw:
            try:
                _unblock_at, unblock_label = format_traffic_limit_unblock_at(int(period_days_raw))
            except (TypeError, ValueError):
                unblock_label = None
        if unblock_label:
            lines.append(f"🕓 {unblock_label}")

    lines.append(when)
    return "\n".join(lines)


def _build_client_ban_message(
    actor_admin: str,
    target_type: str | None,
    target_name: str | None,
    details: str | None,
    when: str,
) -> str | None:
    client = _fmt_config_object(target_type, target_name)
    action = _resolve_client_block_action(details)
    detail_map = parse_mini_details_kv(details)
    days = detail_map.get("days")
    block_until = detail_map.get("block_until")

    if action == "unblock":
        return _format_notify(
            "🟢 <b>Разблокировка клиента</b>",
            actor_admin,
            f"Разблокировал клиента {client}",
            when,
        )
    if action == "permanent_block":
        return _format_notify(
            "🔴 <b>Постоянная блокировка</b>",
            actor_admin,
            f"Заблокировал клиента {client} бессрочно (до ручной разблокировки)",
            when,
        )
    if action == "temp_block":
        duration = f"на {days} дн." if days else "временно"
        if block_until:
            duration = f"{duration}, до {_fmt_code(block_until)}"
        return _format_notify(
            "⏱️ <b>Временная блокировка</b>",
            actor_admin,
            f"Временно заблокировал клиента {client} {duration}",
            when,
        )
    return None


class AdminNotifyService:
    def __init__(self, *, logger_instance: logging.Logger | None = None):
        self.logger = logger_instance or logger
        self._monitor_cooldowns: dict[str, datetime] = {}
        self._resource_alert_cooldowns: dict[tuple[str, int | None], datetime] = {}
        self._monitor_lock = threading.Lock()

    def send(
        self,
        db: Session,
        event_type: str,
        *,
        actor_username: str | None = None,
        target_name: str | None = None,
        target_type: str | None = None,
        remote_addr: str | None = None,
        details: str | None = None,
        subject_name: str | None = None,
        client_timezone: str | None = None,
        node_id: int | None = None,
        node_name: str | None = None,
    ) -> None:
        try:
            if not get_feature_service().is_enabled("telegram"):
                return
            if _get_setting(db, "telegram_notify_enabled", "false") != "true":
                return
            bot_token = _get_setting(db, "telegram_bot_token", "").strip()
            if not bot_token:
                return

            pref_key = _PREF_KEY_MAP.get(event_type, event_type)
            notify_users = [
                u for u in db.query(User).filter(User.telegram_id.isnot(None)).all()
                if u.has_tg_notify_event(pref_key)
            ]
            if not notify_users:
                return

            text = self._build_text(
                event_type,
                actor_username,
                target_name,
                target_type,
                remote_addr,
                details,
                subject_name,
                client_timezone=client_timezone,
            )
            if text is None:
                return

            text = _prepend_node_context(text, node_id=node_id, node_name=node_name)

            dispatch_admin_notify(
                db,
                event_type=event_type,
                text=text,
                recipients=notify_users,
                bot_token=bot_token,
            )
        except Exception as exc:
            self.logger.warning("TG admin notify error: %s", exc)

    def send_login_success(
        self,
        db: Session,
        *,
        actor_username: str,
        remote_addr: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "login_success",
            actor_username=actor_username,
            remote_addr=remote_addr,
            client_timezone=client_timezone,
        )

    def send_login_failed(
        self,
        db: Session,
        *,
        actor_username: str | None = None,
        remote_addr: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "login_failed",
            actor_username=actor_username,
            remote_addr=remote_addr,
            client_timezone=client_timezone,
        )

    def send_tg_login_unlinked(
        self,
        db: Session,
        *,
        telegram_id: str,
        remote_addr: str | None = None,
        mini: bool = False,
        client_timezone: str | None = None,
    ) -> None:
        event_type = "tg_mini_login_unlinked" if mini else "tg_login_unlinked"
        self.send(
            db,
            event_type,
            target_name=telegram_id,
            remote_addr=remote_addr,
            client_timezone=client_timezone,
        )

    def send_config_create(
        self,
        db: Session,
        *,
        actor_username: str,
        target_name: str,
        target_type: str,
        node_id: int | None = None,
        node_name: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "config_create",
            actor_username=actor_username,
            target_name=target_name,
            target_type=target_type,
            node_id=node_id,
            node_name=node_name,
            client_timezone=client_timezone,
        )

    def send_config_recreate(
        self,
        db: Session,
        *,
        actor_username: str,
        target_name: str,
        target_type: str,
        node_id: int | None = None,
        node_name: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "config_recreate",
            actor_username=actor_username,
            target_name=target_name,
            target_type=target_type,
            node_id=node_id,
            node_name=node_name,
            client_timezone=client_timezone,
        )

    def send_config_delete(
        self,
        db: Session,
        *,
        actor_username: str,
        target_name: str,
        target_type: str,
        node_id: int | None = None,
        node_name: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "config_delete",
            actor_username=actor_username,
            target_name=target_name,
            target_type=target_type,
            node_id=node_id,
            node_name=node_name,
            client_timezone=client_timezone,
        )

    def send_user_create(
        self,
        db: Session,
        *,
        actor_username: str,
        target_name: str,
        details: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "user_create",
            actor_username=actor_username,
            target_name=target_name,
            details=details,
            client_timezone=client_timezone,
        )

    def send_user_delete(
        self,
        db: Session,
        *,
        actor_username: str,
        target_name: str,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "user_delete",
            actor_username=actor_username,
            target_name=target_name,
            client_timezone=client_timezone,
        )

    def send_client_ban(
        self,
        db: Session,
        *,
        actor_username: str,
        target_name: str,
        target_type: str,
        details: str | None = None,
        node_id: int | None = None,
        node_name: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "client_ban",
            actor_username=actor_username,
            target_name=target_name,
            target_type=target_type,
            details=details,
            node_id=node_id,
            node_name=node_name,
            client_timezone=client_timezone,
        )

    def send_settings_change(
        self,
        db: Session,
        *,
        actor_username: str,
        settings_key: str,
        details: str | None = None,
        subject_name: str | None = None,
        target_type: str | None = None,
        node_id: int | None = None,
        node_name: str | None = None,
        client_timezone: str | None = None,
    ) -> None:
        self.send(
            db,
            "settings_change",
            actor_username=actor_username,
            target_name=settings_key,
            details=details,
            subject_name=subject_name,
            target_type=target_type,
            node_id=node_id,
            node_name=node_name,
            client_timezone=client_timezone,
        )

    def send_traffic_limit_block(
        self,
        db: Session,
        *,
        target_name: str,
        target_type: str,
        details: str | None = None,
        node_id: int | None = None,
        node_name: str | None = None,
    ) -> None:
        self.send(
            db,
            "traffic_limit_block",
            target_name=target_name,
            target_type=target_type,
            details=details,
            node_id=node_id,
            node_name=node_name,
        )

    def send_traffic_limit_unblock(
        self,
        db: Session,
        *,
        target_name: str,
        target_type: str,
        details: str | None = None,
        node_id: int | None = None,
        node_name: str | None = None,
    ) -> None:
        self.send(
            db,
            "traffic_limit_unblock",
            target_name=target_name,
            target_type=target_type,
            details=details,
            node_id=node_id,
            node_name=node_name,
        )

    def send_high_cpu(
        self,
        db: Session,
        *,
        details: str,
        node_id: int | None = None,
        node_name: str | None = None,
    ) -> None:
        self.send(
            db,
            "high_cpu",
            details=details,
            node_id=node_id,
            node_name=node_name,
        )

    def send_high_ram(
        self,
        db: Session,
        *,
        details: str,
        node_id: int | None = None,
        node_name: str | None = None,
    ) -> None:
        self.send(
            db,
            "high_ram",
            details=details,
            node_id=node_id,
            node_name=node_name,
        )

    def send_cidr_deploy_failed(
        self,
        db: Session,
        *,
        details: str | None = None,
        actor_username: str | None = None,
    ) -> None:
        self.send(
            db,
            "cidr_deploy_failed",
            actor_username=actor_username,
            details=details,
        )

    def send_cidr_ingest_partial(
        self,
        db: Session,
        *,
        details: str | None = None,
        actor_username: str | None = None,
    ) -> None:
        self.send(
            db,
            "cidr_ingest_partial",
            actor_username=actor_username,
            details=details,
        )

    def send_cidr_rollback_failed(
        self,
        db: Session,
        *,
        details: str | None = None,
        actor_username: str | None = None,
    ) -> None:
        self.send(
            db,
            "settings_cidr_rollback_queued",
            actor_username=actor_username,
            details=details,
        )

    def maybe_send_resource_alert(
        self,
        db: Session,
        *,
        cpu_percent: float | None = None,
        ram_percent: float | None = None,
        node_id: int | None = None,
        node_name: str | None = None,
        cpu_source: SustainedMetricSource | None = None,
        ram_source: SustainedMetricSource | None = None,
    ) -> None:
        from app.services.resource_alert_sustained import format_alert_details, is_sustained_high

        if not get_feature_service().is_enabled("resource_monitor"):
            return
        cfg = get_settings()
        now = datetime.now(timezone.utc)
        cooldown = timedelta(minutes=cfg.monitor_cooldown_minutes)
        with self._monitor_lock:
            if cpu_percent is not None and cpu_percent >= cfg.monitor_cpu_threshold:
                source = cpu_source or (
                    SustainedMetricSource.node_cpu
                    if node_id is not None
                    else SustainedMetricSource.panel_host_cpu
                )
                interval = self._sustained_sample_interval(source)
                sustained_ok, sustained_detail = is_sustained_high(
                    db,
                    source=source,
                    node_id=node_id,
                    threshold=float(cfg.monitor_cpu_threshold),
                    current_value=float(cpu_percent),
                    sustained_seconds=cfg.monitor_sustained_seconds,
                    sample_interval_seconds=interval,
                )
                if sustained_ok:
                    key = ("high_cpu", node_id)
                    last = self._resource_alert_cooldowns.get(key)
                    if last is None or (now - last) >= cooldown:
                        self._resource_alert_cooldowns[key] = now
                        self.send_high_cpu(
                            db,
                            details=format_alert_details(
                                float(cpu_percent),
                                float(cfg.monitor_cpu_threshold),
                                sustained_detail,
                            ),
                            node_id=node_id,
                            node_name=node_name,
                        )
            if ram_percent is not None and ram_percent >= cfg.monitor_ram_threshold:
                source = ram_source or (
                    SustainedMetricSource.node_ram
                    if node_id is not None
                    else SustainedMetricSource.panel_host_ram
                )
                interval = self._sustained_sample_interval(source)
                sustained_ok, sustained_detail = is_sustained_high(
                    db,
                    source=source,
                    node_id=node_id,
                    threshold=float(cfg.monitor_ram_threshold),
                    current_value=float(ram_percent),
                    sustained_seconds=cfg.monitor_sustained_seconds,
                    sample_interval_seconds=interval,
                )
                if sustained_ok:
                    key = ("high_ram", node_id)
                    last = self._resource_alert_cooldowns.get(key)
                    if last is None or (now - last) >= cooldown:
                        self._resource_alert_cooldowns[key] = now
                        self.send_high_ram(
                            db,
                            details=format_alert_details(
                                float(ram_percent),
                                float(cfg.monitor_ram_threshold),
                                sustained_detail,
                            ),
                            node_id=node_id,
                            node_name=node_name,
                        )

    @staticmethod
    def _sustained_sample_interval(source: SustainedMetricSource) -> int:
        cfg = get_settings()
        if source in (SustainedMetricSource.node_cpu, SustainedMetricSource.node_ram):
            return cfg.resource_metrics_interval_seconds
        if source == SustainedMetricSource.panel_backend_cpu:
            return cfg.panel_resource_metrics_interval_seconds
        return cfg.monitor_check_interval_seconds

    def start_monitor(self) -> None:
        if not self._monitor_enabled():
            self.logger.info("Resource monitor disabled (MONITOR_ENABLED=false)")
            return
        thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="resource-monitor",
        )
        thread.start()

    def _monitor_enabled(self) -> bool:
        return get_feature_service().is_enabled("resource_monitor")

    def _build_text(
        self,
        event_type: str,
        actor_username: str | None,
        target_name: str | None,
        target_type: str | None,
        remote_addr: str | None,
        details: str | None,
        subject_name: str | None = None,
        *,
        client_timezone: str | None = None,
    ) -> str | None:
        when = _fmt_when(format_notify_when(client_timezone))
        actor_admin = _fmt_actor(actor_username, as_admin=True)
        actor_user = _fmt_actor(actor_username, as_admin=False)
        ip = _fmt_ip(remote_addr)

        if event_type == "login_success":
            return _format_notify(
                "✅ <b>Вход в панель</b>",
                actor_user,
                f"Вошёл в панель · {ip}",
                when,
            )
        if event_type == "login_failed":
            return _format_notify_system(
                "⚠️ <b>Неудачный вход</b>",
                f"🔑 Логин {_fmt_code(actor_username)} · {ip}",
                when,
            )
        if event_type in ("tg_login_unlinked", "tg_mini_login_unlinked"):
            via = "📱 мини-приложение" if "mini" in event_type else "✈️ Телеграм"
            return _format_notify_system(
                "🚫 <b>TG ID не привязан</b>",
                f"Попытка входа через {via} · 🆔 {_fmt_code(target_name)} · {ip}",
                when,
            )
        if event_type == "config_create":
            return _format_notify(
                "✨ <b>Создание конфига</b>",
                actor_admin,
                _fmt_action_config("создал", target_type, target_name),
                when,
            )
        if event_type == "config_recreate":
            return _format_notify(
                "🔄 <b>Пересоздание конфига</b>",
                actor_admin,
                _fmt_action_config("пересоздал", target_type, target_name),
                when,
            )
        if event_type == "config_delete":
            return _format_notify(
                "🗑️ <b>Удаление конфига</b>",
                actor_admin,
                _fmt_action_config("удалил", target_type, target_name),
                when,
            )
        if event_type == "user_create":
            extra = f" · 📝 {_fmt_code(details)}" if details else ""
            return _format_notify(
                "➕ <b>Новый пользователь</b>",
                actor_admin,
                f"Добавил пользователя 🆔 {_fmt_code(target_name)}{extra}",
                when,
            )
        if event_type == "user_delete":
            return _format_notify(
                "➖ <b>Удаление пользователя</b>",
                actor_admin,
                f"Удалил пользователя 🆔 {_fmt_code(target_name)}",
                when,
            )
        if event_type == "client_ban":
            block_text = _build_client_ban_message(
                actor_admin, target_type, target_name, details, when,
            )
            if block_text:
                return block_text
            return _format_notify(
                "🔒 <b>Статус клиента</b>",
                actor_admin,
                f"Изменил статус блокировки для {_fmt_config_object(target_type, target_name)}",
                when,
            )
        if event_type == "settings_change":
            settings_key = str(target_name or "").strip()
            tg_title = SETTINGS_TG_TITLES.get(settings_key, "Изменение настроек")
            action_line = user_action_tg_action_line(
                settings_key,
                details=details,
                target_name=subject_name,
                target_type=target_type,
            )
            icon = "🔧" if settings_key in SETTINGS_ACTION_EVENTS else "⚙️"
            return _format_notify(
                f"{icon} <b>{tg_title}</b>",
                actor_admin,
                action_line,
                when,
            )
        if event_type == "traffic_limit_block":
            return _build_traffic_limit_message(
                title="🚫 <b>Блокировка по лимиту трафика</b>",
                target_type=target_type,
                target_name=target_name,
                details=details,
                when=when,
                action_line="Клиент {client} отключён — превышен лимит трафика",
            )
        if event_type == "traffic_limit_unblock":
            return _build_traffic_limit_message(
                title="🟢 <b>Авторазблокировка по лимиту трафика</b>",
                target_type=target_type,
                target_name=target_name,
                details=details,
                when=when,
                action_line="Клиент {client} разблокирован — начался новый период учёта",
                show_unblock_hint=False,
            )
        if event_type == "high_cpu":
            metric = _fmt_code(details) if details else "—"
            return _format_notify_system(
                "🔥 <b>Высокая нагрузка процессора</b>",
                f"📊 {metric}",
                when,
            )
        if event_type == "high_ram":
            metric = _fmt_code(details) if details else "—"
            return _format_notify_system(
                "💾 <b>Высокая нагрузка памяти</b>",
                f"📊 {metric}",
                when,
            )
        if event_type == "alert_rule":
            rule_name = _fmt_code(target_name)
            condition = details or "—"
            return _format_notify_system(
                "🚨 <b>Alert rule</b>",
                f"📋 {rule_name}\n📊 {condition}",
                when,
            )
        if event_type == "cidr_deploy_failed":
            action = details or "Развёртывание CIDR завершилось с ошибкой"
            if actor_username:
                return _format_notify(
                    "❌ <b>Ошибка развёртывания CIDR</b>",
                    _fmt_actor(actor_username, as_admin=True),
                    action,
                    when,
                )
            return _format_notify_system(
                "❌ <b>Ошибка развёртывания CIDR</b>",
                action,
                when,
            )
        if event_type in (
            "user_cert_expiry_reminder",
            "user_traffic_limit_reminder",
            "user_temp_block_reminder",
        ):
            titles = {
                "user_cert_expiry_reminder": "⚠️ <b>Сертификат пользователя</b>",
                "user_traffic_limit_reminder": "📊 <b>Лимит трафика пользователя</b>",
                "user_temp_block_reminder": "⛔ <b>Временная блокировка</b>",
            }
            user_label = _fmt_code(subject_name or actor_username)
            client_label = _fmt_code(target_name)
            detail_line = details or "—"
            return _format_notify_system(
                titles[event_type],
                f"👤 {user_label} · клиент {client_label} · {detail_line}",
                when,
            )
        return None

    def _monitor_loop(self) -> None:
        from app.database import SessionLocal

        time.sleep(15)
        psutil.cpu_percent(interval=None)
        time.sleep(1)
        settings = get_settings()
        while True:
            try:
                if not self._monitor_enabled():
                    time.sleep(60)
                    continue

                cpu_thr = settings.monitor_cpu_threshold
                ram_thr = settings.monitor_ram_threshold
                cooldown_min = settings.monitor_cooldown_minutes
                interval_sec = settings.monitor_check_interval_seconds

                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                now = datetime.now(timezone.utc)
                cooldown = timedelta(minutes=cooldown_min)

                db = SessionLocal()
                try:
                    from app.services.panel_resource_metrics import persist_host_snapshot

                    persist_host_snapshot(db, cpu_percent=cpu, memory_percent=ram)
                    self.maybe_send_resource_alert(
                        db,
                        cpu_percent=cpu,
                        ram_percent=ram,
                        node_name="Panel",
                    )
                finally:
                    db.close()

                time.sleep(max(9, interval_sec - 1))
            except Exception as exc:
                self.logger.warning("Resource monitor error: %s", exc)
                time.sleep(60)


def _telegram_notify_backend(
    *,
    db: Session,
    event_type: str,
    text: str,
    recipients: list,
    bot_token: str,
    **kwargs,
) -> None:
    for user in recipients:
        send_tg_message(bot_token, user.telegram_id, text)


register_notify_backend("telegram", _telegram_notify_backend)

admin_notify_service = AdminNotifyService()
