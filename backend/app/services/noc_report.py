"""Lightweight NOC summary for scheduled Telegram reports (DB aggregates only)."""

from __future__ import annotations

import logging
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AlertRule,
    AppSetting,
    CidrDbRefreshLog,
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    TrafficSessionState,
    User,
    UserTrafficSample,
    WgAccessPolicy,
)
from app.services.feature_guards import get_feature_service
from app.services.node_compare_metrics import get_traffic_totals_by_node
from app.services.notify_time import format_notify_when
from app.services.resource_metrics import get_latest_samples_by_node, get_resource_stats_by_node
from app.services.telegram import send_tg_document, send_tg_message
from app.services.traffic_limit import human_bytes

logger = logging.getLogger(__name__)

NOC_REPORT_EVENT = "noc_report"
WEEKLY_REPORT_DAYS = 7
DAILY_REPORT_DAYS = 1
DAILY_TOP_CLIENTS_LIMIT = 3
WEEKLY_TOP_CLIENTS_LIMIT = 5
_CIDR_OK_STATUSES = frozenset({"ok", "success"})


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


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _session_active_interval(
    session: TrafficSessionState,
    since: datetime,
    until: datetime,
) -> tuple[datetime, datetime] | None:
    """Active interval of a session clipped to [since, until), or None if no overlap."""
    since_n = _to_naive_utc(since)
    until_n = _to_naive_utc(until)
    if until_n <= since_n:
        return None

    connected_ts = int(session.connected_since_ts or 0)
    is_wg = _wg_profile(session.profile)

    if connected_ts > 0:
        sess_start = datetime.utcfromtimestamp(connected_ts)
    elif is_wg:
        if session.is_active or session.ended_at:
            sess_start = since_n
        else:
            return None
    elif session.last_seen_at:
        sess_start = session.last_seen_at
    else:
        return None

    if session.is_active:
        sess_end = until_n
    elif session.ended_at:
        sess_end = session.ended_at
    elif session.last_seen_at:
        sess_end = session.last_seen_at
    else:
        return None

    overlap_start = max(sess_start, since_n)
    overlap_end = min(sess_end, until_n)
    if overlap_end <= overlap_start:
        return None
    return overlap_start, overlap_end


def _peak_concurrent(intervals: list[tuple[datetime, datetime]]) -> int:
    if not intervals:
        return 0
    events: list[tuple[datetime, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], 0 if item[1] < 0 else 1))
    current = 0
    peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _query_period_sessions(db: Session, *, since: datetime, until: datetime) -> list[TrafficSessionState]:
    since_n = _to_naive_utc(since)
    return (
        db.query(TrafficSessionState)
        .filter(
            or_(
                TrafficSessionState.is_active.is_(True),
                TrafficSessionState.ended_at >= since_n,
                TrafficSessionState.last_seen_at >= since_n,
            )
        )
        .all()
    )


def _session_stats_by_node(
    db: Session,
    *,
    since: datetime,
    until: datetime,
) -> tuple[dict[int, dict[str, float | int]], dict[str, int]]:
    """Average/peak concurrent OVPN/WG sessions per node and fleet-wide peaks."""
    since_n = _to_naive_utc(since)
    until_n = _to_naive_utc(until)
    period_seconds = (until_n - since_n).total_seconds()
    if period_seconds <= 0:
        return {}, {"openvpn_peak": 0, "wireguard_peak": 0}

    overlap_totals: dict[int, dict[str, float]] = defaultdict(lambda: {"openvpn": 0.0, "wireguard": 0.0})
    intervals_by_node: dict[int, dict[str, list[tuple[datetime, datetime]]]] = defaultdict(
        lambda: {"openvpn": [], "wireguard": []}
    )
    fleet_intervals: dict[str, list[tuple[datetime, datetime]]] = {"openvpn": [], "wireguard": []}

    for session in _query_period_sessions(db, since=since, until=until):
        interval = _session_active_interval(session, since, until)
        if interval is None:
            continue
        start, end = interval
        node_id = int(session.node_id)
        bucket = "wireguard" if _wg_profile(session.profile) else "openvpn"
        overlap_totals[node_id][bucket] += (end - start).total_seconds()
        intervals_by_node[node_id][bucket].append(interval)
        fleet_intervals[bucket].append(interval)

    node_ids = set(overlap_totals) | set(intervals_by_node)
    by_node = {
        node_id: {
            "openvpn": round(overlap_totals[node_id]["openvpn"] / period_seconds, 1),
            "wireguard": round(overlap_totals[node_id]["wireguard"] / period_seconds, 1),
            "openvpn_peak": _peak_concurrent(intervals_by_node[node_id]["openvpn"]),
            "wireguard_peak": _peak_concurrent(intervals_by_node[node_id]["wireguard"]),
        }
        for node_id in node_ids
    }
    fleet_peaks = {
        "openvpn_peak": _peak_concurrent(fleet_intervals["openvpn"]),
        "wireguard_peak": _peak_concurrent(fleet_intervals["wireguard"]),
    }
    return by_node, fleet_peaks


def _format_session_count(value: float | int | None) -> str:
    if value is None:
        return "0"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}"
    return str(int(value))


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
                "node_id": node.id,
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


def _period_bounds(*, period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    until = _as_utc(now) or datetime.now(timezone.utc)
    days = WEEKLY_REPORT_DAYS if period == "weekly" else DAILY_REPORT_DAYS
    return until - timedelta(days=days), until


def _format_period_window(since: datetime, until: datetime, *, period: str) -> str:
    if period == "daily":
        return "последние 24 ч"
    start = since.astimezone(timezone.utc).strftime("%d.%m")
    end = until.astimezone(timezone.utc).strftime("%d.%m")
    return f"{start} — {end} UTC (7 дн.)"


def _period_average_label(period: str) -> str:
    return "среднее за 7 дн." if period == "weekly" else "среднее за день"


def _period_peak_label(period: str) -> str:
    return "пик за 7 дн." if period == "weekly" else "пик за день"


def _traffic_by_node_period(db: Session, *, since: datetime, until: datetime) -> dict[int, int]:
    traffic_sum = func.coalesce(
        func.sum(UserTrafficSample.delta_received + UserTrafficSample.delta_sent),
        0,
    )
    rows = (
        db.query(UserTrafficSample.node_id, traffic_sum)
        .filter(
            UserTrafficSample.created_at >= since,
            UserTrafficSample.created_at < until,
        )
        .group_by(UserTrafficSample.node_id)
        .all()
    )
    return {int(node_id): int(total or 0) for node_id, total in rows}


def _enrich_summary_with_period_traffic(
    summary: dict,
    *,
    period_traffic_by_node: dict[int, int],
) -> None:
    period_total = 0
    for node in summary.get("nodes") or []:
        node_id = int(node.get("node_id") or 0)
        period_bytes = int(period_traffic_by_node.get(node_id) or 0)
        node["period_traffic_bytes"] = period_bytes
        period_total += period_bytes
    summary["period_traffic_bytes"] = period_total


def _traffic_total_period(db: Session, *, since: datetime, until: datetime) -> int:
    return sum(_traffic_by_node_period(db, since=since, until=until).values())


def _format_traffic_delta(current: int, previous: int) -> str | None:
    if previous <= 0 or current < 0:
        return None
    delta_pct = ((current - previous) / previous) * 100
    sign = "+" if delta_pct >= 0 else ""
    return f"{sign}{delta_pct:.0f}%"


def _format_lag_duration(seconds: int | None) -> str:
    if seconds is None:
        return "нет данных"
    value = max(0, int(seconds))
    if value < 60:
        return f"{value} сек назад"
    if value < 3600:
        return f"{value // 60} мин назад"
    hours = value // 3600
    minutes = (value % 3600) // 60
    if minutes:
        return f"{hours} ч {minutes} мин назад"
    return f"{hours} ч назад"


def _traffic_sync_status(db: Session) -> dict:
    settings = get_settings()
    last_sample = db.query(func.max(UserTrafficSample.created_at)).scalar()
    lag_seconds = None
    if last_sample is not None:
        lag_seconds = max(0, int((datetime.utcnow() - last_sample).total_seconds()))
    stale_threshold = int(settings.traffic_db_stale_seconds or 600)
    stale = lag_seconds is None or lag_seconds > stale_threshold
    return {
        "lag_seconds": lag_seconds,
        "stale": stale,
        "stale_threshold_seconds": stale_threshold,
    }


def _traffic_limit_summary(db: Session, *, since: datetime, until: datetime) -> dict[str, int]:
    since_n = _to_naive_utc(since)
    until_n = _to_naive_utc(until)
    blocked_now = 0
    blocks_in_period = 0
    for model in (OpenVpnAccessPolicy, WgAccessPolicy):
        blocked_now += (
            db.query(model)
            .filter(
                model.block_reason == "traffic_limit",
                or_(model.is_temp_blocked.is_(True), model.is_permanent_blocked.is_(True)),
            )
            .count()
        )
        blocks_in_period += (
            db.query(model)
            .filter(
                model.block_reason == "traffic_limit",
                model.block_started_at.isnot(None),
                model.block_started_at >= since_n,
                model.block_started_at < until_n,
            )
            .count()
        )
    return {"blocked_now": blocked_now, "blocks_in_period": blocks_in_period}


def _format_resource_avg_peak(avg: float | None, peak: float | None, *, suffix: str = "%") -> str | None:
    if avg is None and peak is None:
        return None
    avg_label = "—" if avg is None else f"{avg:g}{suffix}"
    peak_label = "—" if peak is None else f"{peak:g}{suffix}"
    return f"{avg_label} / {peak_label}"


def _enrich_summary_with_period_resource_averages(
    summary: dict,
    *,
    stats_by_node: dict[int, dict[str, float | None]],
) -> None:
    cpu_avgs: list[float] = []
    cpu_peaks: list[float] = []
    ram_avgs: list[float] = []
    ram_peaks: list[float] = []
    disk_avgs: list[float] = []
    disk_peaks: list[float] = []

    for node in summary.get("nodes") or []:
        node_id = int(node.get("node_id") or 0)
        stats = stats_by_node.get(node_id)
        if not stats:
            continue
        for avg_key, peak_key, node_avg_key, node_peak_key, avg_bucket, peak_bucket in (
            ("cpu_percent", "cpu_peak", "cpu_percent", "cpu_peak", cpu_avgs, cpu_peaks),
            ("memory_percent", "memory_peak", "memory_percent", "memory_peak", ram_avgs, ram_peaks),
            ("disk_percent", "disk_peak", "disk_percent", "disk_peak", disk_avgs, disk_peaks),
        ):
            avg_value = stats.get(avg_key)
            peak_value = stats.get(peak_key)
            if avg_value is not None:
                node[node_avg_key] = avg_value
                avg_bucket.append(float(avg_value))
            if peak_value is not None:
                node[node_peak_key] = peak_value
                peak_bucket.append(float(peak_value))

    def _fleet_avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    def _fleet_peak(values: list[float]) -> float | None:
        return round(max(values), 1) if values else None

    summary["resource_fleet"] = {
        "cpu_avg": _fleet_avg(cpu_avgs),
        "cpu_peak": _fleet_peak(cpu_peaks),
        "memory_avg": _fleet_avg(ram_avgs),
        "memory_peak": _fleet_peak(ram_peaks),
        "disk_avg": _fleet_avg(disk_avgs),
        "disk_peak": _fleet_peak(disk_peaks),
    }


def _enrich_summary_with_period_session_averages(
    summary: dict,
    *,
    stats_by_node: dict[int, dict[str, float | int]],
    fleet_peaks: dict[str, int],
) -> None:
    total_ovpn = 0.0
    total_wg = 0.0
    for node in summary.get("nodes") or []:
        node_id = int(node.get("node_id") or 0)
        stats = stats_by_node.get(node_id) or {
            "openvpn": 0.0,
            "wireguard": 0.0,
            "openvpn_peak": 0,
            "wireguard_peak": 0,
        }
        node["openvpn"] = stats.get("openvpn", 0.0)
        node["wireguard"] = stats.get("wireguard", 0.0)
        node["openvpn_peak"] = int(stats.get("openvpn_peak") or 0)
        node["wireguard_peak"] = int(stats.get("wireguard_peak") or 0)
        total_ovpn += float(node["openvpn"])
        total_wg += float(node["wireguard"])

    summary["total_openvpn"] = round(total_ovpn, 1)
    summary["total_wireguard"] = round(total_wg, 1)
    summary["total_openvpn_peak"] = int(fleet_peaks.get("openvpn_peak") or 0)
    summary["total_wireguard_peak"] = int(fleet_peaks.get("wireguard_peak") or 0)


def build_noc_report_data(
    db: Session,
    *,
    period: str,
    now: datetime | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    top_clients_limit: int | None = None,
) -> dict:
    """Snapshot metrics plus period-scoped traffic, top clients and incidents."""
    if since is None or until is None:
        since, until = _period_bounds(period=period, now=now)
    else:
        since = _as_utc(since) or datetime.now(timezone.utc)
        until = _as_utc(until) or datetime.now(timezone.utc)
    summary = build_noc_summary(db)
    period_traffic_by_node = _traffic_by_node_period(db, since=since, until=until)
    _enrich_summary_with_period_traffic(summary, period_traffic_by_node=period_traffic_by_node)

    period_seconds = (until - since).total_seconds()
    prev_until = since
    prev_since = since - timedelta(seconds=period_seconds)
    prev_traffic = _traffic_total_period(db, since=prev_since, until=prev_until)
    summary["traffic_prev_period_bytes"] = prev_traffic
    summary["traffic_delta_pct"] = _format_traffic_delta(
        int(summary.get("period_traffic_bytes") or 0),
        prev_traffic,
    )

    resource_stats_by_node = get_resource_stats_by_node(db, since=since, until=until)
    _enrich_summary_with_period_resource_averages(summary, stats_by_node=resource_stats_by_node)
    session_stats_by_node, session_fleet_peaks = _session_stats_by_node(db, since=since, until=until)
    _enrich_summary_with_period_session_averages(
        summary,
        stats_by_node=session_stats_by_node,
        fleet_peaks=session_fleet_peaks,
    )

    if top_clients_limit is None:
        top_clients_limit = (
            WEEKLY_TOP_CLIENTS_LIMIT if period == "weekly" else DAILY_TOP_CLIENTS_LIMIT
        )

    compare_label = "к прошлой неделе" if period == "weekly" else "к вчера"

    return {
        "period": period,
        "period_start": since,
        "period_end": until,
        "compare_label": compare_label,
        "summary": summary,
        "traffic_sync": _traffic_sync_status(db),
        "traffic_limit": _traffic_limit_summary(db, since=since, until=until),
        "top_clients": _top_clients(db, since=since, until=until, limit=top_clients_limit),
        "incidents": _weekly_incidents(db, since=since, until=until),
        "cidr_failures": _weekly_cidr_failures(db, since=since, until=until),
    }


def _format_incident_line(incident: dict) -> str:
    triggered = incident.get("last_triggered_at")
    when = "—"
    if isinstance(triggered, datetime):
        when = triggered.astimezone(timezone.utc).strftime("%d.%m %H:%M")
    name = str(incident.get("name") or "Алерт")
    return f"• {name} · {when}"


def format_noc_report_message(report_data: dict) -> str:
    period = str(report_data.get("period") or "daily")
    summary = report_data.get("summary") or report_data
    since = report_data.get("period_start")
    until = report_data.get("period_end")

    period_label = "еженедельная" if period == "weekly" else "ежедневная"
    traffic_window = "7 дн." if period == "weekly" else "24 ч"
    average_label = _period_average_label(period)
    peak_label = _period_peak_label(period)
    when = format_notify_when(None)

    lines = [
        f"📊 <b>NOC сводка ({period_label})</b>",
        f"🕐 {when}",
    ]
    if isinstance(since, datetime) and isinstance(until, datetime):
        lines.append(f"📅 Период: {_format_period_window(since, until, period=period)}")
    lines.append("")
    lines.append(f"Узлы: <b>{summary['nodes_online']}/{summary['nodes_total']}</b> online")
    lines.append(
        f"Сессии, {average_label}: OVPN <b>{_format_session_count(summary['total_openvpn'])}</b>"
        f" · WG <b>{_format_session_count(summary['total_wireguard'])}</b>"
    )
    lines.append(
        f"Макс. одновременно, {peak_label}: OVPN <b>{summary.get('total_openvpn_peak', 0)}</b>"
        f" · WG <b>{summary.get('total_wireguard_peak', 0)}</b>"
    )

    period_traffic_label = human_bytes(summary.get("period_traffic_bytes"))
    if period_traffic_label:
        traffic_line = f"Трафик за {traffic_window}: <b>{period_traffic_label}</b>"
        delta_pct = summary.get("traffic_delta_pct")
        compare_label = str(report_data.get("compare_label") or "к прошлому периоду")
        if delta_pct:
            traffic_line += f" ({delta_pct} {compare_label})"
        lines.append(traffic_line)

    cumulative_label = human_bytes(summary.get("total_traffic_bytes"))
    if cumulative_label and period == "weekly":
        lines.append(f"Накопительно: {cumulative_label}")

    resource_fleet = summary.get("resource_fleet") or {}
    resource_parts: list[str] = []
    cpu_label = _format_resource_avg_peak(resource_fleet.get("cpu_avg"), resource_fleet.get("cpu_peak"))
    if cpu_label:
        resource_parts.append(f"CPU {cpu_label}")
    ram_label = _format_resource_avg_peak(resource_fleet.get("memory_avg"), resource_fleet.get("memory_peak"))
    if ram_label:
        resource_parts.append(f"RAM {ram_label}")
    disk_label = _format_resource_avg_peak(resource_fleet.get("disk_avg"), resource_fleet.get("disk_peak"))
    if disk_label:
        resource_parts.append(f"Диск {disk_label}")
    if resource_parts:
        lines.append(f"Ресурсы (среднее / пик): {' · '.join(resource_parts)}")

    traffic_sync = report_data.get("traffic_sync") or {}
    lag_seconds = traffic_sync.get("lag_seconds")
    if traffic_sync.get("stale"):
        lines.append(
            f"⚠️ Сбор трафика устарел · последний сэмпл {_format_lag_duration(lag_seconds)}"
        )
    elif lag_seconds is not None:
        lines.append(f"📡 Сбор трафика · {_format_lag_duration(lag_seconds)}")

    traffic_limit = report_data.get("traffic_limit") or {}
    blocked_now = int(traffic_limit.get("blocked_now") or 0)
    blocks_in_period = int(traffic_limit.get("blocks_in_period") or 0)
    if blocked_now or blocks_in_period:
        limit_parts = []
        if blocked_now:
            limit_parts.append(f"<b>{blocked_now}</b> сейчас")
        if blocks_in_period:
            limit_parts.append(f"<b>{blocks_in_period}</b> за {traffic_window}")
        lines.append(f"🚫 Лимит трафика: {' · '.join(limit_parts)}")

    offline_nodes = [
        node.get("name")
        for node in summary.get("nodes") or []
        if node.get("status") != NodeStatus.online.value and node.get("name")
    ]
    if offline_nodes:
        lines.append(f"🔴 Офлайн: <b>{', '.join(offline_nodes)}</b>")

    incidents = report_data.get("incidents") or []
    if incidents:
        lines.append("")
        lines.append(f"⚠️ Алерты: <b>{len(incidents)}</b> срабатываний")
        for incident in incidents[:3]:
            lines.append(_format_incident_line(incident))
        if len(incidents) > 3:
            lines.append(f"… и ещё {len(incidents) - 3}")

    cidr_failures = report_data.get("cidr_failures") or []
    if period == "weekly" or cidr_failures:
        if cidr_failures:
            lines.append(_format_cidr_failures_line(cidr_failures))
        elif period == "weekly":
            lines.append("🌐 CIDR: без ошибок")

    top_clients = report_data.get("top_clients") or []
    if top_clients:
        lines.append("")
        lines.append(f"<b>Топ клиентов ({traffic_window}):</b>")
        for idx, client in enumerate(top_clients, start=1):
            client_label = human_bytes(client.get("traffic_bytes")) or "0 B"
            lines.append(f"{idx}. {client.get('common_name') or '—'} — {client_label}")

    nodes = summary.get("nodes") or []
    multi_node = int(summary.get("nodes_total") or 0) > 1
    lines.append("")
    for node in nodes:
        status_icon = "🟢" if node.get("status") == NodeStatus.online.value else "🔴"
        parts = [
            f"OVPN {_format_session_count(node.get('openvpn', 0))} (макс. {node.get('openvpn_peak', 0)})",
            f"WG {_format_session_count(node.get('wireguard', 0))} (макс. {node.get('wireguard_peak', 0)})",
        ]
        if node.get("cpu_percent") is not None:
            cpu_peak = node.get("cpu_peak")
            if cpu_peak is not None:
                parts.append(f"CPU {node['cpu_percent']}% (пик {cpu_peak:g}%)")
            else:
                parts.append(f"CPU {node['cpu_percent']}%")
        if node.get("memory_percent") is not None:
            ram_peak = node.get("memory_peak")
            if ram_peak is not None:
                parts.append(f"RAM {node['memory_percent']}% (пик {ram_peak:g}%)")
            else:
                parts.append(f"RAM {node['memory_percent']}%")
        if node.get("disk_percent") is not None:
            disk_peak = node.get("disk_peak")
            if disk_peak is not None:
                parts.append(f"Диск {node['disk_percent']}% (пик {disk_peak:g}%)")
            else:
                parts.append(f"Диск {node['disk_percent']}%")
        if multi_node:
            node_period = human_bytes(node.get("period_traffic_bytes"))
            if node_period:
                parts.append(f"{node_period}/{traffic_window}")
        lines.append(
            f"{status_icon} <b>{node.get('name')}</b>, {average_label} · {' · '.join(parts)}"
        )

    return "\n".join(lines)


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
        if status in {"cleared", "running"}:
            continue
        if status in _CIDR_OK_STATUSES and int(row.providers_failed or 0) == 0:
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


def _format_cidr_failures_line(cidr_failures: list[dict]) -> str:
    errors = sum(1 for item in cidr_failures if str(item.get("status") or "") == "error")
    partials = sum(1 for item in cidr_failures if str(item.get("status") or "") == "partial")
    other = len(cidr_failures) - errors - partials

    parts: list[str] = []
    if errors:
        parts.append(f"{errors} ошибок")
    if partials:
        parts.append(f"{partials} частичных")
    if other:
        parts.append(f"{other} проблем")
    return f"🌐 CIDR: <b>{', '.join(parts)}</b> обновления"


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

    report = build_noc_report_data(
        db,
        period="weekly",
        since=since,
        until=until,
        top_clients_limit=limit,
    )
    return {
        "period": {"start": since, "end": until},
        "summary": report["summary"],
        "compare_label": report.get("compare_label"),
        "traffic_sync": report.get("traffic_sync"),
        "traffic_limit": report.get("traffic_limit"),
        "top_clients": report["top_clients"],
        "incidents": report["incidents"],
        "cidr_failures": report["cidr_failures"],
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

    report_data = build_noc_report_data(db, period=period)
    text = format_noc_report_message(report_data)
    sent = 0
    for user in recipients:
        try:
            if send_tg_message(bot_token, user.telegram_id, text):
                sent += 1
        except Exception as exc:
            logger.warning("NOC report TG send failed for user %s: %s", user.id, exc)

    return {"status": "sent", "period": period, "recipients": len(recipients), "sent": sent}


def send_noc_report_preview(
    db: Session,
    *,
    period: str,
    telegram_id: str,
    bot_token: str,
) -> bool:
    """Send a single NOC report message to one Telegram ID (manual preview)."""
    report_data = build_noc_report_data(db, period=period)
    text = format_noc_report_message(report_data)
    return send_tg_message(bot_token, telegram_id, text, run_async=False)


def send_weekly_pdf_preview(
    db: Session,
    *,
    telegram_id: str,
    bot_token: str,
) -> bool:
    """Generate and send weekly NOC PDF to one Telegram ID (manual preview)."""
    pdf_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(generate_weekly_pdf_bytes(db))
            pdf_path = Path(tmp.name)
        when = format_notify_when(None)
        caption = f"📄 <b>NOC weekly PDF (предпросмотр)</b>\n🕐 {when}"
        filename = f"noc-weekly-preview-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.pdf"
        return send_tg_document(
            bot_token,
            telegram_id,
            str(pdf_path),
            caption=caption,
            filename=filename,
            content_type="application/pdf",
            run_async=False,
        )
    finally:
        if pdf_path is not None:
            try:
                pdf_path.unlink(missing_ok=True)
            except OSError:
                pass
