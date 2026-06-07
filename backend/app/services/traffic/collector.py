"""Traffic snapshot collector and persistence (ported from AdminAntizapret)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import TrafficSessionState, UserTrafficSample, UserTrafficStatProtocol
from app.schemas import OpenVpnClient, WireGuardPeer


def _profile_from_log_name(log_name: str) -> str:
    base = log_name.replace("-status.log", "")
    return base


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
        if not peer.client_name:
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

                session_state = sessions.get(session_key)
                is_new = session_state is None

                if is_new:
                    session_state = TrafficSessionState(
                        node_id=self.node_id,
                        session_key=session_key,
                        profile=profile,
                        common_name=common_name,
                        real_address=(client.get("real_address") or "").strip() or None,
                        virtual_address=(client.get("virtual_address") or "").strip() or None,
                        connected_since_ts=int(client.get("connected_since_ts") or 0),
                        last_bytes_received=current_rx,
                        last_bytes_sent=current_tx,
                        is_active=True,
                        last_seen_at=now,
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
                    session_state.last_seen_at = now
                    session_state.is_active = True
                    session_state.ended_at = None

                stat_key = (common_name, protocol_type)
                user_stat = stats.get(stat_key)
                if user_stat is None:
                    user_stat = UserTrafficStatProtocol(
                        node_id=self.node_id,
                        common_name=common_name,
                        protocol_type=protocol_type,
                        first_seen_at=now,
                        last_seen_at=now,
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
                user_stat.last_seen_at = now
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

    def get_summary(self, active_names: set[str], stale_seconds: int = 600) -> tuple[list[dict], dict]:
        now = datetime.utcnow()
        rows_out: list[dict] = []

        stats = self.db.query(UserTrafficStatProtocol).filter(
            UserTrafficStatProtocol.node_id == self.node_id
        ).order_by(UserTrafficStatProtocol.total_received.desc()).all()

        recent_usage = self._recent_usage()

        total_rx = total_tx = 0
        total_rx_vpn = total_tx_vpn = 0
        total_rx_az = total_tx_az = 0

        for row in stats:
            rx = int(row.total_received or 0)
            tx = int(row.total_sent or 0)
            rx_vpn = int(row.total_received_vpn or 0)
            tx_vpn = int(row.total_sent_vpn or 0)
            rx_az = int(row.total_received_antizapret or 0)
            tx_az = int(row.total_sent_antizapret or 0)
            total_rx += rx
            total_tx += tx
            total_rx_vpn += rx_vpn
            total_tx_vpn += tx_vpn
            total_rx_az += rx_az
            total_tx_az += tx_az

            recent = recent_usage.get((row.common_name, row.protocol_type), {})
            is_active = row.common_name in active_names

            rows_out.append({
                "common_name": row.common_name,
                "protocol_type": row.protocol_type,
                "total_received": rx,
                "total_sent": tx,
                "total_bytes": rx + tx,
                "total_received_vpn": rx_vpn,
                "total_sent_vpn": tx_vpn,
                "total_bytes_vpn": rx_vpn + tx_vpn,
                "total_received_antizapret": rx_az,
                "total_sent_antizapret": tx_az,
                "total_bytes_antizapret": rx_az + tx_az,
                "traffic_1d": int(recent.get("days_1", 0)),
                "traffic_7d": int(recent.get("days_7", 0)),
                "traffic_30d": int(recent.get("days_30", 0)),
                "total_sessions": int(row.total_sessions or 0),
                "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "is_active": is_active,
            })

        latest_sample = self.db.query(func.max(UserTrafficSample.created_at)).filter(
            UserTrafficSample.node_id == self.node_id
        ).scalar()
        db_age_seconds = None
        if latest_sample:
            db_age_seconds = max(int((now - latest_sample).total_seconds()), 0)

        summary = {
            "users_count": len(rows_out),
            "active_users_count": sum(1 for r in rows_out if r["is_active"]),
            "total_received": total_rx,
            "total_sent": total_tx,
            "total_received_vpn": total_rx_vpn,
            "total_sent_vpn": total_tx_vpn,
            "total_received_antizapret": total_rx_az,
            "total_sent_antizapret": total_tx_az,
            "latest_sample_at": latest_sample.isoformat() if latest_sample else None,
            "db_age_seconds": db_age_seconds,
            "db_is_stale": db_age_seconds is not None and db_age_seconds > stale_seconds,
        }
        return rows_out, summary

    def _recent_usage(self) -> dict:
        now = datetime.utcnow()
        windows = {
            "days_1": now - timedelta(days=1),
            "days_7": now - timedelta(days=7),
            "days_30": now - timedelta(days=30),
        }
        result: dict[tuple[str, str], dict[str, int]] = {}

        for label, since in windows.items():
            samples = self.db.query(UserTrafficSample).filter(
                UserTrafficSample.node_id == self.node_id,
                UserTrafficSample.created_at >= since,
            ).all()
            for s in samples:
                key = (s.common_name, s.protocol_type)
                result.setdefault(key, {"days_1": 0, "days_7": 0, "days_30": 0})
                result[key][label] += int(s.delta_received or 0) + int(s.delta_sent or 0)

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
