"""Traffic time-series chart data (ported from AdminAntizapret)."""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UserTrafficSample
from app.services.chart_timezone import (
    local_bucket_start_as_utc_iso,
    naive_utc_to_local,
    resolve_chart_timezone,
)
from app.services.traffic.period import TrafficPeriodWindow, chart_bucket_for_window


def fetch_traffic_chart(
    db: Session,
    node_ids: int | list[int],
    client: str,
    range_key: str = "7d",
    protocol_filter: str = "all",
    tz_name: str | None = None,
    *,
    period_window: TrafficPeriodWindow | None = None,
) -> dict:
    scope_ids = [node_ids] if isinstance(node_ids, int) else list(node_ids)
    client = (client or "").strip()
    range_key = (range_key or "7d").strip().lower()
    protocol_filter = (protocol_filter or "all").strip().lower()
    tz = resolve_chart_timezone(explicit=tz_name)

    if not client:
        return {"error": "Параметр client обязателен"}

    if range_key == "24h":
        range_key = "1d"
    if range_key not in ("1h", "1d", "7d", "30d", "all"):
        range_key = "7d"
    if protocol_filter not in ("all", "openvpn", "wireguard", "amneziawg2"):
        protocol_filter = "all"

    now = datetime.utcnow()
    since_dt = None
    until_dt = None
    bucket = "day"
    response_range = range_key
    retention_days = (
        period_window.retention_days
        if period_window is not None
        else get_settings().traffic_sample_retention_days
    )

    if period_window is not None and period_window.mode == "custom":
        since_dt = period_window.since_utc
        until_dt = period_window.until_utc
        bucket = chart_bucket_for_window(period_window)
        response_range = "custom"
    elif range_key == "1h":
        since_dt = now - timedelta(hours=1)
        bucket = "minute5"
    elif range_key == "1d":
        since_dt = now - timedelta(hours=24)
        bucket = "hour"
    elif range_key == "7d":
        since_dt = now - timedelta(days=7)
        bucket = "day"
    elif range_key == "30d":
        since_dt = now - timedelta(days=30)
        bucket = "day"
    else:
        bucket = "month"

    query = db.query(UserTrafficSample).filter(
        UserTrafficSample.node_id.in_(scope_ids),
        UserTrafficSample.common_name == client,
    )
    if since_dt is not None:
        query = query.filter(UserTrafficSample.created_at >= since_dt)
    if until_dt is not None:
        query = query.filter(UserTrafficSample.created_at < until_dt)

    samples = query.order_by(UserTrafficSample.created_at.asc()).all()
    grouped: dict = defaultdict(
        lambda: {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0, "amneziawg2": 0}
    )

    for item in samples:
        dt = item.created_at
        if not dt:
            continue
        local_dt = naive_utc_to_local(dt, tz)

        if bucket == "minute5":
            minute = (local_dt.minute // 5) * 5
            bucket_key = local_dt.strftime("%Y-%m-%d %H") + f":{minute:02d}"
            label = local_dt.strftime("%H") + f":{minute:02d}"
        elif bucket == "hour":
            bucket_key = local_dt.strftime("%Y-%m-%d %H")
            label = local_dt.strftime("%d.%m %H:00")
        elif bucket == "day":
            bucket_key = local_dt.strftime("%Y-%m-%d")
            label = local_dt.strftime("%d.%m")
        else:
            bucket_key = local_dt.strftime("%Y-%m")
            label = local_dt.strftime("%Y-%m")

        total_delta = int(item.delta_received or 0) + int(item.delta_sent or 0)
        net = "antizapret" if item.network_type == "antizapret" else "vpn"
        protocol = (item.protocol_type or "openvpn").strip().lower()
        if protocol.startswith("openvpn"):
            protocol = "openvpn"
        elif protocol not in ("wireguard", "amneziawg2"):
            protocol = "openvpn"

        if protocol_filter != "all" and protocol != protocol_filter:
            continue

        grouped[bucket_key]["label"] = label
        grouped[bucket_key].setdefault("timestamp", local_bucket_start_as_utc_iso(local_dt, bucket))
        grouped[bucket_key][net] += total_delta
        grouped[bucket_key][protocol] += total_delta

    ordered_keys = sorted(grouped.keys())
    labels = [grouped[k].get("label", k) for k in ordered_keys]
    timestamps = [grouped[k].get("timestamp") for k in ordered_keys]
    vpn_bytes = [int(grouped[k].get("vpn", 0)) for k in ordered_keys]
    antizapret_bytes = [int(grouped[k].get("antizapret", 0)) for k in ordered_keys]
    openvpn_bytes = [int(grouped[k].get("openvpn", 0)) for k in ordered_keys]
    wireguard_bytes = [int(grouped[k].get("wireguard", 0)) for k in ordered_keys]
    amneziawg2_bytes = [int(grouped[k].get("amneziawg2", 0)) for k in ordered_keys]

    total_vpn = sum(vpn_bytes)
    total_antizapret = sum(antizapret_bytes)

    return {
        "client": client,
        "range": response_range,
        "bucket": bucket,
        "protocol_filter": protocol_filter,
        "timezone": tz,
        "labels": labels,
        "timestamps": timestamps,
        "vpn_bytes": vpn_bytes,
        "antizapret_bytes": antizapret_bytes,
        "openvpn_bytes": openvpn_bytes,
        "wireguard_bytes": wireguard_bytes,
        "amneziawg2_bytes": amneziawg2_bytes,
        "total_vpn": total_vpn,
        "total_antizapret": total_antizapret,
        "total": total_vpn + total_antizapret,
        "retention_days": retention_days,
    }
