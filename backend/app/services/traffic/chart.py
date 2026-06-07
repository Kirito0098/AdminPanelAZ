"""Traffic time-series chart data (ported from AdminAntizapret)."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import UserTrafficSample


def fetch_traffic_chart(
    db: Session,
    node_id: int,
    client: str,
    range_key: str = "7d",
    protocol_filter: str = "all",
) -> dict:
    client = (client or "").strip()
    range_key = (range_key or "7d").strip().lower()
    protocol_filter = (protocol_filter or "all").strip().lower()

    if not client:
        return {"error": "Параметр client обязателен"}

    if range_key == "24h":
        range_key = "1d"
    if range_key not in ("1h", "1d", "7d", "30d", "all"):
        range_key = "7d"
    if protocol_filter not in ("all", "openvpn", "wireguard"):
        protocol_filter = "all"

    now = datetime.utcnow()
    since_dt = None
    bucket = "day"

    if range_key == "1h":
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
        UserTrafficSample.node_id == node_id,
        UserTrafficSample.common_name == client,
    )
    if since_dt is not None:
        query = query.filter(UserTrafficSample.created_at >= since_dt)

    samples = query.order_by(UserTrafficSample.created_at.asc()).all()
    grouped: dict = defaultdict(lambda: {"vpn": 0, "antizapret": 0, "openvpn": 0, "wireguard": 0})

    for item in samples:
        dt = item.created_at
        if not dt:
            continue

        if bucket == "minute5":
            minute = (dt.minute // 5) * 5
            bucket_key = dt.strftime("%Y-%m-%d %H") + f":{minute:02d}"
            label = dt.strftime("%H") + f":{minute:02d}"
        elif bucket == "hour":
            bucket_key = dt.strftime("%Y-%m-%d %H")
            label = dt.strftime("%d.%m %H:00")
        elif bucket == "day":
            bucket_key = dt.strftime("%Y-%m-%d")
            label = dt.strftime("%d.%m")
        else:
            bucket_key = dt.strftime("%Y-%m")
            label = dt.strftime("%Y-%m")

        total_delta = int(item.delta_received or 0) + int(item.delta_sent or 0)
        net = "antizapret" if item.network_type == "antizapret" else "vpn"
        protocol = (item.protocol_type or "openvpn").strip().lower()
        if protocol not in ("openvpn", "wireguard"):
            protocol = "openvpn"

        if protocol_filter != "all" and protocol != protocol_filter:
            continue

        grouped[bucket_key]["label"] = label
        grouped[bucket_key][net] += total_delta
        grouped[bucket_key][protocol] += total_delta

    ordered_keys = sorted(grouped.keys())
    labels = [grouped[k].get("label", k) for k in ordered_keys]
    vpn_bytes = [int(grouped[k].get("vpn", 0)) for k in ordered_keys]
    antizapret_bytes = [int(grouped[k].get("antizapret", 0)) for k in ordered_keys]
    openvpn_bytes = [int(grouped[k].get("openvpn", 0)) for k in ordered_keys]
    wireguard_bytes = [int(grouped[k].get("wireguard", 0)) for k in ordered_keys]

    total_vpn = sum(vpn_bytes)
    total_antizapret = sum(antizapret_bytes)

    return {
        "client": client,
        "range": range_key,
        "bucket": bucket,
        "protocol_filter": protocol_filter,
        "labels": labels,
        "vpn_bytes": vpn_bytes,
        "antizapret_bytes": antizapret_bytes,
        "openvpn_bytes": openvpn_bytes,
        "wireguard_bytes": wireguard_bytes,
        "total_vpn": total_vpn,
        "total_antizapret": total_antizapret,
        "total": total_vpn + total_antizapret,
    }
