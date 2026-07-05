"""Traffic snapshot collector and persistence (ported from AdminAntizapret)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import Node, TrafficSessionState, UserTrafficSample, UserTrafficStatProtocol
from app.schemas import (
    OpenVpnClient,
    TrafficClientRow,
    TrafficHaNodeBreakdown,
    TrafficSummary,
    VpnConfigHaInfo,
    WireGuardPeer,
)
from app.services.wireguard_status import wireguard_peer_is_online


def _profile_from_log_name(log_name: str) -> str:
    base = log_name.replace("-status.log", "")
    return base


def _parse_status_timestamp(value, fallback: datetime) -> datetime:
    """Parse a protocol-reported activity timestamp (e.g. WireGuard handshake).

    Returns a naive UTC datetime clamped to ``fallback`` (scan time) so a real
    last-connection time is used for ``last_seen_at`` instead of the moment the
    collector happened to run. Falls back to ``fallback`` when the value is
    missing or unparseable.
    """
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    # Never report a future activity time (clock skew / rounding).
    return min(parsed, fallback)


def build_status_rows(
    openvpn_clients: list[OpenVpnClient],
    wireguard_peers: list[WireGuardPeer],
) -> list[dict]:
    """Convert monitoring data into status rows for traffic persistence."""
    rows: list[dict] = []

    ovpn_by_profile: dict[str, list[dict]] = {}
    for client in openvpn_clients:
        profile = (client.profile or "").strip()
        if not profile:
            profile = "antizapret-udp" if client.common_name.startswith("antizapret") else "vpn-udp"
        ovpn_by_profile.setdefault(profile, []).append({
            "common_name": client.common_name,
            "real_address": client.real_address,
            "virtual_address": client.virtual_address,
            "bytes_received": client.bytes_received,
            "bytes_sent": client.bytes_sent,
            "connected_since_ts": int(client.connected_since_ts or 0),
            "session_kind": "openvpn",
        })

    for profile, clients in ovpn_by_profile.items():
        rows.append({"profile": profile, "traffic_clients": clients})

    for peer in wireguard_peers:
        if not peer.client_name or not wireguard_peer_is_online(peer):
            continue
        profile = "antizapret-wg" if peer.interface == "antizapret" else "vpn-wg"
        rows.append({
            "profile": profile,
            "traffic_clients": [{
                "common_name": peer.client_name,
                "real_address": peer.endpoint or "",
                "virtual_address": peer.allowed_ips or "",
                "bytes_received": peer.transfer_rx,
                "bytes_sent": peer.transfer_tx,
                "connected_since_ts": 0,
                "session_kind": "wireguard",
                "peer_public_key": peer.public_key,
                "last_seen_iso": peer.latest_handshake,
            }],
        })

    return rows


def build_session_key(profile: str, client: dict) -> str:
    session_kind = (client.get("session_kind") or "").strip().lower()
    if session_kind == "wireguard" or str(profile).endswith("-wg"):
        return (
            f"{profile}|wg|{client.get('common_name', '-')}|"
            f"{client.get('peer_public_key', '-')}|{client.get('virtual_address', '-')}"
        )
    return (
        f"{profile}|{client.get('common_name', '-')}|{client.get('real_address', '-')}|"
        f"{client.get('virtual_address', '-')}|{int(client.get('connected_since_ts') or 0)}"
    )


class TrafficCollectorService:
    def __init__(self, db: Session, node_id: int):
        self.db = db
        self.node_id = node_id

    def persist_snapshot(self, status_rows: list[dict]) -> dict:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        sessions = {
            row.session_key: row
            for row in self.db.query(TrafficSessionState).filter(
                TrafficSessionState.node_id == self.node_id
            ).all()
        }
        previously_active = {k for k, r in sessions.items() if r.is_active}

        stats = {
            (row.common_name, row.protocol_type): row
            for row in self.db.query(UserTrafficStatProtocol).filter(
                UserTrafficStatProtocol.node_id == self.node_id
            ).all()
        }

        seen_keys: set[str] = set()
        samples_added = 0

        for status_row in status_rows:
            profile = status_row.get("profile", "unknown")
            for client in status_row.get("traffic_clients", []):
                session_key = build_session_key(profile, client)
                if session_key in seen_keys:
                    continue
                seen_keys.add(session_key)

                current_rx = int(client.get("bytes_received") or 0)
                current_tx = int(client.get("bytes_sent") or 0)
                common_name = (client.get("common_name") or "-").strip()
                is_antizapret = str(profile).startswith("antizapret")
                is_wireguard = str(profile).endswith("-wg")
                protocol_type = "wireguard" if is_wireguard else "openvpn"

                # Real last-connection time reported by the protocol (WireGuard
                # handshake); OpenVPN clients in the status are connected right
                # now, so they fall back to scan time.
                client_seen = _parse_status_timestamp(client.get("last_seen_iso"), now)

                session_state = sessions.get(session_key)
                is_new = session_state is None
                was_inactive = bool(session_state and not session_state.is_active)

                connected_ts = int(client.get("connected_since_ts") or 0)
                if is_wireguard and connected_ts <= 0:
                    connected_ts = int(client_seen.timestamp())

                if is_new:
                    session_state = TrafficSessionState(
                        node_id=self.node_id,
                        session_key=session_key,
                        profile=profile,
                        common_name=common_name,
                        real_address=(client.get("real_address") or "").strip() or None,
                        virtual_address=(client.get("virtual_address") or "").strip() or None,
                        connected_since_ts=connected_ts,
                        last_bytes_received=current_rx,
                        last_bytes_sent=current_tx,
                        is_active=True,
                        last_seen_at=client_seen,
                    )
                    self.db.add(session_state)
                    sessions[session_key] = session_state
                    if is_wireguard:
                        delta_rx, delta_tx = 0, 0
                    else:
                        delta_rx, delta_tx = max(current_rx, 0), max(current_tx, 0)
                else:
                    delta_rx = current_rx - int(session_state.last_bytes_received or 0)
                    delta_tx = current_tx - int(session_state.last_bytes_sent or 0)
                    if delta_rx < 0:
                        delta_rx = max(current_rx, 0)
                    if delta_tx < 0:
                        delta_tx = max(current_tx, 0)
                    session_state.last_bytes_received = current_rx
                    session_state.last_bytes_sent = current_tx
                    session_state.last_seen_at = client_seen
                    if is_wireguard and (was_inactive or int(session_state.connected_since_ts or 0) <= 0):
                        session_state.connected_since_ts = connected_ts
                    session_state.is_active = True
                    session_state.ended_at = None

                stat_key = (common_name, protocol_type)
                user_stat = stats.get(stat_key)
                if user_stat is None:
                    user_stat = UserTrafficStatProtocol(
                        node_id=self.node_id,
                        common_name=common_name,
                        protocol_type=protocol_type,
                        first_seen_at=client_seen,
                        last_seen_at=client_seen,
                    )
                    self.db.add(user_stat)
                    stats[stat_key] = user_stat

                user_stat.total_received = int(user_stat.total_received or 0) + max(delta_rx, 0)
                user_stat.total_sent = int(user_stat.total_sent or 0) + max(delta_tx, 0)

                if max(delta_rx, 0) > 0 or max(delta_tx, 0) > 0:
                    self.db.add(UserTrafficSample(
                        node_id=self.node_id,
                        common_name=common_name,
                        network_type="antizapret" if is_antizapret else "vpn",
                        protocol_type=protocol_type,
                        delta_received=max(delta_rx, 0),
                        delta_sent=max(delta_tx, 0),
                        created_at=now,
                    ))
                    samples_added += 1

                if is_antizapret:
                    user_stat.total_received_antizapret = int(user_stat.total_received_antizapret or 0) + max(delta_rx, 0)
                    user_stat.total_sent_antizapret = int(user_stat.total_sent_antizapret or 0) + max(delta_tx, 0)
                else:
                    user_stat.total_received_vpn = int(user_stat.total_received_vpn or 0) + max(delta_rx, 0)
                    user_stat.total_sent_vpn = int(user_stat.total_sent_vpn or 0) + max(delta_tx, 0)
                user_stat.last_seen_at = (
                    client_seen
                    if user_stat.last_seen_at is None
                    else max(user_stat.last_seen_at, client_seen)
                )
                if is_new:
                    user_stat.total_sessions = int(user_stat.total_sessions or 0) + 1

        for session_key, session_state in sessions.items():
            if session_key in seen_keys or session_key not in previously_active:
                continue
            if session_state.is_active:
                session_state.is_active = False
                session_state.ended_at = now

        self.db.commit()
        return {"samples_added": samples_added, "active_sessions": len(seen_keys)}

    def get_summary(
        self,
        active_names: set[str],
        stale_seconds: int = 600,
        *,
        node_ids: list[int] | None = None,
        ha_info: VpnConfigHaInfo | None = None,
        node_names: dict[int, str] | None = None,
        active_by_node: dict[int, set[str]] | None = None,
    ) -> tuple[list[TrafficClientRow], TrafficSummary]:
        """Aggregate persisted traffic stats into per-client rows.

        When ``node_ids`` spans more than one node (an HA Sync Group), rows for
        the same logical client (``common_name`` + ``protocol_type``, matched
        case-insensitively) are summed across nodes and tagged with ``ha`` /
        ``ha_aggregated`` metadata plus a per-node breakdown.
        """
        now = datetime.utcnow()
        scope_ids = node_ids or [self.node_id]
        node_names = node_names or {}

        def _node_active(node_id: int, name: str) -> bool:
            if active_by_node is not None:
                return name in active_by_node.get(node_id, set())
            return name in active_names

        stats = (
            self.db.query(UserTrafficStatProtocol)
            .filter(UserTrafficStatProtocol.node_id.in_(scope_ids))
            .order_by(UserTrafficStatProtocol.total_received.desc())
            .all()
        )

        recent_usage = self._recent_usage(scope_ids)

        aggregates: dict[tuple[str, str], dict] = {}
        order: list[tuple[str, str]] = []

        for row in stats:
            client_lower = (row.common_name or "").lower()
            protocol = row.protocol_type
            key = (client_lower, protocol)
            agg = aggregates.get(key)
            if agg is None:
                agg = {
                    "display_name": row.common_name,
                    "display_bytes": -1,
                    "protocol_type": protocol,
                    "rx": 0,
                    "tx": 0,
                    "rx_vpn": 0,
                    "tx_vpn": 0,
                    "rx_az": 0,
                    "tx_az": 0,
                    "traffic_1d": 0,
                    "traffic_7d": 0,
                    "traffic_30d": 0,
                    "total_sessions": 0,
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "is_active": False,
                    "breakdown": [],
                }
                aggregates[key] = agg
                order.append(key)

            rx = int(row.total_received or 0)
            tx = int(row.total_sent or 0)
            row_total = rx + tx
            if row_total > agg["display_bytes"]:
                agg["display_bytes"] = row_total
                agg["display_name"] = row.common_name

            agg["rx"] += rx
            agg["tx"] += tx
            agg["rx_vpn"] += int(row.total_received_vpn or 0)
            agg["tx_vpn"] += int(row.total_sent_vpn or 0)
            agg["rx_az"] += int(row.total_received_antizapret or 0)
            agg["tx_az"] += int(row.total_sent_antizapret or 0)
            agg["total_sessions"] += int(row.total_sessions or 0)

            recent = recent_usage.get((row.node_id, client_lower, protocol), {})
            node_1d = int(recent.get("days_1", 0))
            node_7d = int(recent.get("days_7", 0))
            node_30d = int(recent.get("days_30", 0))
            agg["traffic_1d"] += node_1d
            agg["traffic_7d"] += node_7d
            agg["traffic_30d"] += node_30d

            if row.first_seen_at is not None:
                if agg["first_seen_at"] is None or row.first_seen_at < agg["first_seen_at"]:
                    agg["first_seen_at"] = row.first_seen_at
            if row.last_seen_at is not None:
                if agg["last_seen_at"] is None or row.last_seen_at > agg["last_seen_at"]:
                    agg["last_seen_at"] = row.last_seen_at

            node_active = _node_active(row.node_id, row.common_name)
            if node_active:
                agg["is_active"] = True

            if ha_info is not None:
                agg["breakdown"].append(
                    {
                        "node_id": row.node_id,
                        "node_name": node_names.get(row.node_id) or f"node-{row.node_id}",
                        "total_bytes": row_total,
                        "traffic_7d": node_7d,
                        "is_active": node_active,
                    }
                )

        rows_out: list[TrafficClientRow] = []
        total_rx = total_tx = 0
        total_rx_vpn = total_tx_vpn = 0
        total_rx_az = total_tx_az = 0

        for key in order:
            agg = aggregates[key]
            rx = agg["rx"]
            tx = agg["tx"]
            rx_vpn = agg["rx_vpn"]
            tx_vpn = agg["tx_vpn"]
            rx_az = agg["rx_az"]
            tx_az = agg["tx_az"]
            total_rx += rx
            total_tx += tx
            total_rx_vpn += rx_vpn
            total_tx_vpn += tx_vpn
            total_rx_az += rx_az
            total_tx_az += tx_az

            breakdown = None
            if ha_info is not None and agg["breakdown"]:
                breakdown = [
                    TrafficHaNodeBreakdown(**item)
                    for item in sorted(
                        agg["breakdown"], key=lambda i: i["total_bytes"], reverse=True
                    )
                ]

            rows_out.append(
                TrafficClientRow(
                    common_name=agg["display_name"],
                    protocol_type=agg["protocol_type"],
                    total_received=rx,
                    total_sent=tx,
                    total_bytes=rx + tx,
                    total_received_vpn=rx_vpn,
                    total_sent_vpn=tx_vpn,
                    total_bytes_vpn=rx_vpn + tx_vpn,
                    total_received_antizapret=rx_az,
                    total_sent_antizapret=tx_az,
                    total_bytes_antizapret=rx_az + tx_az,
                    traffic_1d=agg["traffic_1d"],
                    traffic_7d=agg["traffic_7d"],
                    traffic_30d=agg["traffic_30d"],
                    total_sessions=agg["total_sessions"],
                    first_seen_at=agg["first_seen_at"].isoformat() if agg["first_seen_at"] else None,
                    last_seen_at=agg["last_seen_at"].isoformat() if agg["last_seen_at"] else None,
                    is_active=agg["is_active"],
                    ha=ha_info,
                    ha_aggregated=ha_info is not None,
                    ha_node_breakdown=breakdown,
                )
            )

        latest_sample = (
            self.db.query(func.max(UserTrafficSample.created_at))
            .filter(UserTrafficSample.node_id.in_(scope_ids))
            .scalar()
        )
        db_age_seconds = None
        if latest_sample:
            db_age_seconds = max(int((now - latest_sample).total_seconds()), 0)

        summary = TrafficSummary(
            users_count=len(rows_out),
            active_users_count=sum(1 for r in rows_out if r.is_active),
            total_received=total_rx,
            total_sent=total_tx,
            total_received_vpn=total_rx_vpn,
            total_sent_vpn=total_tx_vpn,
            total_received_antizapret=total_rx_az,
            total_sent_antizapret=total_tx_az,
            latest_sample_at=latest_sample.isoformat() if latest_sample else None,
            db_age_seconds=db_age_seconds,
            db_is_stale=db_age_seconds is not None and db_age_seconds > stale_seconds,
        )
        return rows_out, summary

    def _recent_usage(self, node_ids: list[int] | None = None) -> dict:
        now = datetime.utcnow()
        scope_ids = node_ids or [self.node_id]
        since_1d = now - timedelta(days=1)
        since_7d = now - timedelta(days=7)
        since_30d = now - timedelta(days=30)

        delta = func.coalesce(UserTrafficSample.delta_received, 0) + func.coalesce(
            UserTrafficSample.delta_sent, 0
        )
        common_name_lower = func.lower(UserTrafficSample.common_name)

        rows = (
            self.db.query(
                UserTrafficSample.node_id,
                common_name_lower.label("cn"),
                UserTrafficSample.protocol_type,
                func.sum(case((UserTrafficSample.created_at >= since_1d, delta), else_=0)).label("days_1"),
                func.sum(case((UserTrafficSample.created_at >= since_7d, delta), else_=0)).label("days_7"),
                func.sum(case((UserTrafficSample.created_at >= since_30d, delta), else_=0)).label("days_30"),
            )
            .filter(
                UserTrafficSample.node_id.in_(scope_ids),
                UserTrafficSample.created_at >= since_30d,
            )
            .group_by(
                UserTrafficSample.node_id,
                common_name_lower,
                UserTrafficSample.protocol_type,
            )
            .all()
        )

        result: dict[tuple[int, str, str], dict[str, int]] = {}
        for row in rows:
            key = (row.node_id, row.cn or "", row.protocol_type)
            result[key] = {
                "days_1": int(row.days_1 or 0),
                "days_7": int(row.days_7 or 0),
                "days_30": int(row.days_30 or 0),
            }
        return result

    def reset_traffic(self, scope: str = "all") -> int:
        q_samples = self.db.query(UserTrafficSample).filter(UserTrafficSample.node_id == self.node_id)
        q_sessions = self.db.query(TrafficSessionState).filter(TrafficSessionState.node_id == self.node_id)
        q_stats = self.db.query(UserTrafficStatProtocol).filter(UserTrafficStatProtocol.node_id == self.node_id)

        if scope == "openvpn":
            q_samples = q_samples.filter(UserTrafficSample.protocol_type == "openvpn")
            q_stats = q_stats.filter(UserTrafficStatProtocol.protocol_type == "openvpn")
        elif scope == "wireguard":
            q_samples = q_samples.filter(UserTrafficSample.protocol_type == "wireguard")
            q_stats = q_stats.filter(UserTrafficStatProtocol.protocol_type == "wireguard")

        deleted = q_samples.delete(synchronize_session=False)
        q_sessions.delete(synchronize_session=False)
        q_stats.delete(synchronize_session=False)
        self.db.commit()
        return deleted


def collect_traffic_snapshot_for_node(db: Session, node_id: int) -> dict:
    """Fetch live status from node adapter and persist traffic snapshot (best-effort)."""
    from app.services.node_manager import get_adapter_for_node

    node = db.get(Node, node_id)
    if node is None:
        return {"samples_added": 0, "active_sessions": 0, "skipped": True}

    adapter = get_adapter_for_node(node)
    status_rows = build_status_rows(adapter.parse_openvpn_status(), adapter.parse_wireguard_status())
    collector = TrafficCollectorService(db, node_id)
    result = collector.persist_snapshot(status_rows)
    result["skipped"] = False
    return result
