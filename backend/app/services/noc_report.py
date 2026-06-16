"""Lightweight NOC summary for scheduled Telegram reports (DB aggregates only)."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AlertRule, AppSetting, CidrDbRefreshLog, Node, NodeStatus, TrafficSessionState, User, UserTrafficSample
from app.services.feature_guards import get_feature_service
from app.services.node_compare_metrics import get_traffic_totals_by_node
from app.services.notify_time import format_notify_when
from app.services.resource_metrics import get_latest_samples_by_node
from app.services.telegram import send_tg_document, send_tg_message
from app.services.traffic_limit import human_bytes

logger = logging.getLogger(__name__)

NOC_REPORT_EVENT = "noc_report"
WEEKLY_REPORT_DAYS = 7


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _wg_profile(profile: str | None) -> bool:
    return "-wg" in (profile or "").lower()


def build_noc_summary(db: Session) -> dict:
    """Aggregate NOC metrics from DB without live node adapter calls."""
    nodes = db.query(Node).order_by(Node.id.asc()).all()
    latest_metrics = get_latest_samples_by_node(db)
    traffic_totals = get_traffic_totals_by_node(db)

    active_rows = (
        db.query(
            TrafficSessionState.node_id,
            TrafficSessionState.profile,
            func.count(TrafficSessionState.id),
        )
        .filter(TrafficSessionState.is_active.is_(True))
        .group_by(TrafficSessionState.node_id, TrafficSessionState.profile)
        .all()
    )

    sessions_by_node: dict[int, dict[str, int]] = {}
    total_ovpn = 0
    total_wg = 0
    for node_id, profile, count in active_rows:
        bucket = sessions_by_node.setdefault(int(node_id), {"openvpn": 0, "wireguard": 0})
        if _wg_profile(profile):
            bucket["wireguard"] += int(count or 0)
            total_wg += int(count or 0)
        else:
            bucket["openvpn"] += int(count or 0)
            total_ovpn += int(count or 0)

    node_lines: list[dict] = []
    nodes_online = 0
    total_traffic = 0
    for node in nodes:
        if node.status == NodeStatus.online:
            nodes_online += 1
        sessions = sessions_by_node.get(node.id, {"openvpn": 0, "wireguard": 0})
        sample = latest_metrics.get(node.id)
        traffic = int(traffic_totals.get(node.id) or 0)
        total_traffic += traffic
        node_lines.append(
            {
                "name": node.name,
                "status": node.status.value if hasattr(node.status, "value") else str(node.status),
                "openvpn": sessions["openvpn"],
                "wireguard": sessions["wireguard"],
                "cpu_percent": round(sample.cpu_percent, 1) if sample else None,
                "memory_percent": round(sample.memory_percent, 1) if sample else None,
                "traffic_bytes": traffic,
            }
        )

    return {
        "timestamp": datetime.now(timezone.utc),
        "nodes_total": len(nodes),
        "nodes_online": nodes_online,
        "total_openvpn": total_ovpn,
        "total_wireguard": total_wg,
        "total_traffic_bytes": total_traffic,
        "nodes": node_lines,
    }


def format_noc_report_message(summary: dict, *, period: str) -> str:
    period_label = "еженедельная" if period == "weekly" else "ежедневная"
    when = format_notify_when(None)
    lines = [
        f"📊 <b>NOC сводка ({period_label})</b>",
        f"🕐 {when}",
        "",
        f"Узлы: <b>{summary['nodes_online']}/{summary['nodes_total']}</b> online",
        (
            f"Сессии: OVPN <b>{summary['total_openvpn']}</b>"
            f" · WG <b>{summary['total_wireguard']}</b>"
        ),
    ]

    traffic_label = human_bytes(summary.get("total_traffic_bytes"))
    if traffic_label:
        lines.append(f"Трафик (всего): <b>{traffic_label}</b>")

    lines.append("")
    for node in summary.get("nodes") or []:
        status_icon = "🟢" if node.get("status") == NodeStatus.online.value else "🔴"
        parts = [
            f"OVPN {node.get('openvpn', 0)}",
            f"WG {node.get('wireguard', 0)}",
        ]
        if node.get("cpu_percent") is not None:
            parts.append(f"CPU {node['cpu_percent']}%")
        if node.get("memory_percent") is not None:
            parts.append(f"RAM {node['memory_percent']}%")
        lines.append(f"{status_icon} <b>{node.get('name')}</b> · {' · '.join(parts)}")

    return "\n".join(lines)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _top_clients(db: Session, *, since: datetime, until: datetime, limit: int) -> list[dict]:
    traffic_sum = func.coalesce(
        func.sum(UserTrafficSample.delta_received + UserTrafficSample.delta_sent),
        0,
    )
    rows = (
        db.query(UserTrafficSample.common_name, traffic_sum.label("total_bytes"))
        .filter(
            UserTrafficSample.created_at >= since,
            UserTrafficSample.created_at < until,
        )
        .group_by(UserTrafficSample.common_name)
        .order_by(traffic_sum.desc())
        .limit(max(1, int(limit or 10)))
        .all()
    )
    return [
        {"common_name": str(name or ""), "traffic_bytes": int(total or 0)}
        for name, total in rows
    ]


def _weekly_incidents(db: Session, *, since: datetime, until: datetime) -> list[dict]:
    from app.services.alert_rules import format_rule_condition

    rules = (
        db.query(AlertRule)
        .filter(AlertRule.last_triggered_at.isnot(None))
        .order_by(AlertRule.last_triggered_at.desc())
        .all()
    )
    incidents: list[dict] = []
    for rule in rules:
        triggered_at = _as_utc(rule.last_triggered_at)
        if triggered_at is None or triggered_at < since or triggered_at >= until:
            continue
        incidents.append(
            {
                "name": rule.name,
                "condition": format_rule_condition(rule),
                "last_triggered_at": triggered_at,
            }
        )
    return incidents


def _weekly_cidr_failures(db: Session, *, since: datetime, until: datetime) -> list[dict]:
    rows = (
        db.query(CidrDbRefreshLog)
        .filter(CidrDbRefreshLog.started_at >= since, CidrDbRefreshLog.started_at < until)
        .order_by(CidrDbRefreshLog.started_at.desc())
        .all()
    )
    failures: list[dict] = []
    for row in rows:
        status = str(row.status or "")
        if status in {"success", "running", "cleared"} and int(row.providers_failed or 0) == 0:
            continue
        failures.append(
            {
                "started_at": _as_utc(row.started_at),
                "status": status,
                "providers_failed": int(row.providers_failed or 0),
                "error": row.error,
            }
        )
    return failures


def build_weekly_report_data(
    db: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    top_clients_limit: int | None = None,
) -> dict:
    """Aggregate weekly PDF report payload (extends NOC summary)."""
    settings = get_settings()
    until = _as_utc(until) or datetime.now(timezone.utc)
    since = _as_utc(since) or (until - timedelta(days=WEEKLY_REPORT_DAYS))
    limit = top_clients_limit if top_clients_limit is not None else settings.noc_report_weekly_pdf_top_clients

    return {
        "period": {"start": since, "end": until},
        "summary": build_noc_summary(db),
        "top_clients": _top_clients(db, since=since, until=until, limit=limit),
        "incidents": _weekly_incidents(db, since=since, until=until),
        "cidr_failures": _weekly_cidr_failures(db, since=since, until=until),
    }


def generate_weekly_pdf_bytes(db: Session, *, since: datetime | None = None, until: datetime | None = None) -> bytes:
    from app.services.noc_report_pdf import generate_weekly_pdf

    report_data = build_weekly_report_data(db, since=since, until=until)
    return generate_weekly_pdf(report_data)


def generate_weekly_pdf_file(
    db: Session,
    output_dir: Path | None = None,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Path:
    """Write weekly PDF to disk and return its path."""
    target_dir = output_dir or Path("data/reports")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = (_as_utc(until) or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    path = target_dir / f"noc-weekly-{stamp}.pdf"
    path.write_bytes(generate_weekly_pdf_bytes(db, since=since, until=until))
    return path


def send_weekly_pdf_report(db: Session, *, since: datetime | None = None, until: datetime | None = None) -> dict:
    """Generate weekly PDF and optionally deliver it to TG admins."""
    settings = get_settings()
    if not settings.noc_report_weekly_pdf_enabled:
        return {"status": "skipped", "reason": "pdf_disabled"}

    pdf_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(generate_weekly_pdf_bytes(db, since=since, until=until))
            pdf_path = Path(tmp.name)

        result: dict = {
            "status": "generated",
            "path": str(pdf_path),
            "sent": 0,
            "recipients": 0,
        }

        if not settings.noc_report_weekly_pdf_tg_enabled:
            result["status"] = "generated_no_tg"
            result["reason"] = "tg_delivery_disabled"
            return result

        if not get_feature_service().is_enabled("telegram"):
            result["status"] = "generated_no_tg"
            result["reason"] = "telegram_disabled"
            return result
        if _get_setting(db, "telegram_notify_enabled", "false") != "true":
            result["status"] = "generated_no_tg"
            result["reason"] = "notify_disabled"
            return result

        bot_token = _get_setting(db, "telegram_bot_token", "").strip()
        if not bot_token:
            result["status"] = "generated_no_tg"
            result["reason"] = "no_bot_token"
            return result

        recipients = _notify_recipients(db)
        result["recipients"] = len(recipients)
        if not recipients:
            result["status"] = "generated_no_tg"
            result["reason"] = "no_recipients"
            return result

        when = format_notify_when(None)
        caption = f"📄 <b>NOC weekly PDF</b>\n🕐 {when}"
        filename = f"noc-weekly-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.pdf"
        sent = 0
        for user in recipients:
            try:
                if send_tg_document(
                    bot_token,
                    user.telegram_id,
                    str(pdf_path),
                    caption=caption,
                    filename=filename,
                    content_type="application/pdf",
                    run_async=False,
                ):
                    sent += 1
            except Exception as exc:
                logger.warning("NOC weekly PDF TG send failed for user %s: %s", user.id, exc)

        result["status"] = "sent" if sent else "generated_no_tg"
        result["sent"] = sent
        if not sent:
            result["reason"] = "send_failed"
        return result
    finally:
        if pdf_path is not None:
            try:
                pdf_path.unlink(missing_ok=True)
            except OSError:
                pass


def _notify_recipients(db: Session) -> list[User]:
    return [
        user
        for user in db.query(User).filter(User.telegram_id.isnot(None)).all()
        if user.has_tg_notify_event(NOC_REPORT_EVENT)
    ]


def send_noc_report(db: Session, *, period: str) -> dict:
    """Build summary and deliver to admins with noc_report TG preference enabled."""
    if not get_feature_service().is_enabled("telegram"):
        return {"status": "skipped", "reason": "telegram_disabled"}
    if _get_setting(db, "telegram_notify_enabled", "false") != "true":
        return {"status": "skipped", "reason": "notify_disabled"}

    bot_token = _get_setting(db, "telegram_bot_token", "").strip()
    if not bot_token:
        return {"status": "skipped", "reason": "no_bot_token"}

    recipients = _notify_recipients(db)
    if not recipients:
        return {"status": "skipped", "reason": "no_recipients"}

    summary = build_noc_summary(db)
    text = format_noc_report_message(summary, period=period)
    sent = 0
    for user in recipients:
        try:
            if send_tg_message(bot_token, user.telegram_id, text):
                sent += 1
        except Exception as exc:
            logger.warning("NOC report TG send failed for user %s: %s", user.id, exc)

    return {"status": "sent", "period": period, "recipients": len(recipients), "sent": sent}
