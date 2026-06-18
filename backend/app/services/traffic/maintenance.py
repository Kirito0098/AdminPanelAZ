"""Traffic DB maintenance (ported from AdminAntizapret traffic_maintenance.py)."""

from __future__ import annotations

import glob
import os
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import TrafficSessionState, UserTrafficSample, UserTrafficStatProtocol, VpnConfig, VpnType
from app.services.traffic.collector import (
    _parse_status_timestamp,
    build_session_key,
    build_status_rows,
)


def normalize_traffic_protocol_scope(protocol_scope: str | None) -> str:
    scope = (protocol_scope or "all").strip().lower()
    if scope not in ("all", "openvpn", "wireguard"):
        return "all"
    return scope


def normalize_traffic_client_identity(raw_name: str | None) -> str:
    return (raw_name or "").strip().lower()


def _profile_matches_protocol_scope(profile: str | None, protocol_scope: str) -> bool:
    scope = normalize_traffic_protocol_scope(protocol_scope)
    is_wireguard_profile = str(profile or "").strip().lower().endswith("-wg")
    if scope == "wireguard":
        return is_wireguard_profile
    if scope == "openvpn":
        return not is_wireguard_profile
    return True


class TrafficMaintenanceService:
    def __init__(self, db: Session, node_id: int):
        self.db = db
        self.node_id = node_id

    def collect_config_protocols_by_client(self) -> dict[str, set[str]]:
        protocols_by_client: dict[str, set[str]] = defaultdict(set)
        rows = self.db.query(VpnConfig).filter(VpnConfig.node_id == self.node_id).all()
        for row in rows:
            name = (row.client_name or "").strip()
            if not name:
                continue
            if row.vpn_type == VpnType.wireguard:
                protocols_by_client[name.lower()].add("WireGuard")
            else:
                protocols_by_client[name.lower()].add("OpenVPN")
        return dict(protocols_by_client)

    def collect_existing_config_client_names(self) -> set[str]:
        names: set[str] = set()
        for row in self.db.query(VpnConfig.client_name).filter(VpnConfig.node_id == self.node_id).distinct():
            identity = normalize_traffic_client_identity(row[0])
            if identity:
                names.add(identity)
        return names

    def collect_wireguard_only_client_names_lower(self) -> set[str]:
        protocols_by_client = self.collect_config_protocols_by_client()
        result: set[str] = set()
        for client_name, protocols in protocols_by_client.items():
            normalized = {str(protocol or "").strip() for protocol in protocols if str(protocol or "").strip()}
            if normalized == {"WireGuard"}:
                if client_name:
                    result.add(client_name)
        return result

    def collect_status_rows_for_snapshot(self, adapter) -> list[dict]:
        ovpn = adapter.parse_openvpn_status()
        wg = adapter.parse_wireguard_status()
        return build_status_rows(ovpn, wg)

    def get_deleted_persisted_traffic_rows(self) -> tuple[list[dict], dict]:
        existing = self.collect_existing_config_client_names()
        stats = (
            self.db.query(UserTrafficStatProtocol)
            .filter(UserTrafficStatProtocol.node_id == self.node_id)
            .order_by(UserTrafficStatProtocol.total_received.desc())
            .all()
        )

        deleted_rows: list[dict] = []
        total_bytes = 0
        seen: set[tuple[str, str]] = set()

        for row in stats:
            identity = normalize_traffic_client_identity(row.common_name)
            if not identity or identity in existing:
                continue
            key = (row.common_name, row.protocol_type)
            if key in seen:
                continue
            seen.add(key)
            total = int(row.total_received or 0) + int(row.total_sent or 0)
            total_bytes += total
            deleted_rows.append({
                "common_name": row.common_name,
                "protocol_type": row.protocol_type,
                "total_received": int(row.total_received or 0),
                "total_sent": int(row.total_sent or 0),
                "total_bytes": total,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            })

        summary = {
            "users_count": len({r["common_name"] for r in deleted_rows}),
            "rows_count": len(deleted_rows),
            "total_bytes": total_bytes,
        }
        return deleted_rows, summary

    def get_never_connected_config_rows(
        self,
        allowed_client_names: set[str] | None = None,
    ) -> tuple[list[dict], dict]:
        stats_keys: set[tuple[str, str]] = set()
        for row in self.db.query(UserTrafficStatProtocol).filter(
            UserTrafficStatProtocol.node_id == self.node_id
        ).all():
            identity = normalize_traffic_client_identity(row.common_name)
            proto = (row.protocol_type or "").strip().lower()
            if identity and proto:
                stats_keys.add((identity, proto))

        configs = (
            self.db.query(VpnConfig)
            .filter(
                VpnConfig.node_id == self.node_id,
                VpnConfig.ha_primary_config_id.is_(None),
            )
            .order_by(VpnConfig.client_name.asc(), VpnConfig.vpn_type.asc())
            .all()
        )

        rows_out: list[dict] = []
        for cfg in configs:
            name = (cfg.client_name or "").strip()
            identity = normalize_traffic_client_identity(name)
            if not identity:
                continue
            if allowed_client_names is not None and name not in allowed_client_names:
                continue
            proto = "wireguard" if cfg.vpn_type == VpnType.wireguard else "openvpn"
            if (identity, proto) in stats_keys:
                continue
            rows_out.append({
                "common_name": name,
                "protocol_type": proto,
                "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
                "config_id": cfg.id,
            })

        summary = {
            "users_count": len({r["common_name"] for r in rows_out}),
            "rows_count": len(rows_out),
        }
        return rows_out, summary

    def delete_persisted_traffic_rows_by_scope(self, protocol_scope: str) -> dict:
        scope = normalize_traffic_protocol_scope(protocol_scope)

        if scope == "all":
            deleted_samples = (
                self.db.query(UserTrafficSample)
                .filter(UserTrafficSample.node_id == self.node_id)
                .delete(synchronize_session=False)
            )
            deleted_sessions = (
                self.db.query(TrafficSessionState)
                .filter(TrafficSessionState.node_id == self.node_id)
                .delete(synchronize_session=False)
            )
            return {
                "scope": scope,
                "deleted_samples": int(deleted_samples or 0),
                "deleted_sessions": int(deleted_sessions or 0),
            }

        if scope == "openvpn":
            deleted_samples = (
                self.db.query(UserTrafficSample)
                .filter(
                    UserTrafficSample.node_id == self.node_id,
                    UserTrafficSample.protocol_type == "openvpn",
                )
                .delete(synchronize_session=False)
            )
            deleted_sessions = (
                self.db.query(TrafficSessionState)
                .filter(
                    TrafficSessionState.node_id == self.node_id,
                    ~TrafficSessionState.profile.like("%-wg"),
                )
                .delete(synchronize_session=False)
            )
            return {
                "scope": scope,
                "deleted_samples": int(deleted_samples or 0),
                "deleted_sessions": int(deleted_sessions or 0),
            }

        wireguard_only_clients = self.collect_wireguard_only_client_names_lower()
        sample_query = self.db.query(UserTrafficSample).filter(UserTrafficSample.node_id == self.node_id)
        if wireguard_only_clients:
            sample_query = sample_query.filter(
                (UserTrafficSample.protocol_type == "wireguard")
                | (
                    (UserTrafficSample.protocol_type != "wireguard")
                    & func.lower(UserTrafficSample.common_name).in_(sorted(wireguard_only_clients))
                )
            )
        else:
            sample_query = sample_query.filter(UserTrafficSample.protocol_type == "wireguard")

        deleted_samples = sample_query.delete(synchronize_session=False)
        deleted_sessions = (
            self.db.query(TrafficSessionState)
            .filter(
                TrafficSessionState.node_id == self.node_id,
                TrafficSessionState.profile.like("%-wg"),
            )
            .delete(synchronize_session=False)
        )
        return {
            "scope": scope,
            "deleted_samples": int(deleted_samples or 0),
            "deleted_sessions": int(deleted_sessions or 0),
        }

    def seed_traffic_session_baseline_for_scope(
        self,
        status_rows: list[dict],
        protocol_scope: str,
        now: datetime | None = None,
    ) -> dict:
        scope = normalize_traffic_protocol_scope(protocol_scope)
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)

        sessions_by_key = {
            row.session_key: row
            for row in self.db.query(TrafficSessionState)
            .filter(TrafficSessionState.node_id == self.node_id)
            .all()
        }

        seen_scope_keys: set[str] = set()
        seeded_users: set[str] = set()
        inserted_sessions = 0
        updated_sessions = 0
        deactivated_sessions = 0

        for status_row in status_rows or []:
            profile = status_row.get("profile", "unknown")
            if not _profile_matches_protocol_scope(profile, scope):
                continue

            for client in status_row.get("traffic_clients", status_row.get("clients", [])):
                common_name = (client.get("common_name") or "-").strip()
                if not common_name or common_name == "-":
                    continue

                session_key = build_session_key(profile, client)
                if session_key in seen_scope_keys:
                    continue
                seen_scope_keys.add(session_key)

                current_rx = int(client.get("bytes_received") or 0)
                current_tx = int(client.get("bytes_sent") or 0)
                client_seen = _parse_status_timestamp(client.get("last_seen_iso"), now)

                session_state = sessions_by_key.get(session_key)
                if session_state is None:
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
                        last_seen_at=client_seen,
                        ended_at=None,
                    )
                    self.db.add(session_state)
                    sessions_by_key[session_key] = session_state
                    inserted_sessions += 1
                else:
                    session_state.profile = profile
                    session_state.common_name = common_name
                    session_state.real_address = (client.get("real_address") or "").strip() or None
                    session_state.virtual_address = (client.get("virtual_address") or "").strip() or None
                    session_state.connected_since_ts = int(client.get("connected_since_ts") or 0)
                    session_state.last_bytes_received = current_rx
                    session_state.last_bytes_sent = current_tx
                    session_state.is_active = True
                    session_state.last_seen_at = client_seen
                    session_state.ended_at = None
                    updated_sessions += 1

                seeded_users.add(common_name)

        for session_key, session_state in sessions_by_key.items():
            if not _profile_matches_protocol_scope(session_state.profile, scope):
                continue
            if session_key in seen_scope_keys:
                continue
            if session_state.is_active:
                session_state.is_active = False
                session_state.ended_at = now
                deactivated_sessions += 1

        return {
            "scope": scope,
            "seeded_users": seeded_users,
            "active_sessions": len(seen_scope_keys),
            "inserted_sessions": inserted_sessions,
            "updated_sessions": updated_sessions,
            "deactivated_sessions": deactivated_sessions,
        }

    def rebuild_user_traffic_stats_from_samples(
        self,
        seed_users: set[str] | None = None,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.query(UserTrafficStatProtocol).filter(
            UserTrafficStatProtocol.node_id == self.node_id
        ).delete(synchronize_session=False)

        stats_map_by_protocol: dict[tuple[str, str], dict] = {}
        wireguard_only_clients = self.collect_wireguard_only_client_names_lower()

        samples = (
            self.db.query(UserTrafficSample)
            .filter(UserTrafficSample.node_id == self.node_id)
            .order_by(UserTrafficSample.created_at.asc())
            .all()
        )

        for sample in samples:
            common_name = (sample.common_name or "").strip()
            if not common_name:
                continue

            protocol = (sample.protocol_type or "openvpn").strip().lower()
            if protocol not in ("openvpn", "wireguard"):
                protocol = "openvpn"
            if protocol == "openvpn" and common_name.strip().lower() in wireguard_only_clients:
                protocol = "wireguard"

            sample_dt = sample.created_at or now
            protocol_key = (common_name, protocol)
            protocol_stat = stats_map_by_protocol.get(protocol_key)
            if protocol_stat is None:
                protocol_stat = {
                    "total_received": 0,
                    "total_sent": 0,
                    "total_received_vpn": 0,
                    "total_sent_vpn": 0,
                    "total_received_antizapret": 0,
                    "total_sent_antizapret": 0,
                    "first_seen_at": sample_dt,
                    "last_seen_at": sample_dt,
                }
                stats_map_by_protocol[protocol_key] = protocol_stat

            delta_rx = max(int(sample.delta_received or 0), 0)
            delta_tx = max(int(sample.delta_sent or 0), 0)
            network_type = (sample.network_type or "vpn").strip().lower()

            protocol_stat["total_received"] += delta_rx
            protocol_stat["total_sent"] += delta_tx
            if network_type == "antizapret":
                protocol_stat["total_received_antizapret"] += delta_rx
                protocol_stat["total_sent_antizapret"] += delta_tx
            else:
                protocol_stat["total_received_vpn"] += delta_rx
                protocol_stat["total_sent_vpn"] += delta_tx
            if sample_dt < protocol_stat["first_seen_at"]:
                protocol_stat["first_seen_at"] = sample_dt
            if sample_dt > protocol_stat["last_seen_at"]:
                protocol_stat["last_seen_at"] = sample_dt

        for (common_name, protocol_type), stat in stats_map_by_protocol.items():
            self.db.add(
                UserTrafficStatProtocol(
                    node_id=self.node_id,
                    common_name=common_name,
                    protocol_type=protocol_type,
                    total_received=stat["total_received"],
                    total_sent=stat["total_sent"],
                    total_received_vpn=stat["total_received_vpn"],
                    total_sent_vpn=stat["total_sent_vpn"],
                    total_received_antizapret=stat["total_received_antizapret"],
                    total_sent_antizapret=stat["total_sent_antizapret"],
                    total_sessions=0,
                    first_seen_at=stat["first_seen_at"] or now,
                    last_seen_at=stat["last_seen_at"] or now,
                )
            )

        seeded_only = 0
        seed_names = sorted({(name or "").strip() for name in (seed_users or set()) if (name or "").strip()})
        seed_protocols_by_name: dict[str, set[str]] = defaultdict(set)
        if seed_names:
            seed_sessions = (
                self.db.query(TrafficSessionState)
                .filter(
                    TrafficSessionState.node_id == self.node_id,
                    TrafficSessionState.common_name.in_(seed_names),
                )
                .all()
            )
            for state_row in seed_sessions:
                protocol_type = (
                    "wireguard" if str(state_row.profile or "").strip().lower().endswith("-wg") else "openvpn"
                )
                seed_protocols_by_name[(state_row.common_name or "").strip()].add(protocol_type)

        active_identities = {
            normalize_traffic_client_identity(name)
            for name, _ in stats_map_by_protocol
        }
        for common_name in seed_names:
            if normalize_traffic_client_identity(common_name) in active_identities:
                continue
            for protocol_type in sorted(seed_protocols_by_name.get(common_name, {"openvpn"})):
                if (common_name, protocol_type) in stats_map_by_protocol:
                    continue
                self.db.add(
                    UserTrafficStatProtocol(
                        node_id=self.node_id,
                        common_name=common_name,
                        protocol_type=protocol_type,
                        total_received=0,
                        total_sent=0,
                        total_received_vpn=0,
                        total_sent_vpn=0,
                        total_received_antizapret=0,
                        total_sent_antizapret=0,
                        total_sessions=0,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                seeded_only += 1

        return {
            "rebuilt_users": len({name for name, _ in stats_map_by_protocol}),
            "rebuilt_users_protocol_rows": len(stats_map_by_protocol),
            "seeded_only_users": seeded_only,
        }

    def reset_persisted_traffic_data(self, protocol_scope: str, adapter) -> tuple[bool, str, dict]:
        scope = normalize_traffic_protocol_scope(protocol_scope)
        scope_human = {
            "all": "вся статистика",
            "openvpn": "OpenVPN",
            "wireguard": "WireGuard/AWG",
        }

        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            status_rows = self.collect_status_rows_for_snapshot(adapter)

            deleted_info = self.delete_persisted_traffic_rows_by_scope(scope)
            stats_query = self.db.query(UserTrafficStatProtocol).filter(
                UserTrafficStatProtocol.node_id == self.node_id
            )
            if scope == "openvpn":
                stats_query = stats_query.filter(UserTrafficStatProtocol.protocol_type == "openvpn")
            elif scope == "wireguard":
                stats_query = stats_query.filter(UserTrafficStatProtocol.protocol_type == "wireguard")
            stats_query.delete(synchronize_session=False)

            baseline_info = self.seed_traffic_session_baseline_for_scope(status_rows, scope, now=now)
            rebuilt_info = self.rebuild_user_traffic_stats_from_samples(
                seed_users=baseline_info.get("seeded_users", set()),
                now=now,
            )
            self.db.commit()

            detail = {
                "deleted": deleted_info,
                "baseline": {
                    "active_sessions": baseline_info.get("active_sessions", 0),
                    "seeded_users": len(baseline_info.get("seeded_users", set())),
                },
                "rebuilt": rebuilt_info,
            }

            if scope == "all":
                message = (
                    "Накопленная статистика трафика очищена. "
                    f"Точка отсчёта: пользователей {len(baseline_info.get('seeded_users', set()))}, "
                    f"активных сессий {baseline_info.get('active_sessions', 0)}."
                )
            else:
                message = (
                    f"Статистика {scope_human.get(scope, scope)} очищена. "
                    f"Удалено samples={deleted_info.get('deleted_samples', 0)}, "
                    f"sessions={deleted_info.get('deleted_sessions', 0)}. "
                    f"Baseline активных сессий: {baseline_info.get('active_sessions', 0)}."
                )
            return True, message, detail
        except Exception as exc:
            self.db.rollback()
            return False, f"Ошибка сброса статистики трафика: {exc}", {}

    def delete_client_traffic_stats(self, common_name: str) -> tuple[bool, str]:
        target_name = (common_name or "").strip()
        if not target_name:
            return False, "Не указано имя клиента."

        target_identity = normalize_traffic_client_identity(target_name)
        names_to_delete: set[str] = {target_name}

        for (stored_name,) in (
            self.db.query(UserTrafficStatProtocol.common_name)
            .filter(UserTrafficStatProtocol.node_id == self.node_id)
            .distinct()
            .all()
        ):
            candidate = (stored_name or "").strip()
            if candidate and normalize_traffic_client_identity(candidate) == target_identity:
                names_to_delete.add(candidate)

        normalized_names = sorted({name.lower() for name in names_to_delete if name})

        def _name_in_target_set(column):
            return func.lower(func.trim(column)).in_(normalized_names)

        try:
            deleted_samples = (
                self.db.query(UserTrafficSample)
                .filter(
                    UserTrafficSample.node_id == self.node_id,
                    _name_in_target_set(UserTrafficSample.common_name),
                )
                .delete(synchronize_session=False)
            )
            deleted_sessions = (
                self.db.query(TrafficSessionState)
                .filter(
                    TrafficSessionState.node_id == self.node_id,
                    _name_in_target_set(TrafficSessionState.common_name),
                )
                .delete(synchronize_session=False)
            )
            deleted_protocol_stats = (
                self.db.query(UserTrafficStatProtocol)
                .filter(
                    UserTrafficStatProtocol.node_id == self.node_id,
                    _name_in_target_set(UserTrafficStatProtocol.common_name),
                )
                .delete(synchronize_session=False)
            )
            self.db.commit()

            deleted_total = int(deleted_samples or 0) + int(deleted_sessions or 0) + int(deleted_protocol_stats or 0)
            if deleted_total == 0:
                return False, f"Для клиента '{target_name}' статистика не найдена."

            return True, (
                f"Статистика клиента '{target_name}' удалена "
                f"(stat_protocol={int(deleted_protocol_stats or 0)}, "
                f"sessions={int(deleted_sessions or 0)}, samples={int(deleted_samples or 0)})."
            )
        except Exception as exc:
            self.db.rollback()
            return False, f"Ошибка удаления статистики: {exc}"


def cleanup_openvpn_status_logs_now(logs_dir: str = "/etc/openvpn/server/logs") -> tuple[bool, str]:
    pattern = os.path.join(logs_dir, "*.log")
    deleted = 0
    failed: list[str] = []

    for file_path in glob.glob(pattern):
        try:
            if os.path.isfile(file_path) and not file_path.endswith("-status.log"):
                os.remove(file_path)
                deleted += 1
        except OSError:
            failed.append(os.path.basename(file_path))

    if failed:
        return False, f"Удалено обычных .log: {deleted}. Ошибки: {', '.join(failed)}"
    return True, f"Удалено обычных .log (без *-status.log): {deleted}"
