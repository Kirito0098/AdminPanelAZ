"""Client VPN session breakdown for traffic monitoring."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import TrafficSessionState
from app.services.ip_geo import lookup_ips_geo, normalize_client_ip, parse_client_endpoint


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _connected_since_at(ts: int) -> str | None:
    if not ts or ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None).isoformat()


def _duration_seconds(
    connected_since_ts: int,
    *,
    ended_at: datetime | None,
    last_seen_at: datetime | None,
    is_active: bool,
) -> int | None:
    if not connected_since_ts or connected_since_ts <= 0:
        if ended_at and last_seen_at:
            return max(int((ended_at - last_seen_at).total_seconds()), 0)
        return None
    start = datetime.fromtimestamp(connected_since_ts, tz=timezone.utc).replace(tzinfo=None)
    end = ended_at or last_seen_at
    if end is None:
        return None
    return max(int((end - start).total_seconds()), 0)


def fetch_client_sessions(
    db: Session,
    node_id: int,
    client_name: str,
    *,
    recent_limit: int = 30,
) -> dict:
    client = (client_name or "").strip()
    if not client:
        return {"error": "client is required"}

    limit = max(1, min(int(recent_limit or 30), 100))
    rows = (
        db.query(TrafficSessionState)
        .filter(
            TrafficSessionState.node_id == node_id,
            TrafficSessionState.common_name == client,
        )
        .order_by(TrafficSessionState.last_seen_at.desc().nullslast(), TrafficSessionState.id.desc())
        .all()
    )

    total_sessions = len(rows)
    by_ip: dict[str, dict] = defaultdict(
        lambda: {
            "client_ip": "",
            "display_address": None,
            "sessions_count": 0,
            "virtual_addresses": set(),
            "total_bytes": 0,
            "first_seen_at": None,
            "last_seen_at": None,
            "is_active": False,
        }
    )
    virtual_addresses: set[str] = set()

    for row in rows:
        endpoint = parse_client_endpoint(row.real_address)
        client_ip = normalize_client_ip(row.real_address)
        bucket = by_ip[client_ip]
        bucket["client_ip"] = client_ip
        bucket["sessions_count"] += 1
        if endpoint["display_address"] and not bucket["display_address"]:
            bucket["display_address"] = endpoint["display_address"]
        if row.virtual_address:
            bucket["virtual_addresses"].add(row.virtual_address.strip())
            virtual_addresses.add(row.virtual_address.strip())
        rx = int(row.last_bytes_received or 0)
        tx = int(row.last_bytes_sent or 0)
        bucket["total_bytes"] += rx + tx
        seen_at = row.last_seen_at
        if seen_at:
            if bucket["first_seen_at"] is None or seen_at < bucket["first_seen_at"]:
                bucket["first_seen_at"] = seen_at
            if bucket["last_seen_at"] is None or seen_at > bucket["last_seen_at"]:
                bucket["last_seen_at"] = seen_at
        if row.is_active:
            bucket["is_active"] = True

    sources = sorted(
        by_ip.values(),
        key=lambda item: (item["sessions_count"], item["total_bytes"]),
        reverse=True,
    )
    for item in sources:
        item["virtual_addresses"] = sorted(item["virtual_addresses"])

    total_bytes_all = sum(int(item["total_bytes"] or 0) for item in sources)
    geo_by_ip = lookup_ips_geo([item["client_ip"] for item in sources])
    by_source = []
    for item in sources:
        share = (int(item["total_bytes"] or 0) / total_bytes_all * 100) if total_bytes_all > 0 else 0.0
        lookup_ip = (item["client_ip"] or "").strip("[]")
        geo = geo_by_ip.get(lookup_ip, {})
        by_source.append({
            "client_ip": item["client_ip"],
            "display_address": item["display_address"],
            "city": geo.get("city"),
            "country": geo.get("country"),
            "isp": geo.get("isp"),
            "location_label": geo.get("location_label"),
            "geo_label": geo.get("geo_label"),
            "sessions_count": int(item["sessions_count"] or 0),
            "virtual_addresses": item["virtual_addresses"],
            "total_bytes": int(item["total_bytes"] or 0),
            "first_seen_at": _iso(item["first_seen_at"]),
            "last_seen_at": _iso(item["last_seen_at"]),
            "is_active": bool(item["is_active"]),
            "share_percent": round(share, 1),
        })

    recent_sessions = []
    for row in rows[:limit]:
        rx = int(row.last_bytes_received or 0)
        tx = int(row.last_bytes_sent or 0)
        recent_sessions.append({
            "profile": row.profile,
            "real_address": parse_client_endpoint(row.real_address)["display_address"],
            "virtual_address": row.virtual_address,
            "connected_since_at": _connected_since_at(int(row.connected_since_ts or 0)),
            "last_seen_at": _iso(row.last_seen_at),
            "ended_at": _iso(row.ended_at),
            "duration_seconds": _duration_seconds(
                int(row.connected_since_ts or 0),
                ended_at=row.ended_at,
                last_seen_at=row.last_seen_at,
                is_active=bool(row.is_active),
            ),
            "bytes_received": rx,
            "bytes_sent": tx,
            "total_bytes": rx + tx,
            "is_active": bool(row.is_active),
        })

    return {
        "client": client,
        "total_sessions": total_sessions,
        "unique_sources": len(by_source),
        "unique_virtual_addresses": len(virtual_addresses),
        "by_source": by_source,
        "recent_sessions": recent_sessions,
    }
