"""Client block/expiry policies for OpenVPN and WireGuard (ported from AdminAntizapret 1.9.0)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import OpenVpnAccessPolicy, WgAccessPolicy
from app.services.node_adapter import NodeAdapter
from app.services.openvpn_ban_hook import ensure_openvpn_ban_check
from app.services.traffic_limit import (
    TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED,
    TrafficLimitExceededError,
    get_client_consumed_traffic_bytes,
    human_bytes,
    resolve_traffic_limit_state,
)
from app.services.wg_runtime import block_client_runtime, unblock_client_runtime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class AccessPolicyService:
    def __init__(
        self,
        db: Session,
        *,
        antizapret_path,
        node_id: int | None = None,
        adapter: NodeAdapter | None = None,
    ):
        self.db = db
        self.node_id = node_id
        self._adapter = adapter
        self.banned_clients_file = antizapret_path / "config" / "banned_clients"
        self.wg_runtime_calls = 0

    def _require_node_id(self) -> int:
        if self.node_id is None:
            raise ValueError("node_id is required for access policy DB operations")
        return self.node_id

    def _consumed_bytes(self, client_name: str, *, period_days: int | None = None) -> int:
        return get_client_consumed_traffic_bytes(
            self.db,
            client_name=client_name,
            node_id=self.node_id,
            period_days=period_days,
            normalize_identity=lambda name: (name or "").strip().lower(),
        )

    def _ovpn_traffic_state(self, row: OpenVpnAccessPolicy | None, *, client_name: str | None = None) -> dict:
        if row is None:
            name = (client_name or "").strip()
            consumed = self._consumed_bytes(name, period_days=None) if name else 0
            return resolve_traffic_limit_state(
                traffic_limit_bytes=None,
                traffic_limit_period_days=None,
                consumed_bytes=consumed,
            )
        consumed = self._consumed_bytes(row.client_name, period_days=row.traffic_limit_period_days)
        return resolve_traffic_limit_state(
            traffic_limit_bytes=row.traffic_limit_bytes,
            traffic_limit_period_days=row.traffic_limit_period_days,
            consumed_bytes=consumed,
        )

    def _wg_traffic_state(self, row: WgAccessPolicy | None, *, client_name: str | None = None) -> dict:
        if row is None:
            name = (client_name or "").strip().lower()
            consumed = self._consumed_bytes(name, period_days=None) if name else 0
            return resolve_traffic_limit_state(
                traffic_limit_bytes=None,
                traffic_limit_period_days=None,
                consumed_bytes=consumed,
            )
        consumed = self._consumed_bytes(row.client_name, period_days=row.traffic_limit_period_days)
        return resolve_traffic_limit_state(
            traffic_limit_bytes=row.traffic_limit_bytes,
            traffic_limit_period_days=row.traffic_limit_period_days,
            consumed_bytes=consumed,
        )

    def _traffic_human_fields(self, traffic_state: dict) -> dict:
        return {
            **traffic_state,
            "traffic_consumed_human": human_bytes(traffic_state.get("traffic_consumed_bytes")),
            "traffic_bytes_left_human": human_bytes(traffic_state.get("traffic_bytes_left")),
        }

    def read_banned_clients(self) -> set[str]:
        if self._adapter is not None:
            content = self._adapter.read_config_file("banned_clients")
            banned: set[str] = set()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    banned.add(line)
            return banned
        if not self.banned_clients_file.exists():
            return set()
        banned: set[str] = set()
        for line in self.banned_clients_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                banned.add(line)
        return banned

    def write_banned_clients(self, clients: set[str]) -> None:
        ordered = sorted(clients, key=str.lower)
        content = "\n".join(ordered) + ("\n" if ordered else "")
        if self._adapter is not None:
            self._adapter.write_config_file("banned_clients", content)
            self._adapter.ensure_openvpn_ban_check()
            return
        self.banned_clients_file.parent.mkdir(parents=True, exist_ok=True)
        self.banned_clients_file.write_text(content, encoding="utf-8")
        ensure_openvpn_ban_check(self.banned_clients_file.parent.parent)

    # ── OpenVPN ──────────────────────────────────────────────────────────

    def _get_ovpn(self, client_name: str) -> OpenVpnAccessPolicy:
        node_id = self._require_node_id()
        row = (
            self.db.query(OpenVpnAccessPolicy)
            .filter_by(node_id=node_id, client_name=client_name)
            .first()
        )
        if row is None:
            row = OpenVpnAccessPolicy(node_id=node_id, client_name=client_name)
            self.db.add(row)
            self.db.flush()
        return row

    def _ovpn_state(self, row: OpenVpnAccessPolicy, now: datetime | None = None) -> dict:
        now = _as_utc(now) or _now()
        block_until = _as_utc(row.block_until)
        temp = bool(row.is_temp_blocked and block_until and block_until > now)
        perm = bool(row.is_permanent_blocked)
        traffic_state = self._ovpn_traffic_state(row)
        traffic_exceeded = bool(traffic_state.get("traffic_limit_exceeded"))
        blocked = temp or perm or traffic_exceeded
        if perm:
            block_mode = "permanent"
        elif temp:
            block_mode = "temp"
        elif traffic_exceeded:
            block_mode = "traffic_limit"
        else:
            block_mode = "none"
        return {
            "is_blocked": blocked,
            "block_mode": block_mode,
            "blocked_days_left": (block_until - now).days if temp and block_until else None,
            "block_duration_days": row.block_days,
            "block_until": block_until.strftime("%Y-%m-%d %H:%M:%S") if block_until else None,
            "traffic_limit_exceeded": traffic_exceeded,
            **self._traffic_human_fields(traffic_state),
        }

    def _cleanup_ovpn_temp_block(self, row: OpenVpnAccessPolicy, now: datetime) -> bool:
        if row.is_temp_blocked and row.block_until and _as_utc(row.block_until) <= now:
            row.is_temp_blocked = False
            row.block_until = None
            row.block_days = None
            if row.block_reason == "manual_temp":
                row.block_reason = None
            row.block_started_at = None
            return True
        return False

    def _cleanup_ovpn_traffic_limit(self, row: OpenVpnAccessPolicy, traffic_state: dict, *, traffic_limit_changed: bool = False) -> bool:
        traffic_exceeded = bool(traffic_state.get("traffic_limit_exceeded"))
        changed = False
        if traffic_exceeded:
            if row.is_permanent_blocked and not row.is_temp_blocked and not (row.updated_by or "").strip():
                row.is_permanent_blocked = False
                row.block_started_at = None
                row.block_days = None
                row.block_until = None
                changed = True
            return changed
        if row.block_reason == "traffic_limit":
            row.block_started_at = None
            row.block_days = None
            row.block_until = None
            changed = True
        if traffic_limit_changed and not traffic_exceeded and row.is_permanent_blocked and not row.is_temp_blocked:
            row.is_permanent_blocked = False
            row.block_started_at = None
            row.block_days = None
            row.block_until = None
            changed = True
        return changed

    def reconcile_openvpn(self, client_name: str, *, traffic_limit_changed: bool = False) -> None:
        node_id = self._require_node_id()
        row = (
            self.db.query(OpenVpnAccessPolicy)
            .filter_by(node_id=node_id, client_name=client_name)
            .first()
        )
        banned = self.read_banned_clients()
        if row is None:
            if client_name in banned:
                banned.discard(client_name)
                self.write_banned_clients(banned)
            return
        now = _now()
        changed = self._cleanup_ovpn_temp_block(row, now)
        traffic_state = self._ovpn_traffic_state(row)
        if self._cleanup_ovpn_traffic_limit(row, traffic_state, traffic_limit_changed=traffic_limit_changed):
            changed = True
        state = self._ovpn_state(row, now)
        if row.block_reason != (state["block_mode"] if state["is_blocked"] else None):
            row.block_reason = state["block_mode"] if state["is_blocked"] else None
            changed = True
        if state["is_blocked"]:
            banned.add(client_name)
        else:
            banned.discard(client_name)
        if changed:
            self.db.commit()
        else:
            self.db.flush()
        self.write_banned_clients(banned)

    def openvpn_temp_block(self, client_name: str, days: int, *, actor: str | None = None) -> dict:
        row = self._get_ovpn(client_name)
        now = _now()
        row.is_temp_blocked = True
        row.is_permanent_blocked = False
        row.block_reason = "manual_temp"
        row.block_started_at = now
        row.block_days = days
        row.block_until = now + timedelta(days=days)
        row.updated_by = actor
        self.db.commit()
        self.reconcile_openvpn(client_name)
        return self._ovpn_state(row)

    def openvpn_permanent_block(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_ovpn(client_name)
        now = _now()
        row.is_temp_blocked = False
        row.is_permanent_blocked = True
        row.block_reason = "manual_permanent"
        row.block_started_at = now
        row.block_days = None
        row.block_until = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_openvpn(client_name)
        return self._ovpn_state(row)

    def openvpn_unblock(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_ovpn(client_name)
        traffic_state = self._ovpn_traffic_state(row)
        if traffic_state.get("traffic_limit_exceeded"):
            raise TrafficLimitExceededError()
        row.is_temp_blocked = False
        row.is_permanent_blocked = False
        row.block_reason = None
        row.block_started_at = None
        row.block_days = None
        row.block_until = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_openvpn(client_name)
        return self._ovpn_state(row)

    def openvpn_set_traffic_limit(
        self,
        client_name: str,
        limit_bytes: int,
        *,
        period_days: int | None = None,
        actor: str | None = None,
    ) -> dict:
        if int(limit_bytes) < 1:
            raise ValueError("Лимит трафика должен быть не меньше 1 байта")
        row = self._get_ovpn(client_name)
        row.traffic_limit_bytes = int(limit_bytes)
        if period_days is not None:
            if int(period_days) not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
                raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.")
            row.traffic_limit_period_days = int(period_days)
        else:
            row.traffic_limit_period_days = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_openvpn(client_name, traffic_limit_changed=True)
        return self._ovpn_state(row)

    def openvpn_clear_traffic_limit(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_ovpn(client_name)
        row.traffic_limit_bytes = None
        row.traffic_limit_period_days = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_openvpn(client_name, traffic_limit_changed=True)
        return self._ovpn_state(row)

    def get_openvpn_policy(self, client_name: str) -> dict:
        node_id = self._require_node_id()
        row = (
            self.db.query(OpenVpnAccessPolicy)
            .filter_by(node_id=node_id, client_name=client_name)
            .first()
        )
        if row is None:
            traffic_state = self._ovpn_traffic_state(None, client_name=client_name)
            return {
                "is_blocked": client_name in self.read_banned_clients(),
                "block_mode": "none",
                **self._traffic_human_fields(traffic_state),
            }
        return self._ovpn_state(row)

    # ── WireGuard ────────────────────────────────────────────────────────

    def _get_wg(self, client_name: str) -> WgAccessPolicy:
        normalized = client_name.strip().lower()
        node_id = self._require_node_id()
        row = (
            self.db.query(WgAccessPolicy)
            .filter_by(node_id=node_id, client_name=normalized)
            .first()
        )
        if row is None:
            row = WgAccessPolicy(node_id=node_id, client_name=normalized)
            self.db.add(row)
            self.db.flush()
        return row

    def _wg_target_reason(self, state: dict) -> str | None:
        if not state["is_blocked"]:
            return None
        mode = state["block_mode"]
        if mode == "expired":
            return "expired"
        if mode == "permanent":
            return "manual_permanent"
        if mode == "temp":
            return "manual_temp"
        if mode == "traffic_limit":
            return "traffic_limit"
        return None

    def _cleanup_wg_temp_block(self, row: WgAccessPolicy, now: datetime) -> bool:
        if row.is_temp_blocked and row.block_until and _as_utc(row.block_until) <= now:
            row.is_temp_blocked = False
            row.block_until = None
            row.block_days = None
            if row.block_reason == "manual_temp":
                row.block_reason = None
            row.block_started_at = None
            return True
        return False

    def _apply_wg_client_runtime(self, client_name: str, *, is_blocked: bool) -> dict | None:
        self.wg_runtime_calls += 1
        normalized = client_name.strip().lower()
        if self._adapter is not None:
            if is_blocked:
                return self._adapter.block_wireguard_client_runtime(normalized)
            return self._adapter.unblock_wireguard_client_runtime(normalized)
        if is_blocked:
            return block_client_runtime(normalized)
        return unblock_client_runtime(normalized)

    def _reapply_all_blocked_runtime(self, *, exclude_client: str | None = None) -> list[dict]:
        now = _now()
        node_id = self._require_node_id()
        excluded = (exclude_client or "").strip().lower()
        results: list[dict] = []
        for row in self.db.query(WgAccessPolicy).filter_by(node_id=node_id).all():
            if excluded and row.client_name == excluded:
                continue
            state = self._wg_state(row, now)
            if not state["is_blocked"]:
                continue
            results.append(
                {
                    "client_name": row.client_name,
                    "result": self._apply_wg_client_runtime(row.client_name, is_blocked=True),
                }
            )
        return results

    def _wg_state(self, row: WgAccessPolicy, now: datetime | None = None) -> dict:
        now = _as_utc(now) or _now()
        expires = _as_utc(row.expires_at)
        block_until = _as_utc(row.block_until)
        expired = bool(expires and expires <= now)
        temp = bool(row.is_temp_blocked and block_until and block_until > now)
        perm = bool(row.is_permanent_blocked)
        traffic_state = self._wg_traffic_state(row)
        traffic_exceeded = bool(traffic_state.get("traffic_limit_exceeded"))
        blocked = expired or temp or perm or traffic_exceeded
        if expired:
            block_mode = "expired"
        elif perm:
            block_mode = "permanent"
        elif temp:
            block_mode = "temp"
        elif traffic_exceeded:
            block_mode = "traffic_limit"
        else:
            block_mode = "none"
        return {
            "is_blocked": blocked,
            "block_mode": block_mode,
            "expired": expired,
            "access_days_left": (expires - now).days if expires and expires > now else None,
            "blocked_days_left": (block_until - now).days if temp and block_until else None,
            "block_until": block_until.strftime("%Y-%m-%d %H:%M:%S") if block_until else None,
            "expires_at": expires.isoformat() if expires else None,
            "traffic_limit_exceeded": traffic_exceeded,
            **self._traffic_human_fields(traffic_state),
        }

    def reconcile_wg(
        self,
        client_name: str,
        *,
        apply_runtime: bool = True,
        force_runtime: bool = False,
        traffic_limit_changed: bool = False,
    ) -> None:
        normalized = client_name.strip().lower()
        node_id = self._require_node_id()
        row = (
            self.db.query(WgAccessPolicy)
            .filter_by(node_id=node_id, client_name=normalized)
            .first()
        )
        if row is None:
            return
        now = _now()
        before_blocked = bool(self._wg_state(row, now)["is_blocked"])
        before_reason = row.block_reason
        self._cleanup_wg_temp_block(row, now)
        traffic_state = self._wg_traffic_state(row)
        if row.block_reason == "traffic_limit" and not traffic_state.get("traffic_limit_exceeded"):
            row.block_reason = None
        state = self._wg_state(row, now)
        if state["is_blocked"] and state["block_mode"] == "traffic_limit":
            row.block_reason = "traffic_limit"
        elif row.block_reason == "traffic_limit" and not state["is_blocked"]:
            row.block_reason = None
        if traffic_limit_changed and not state["traffic_limit_exceeded"] and row.is_permanent_blocked and not row.is_temp_blocked:
            row.is_permanent_blocked = False
            row.block_reason = None
        state = self._wg_state(row, now)
        target_reason = self._wg_target_reason(state)
        if row.block_reason != target_reason:
            row.block_reason = target_reason
        after_blocked = bool(state["is_blocked"])
        after_reason = row.block_reason
        runtime_changed = before_blocked != after_blocked or before_reason != after_reason
        if apply_runtime and (runtime_changed or force_runtime):
            self._apply_wg_client_runtime(normalized, is_blocked=after_blocked)
            if not after_blocked:
                self._reapply_all_blocked_runtime(exclude_client=normalized)
        self.db.commit()

    def wg_set_expiry(self, client_name: str, days: int, *, extend: bool = False, actor: str | None = None) -> dict:
        row = self._get_wg(client_name)
        now = _now()
        base = now
        existing = _as_utc(row.expires_at)
        if extend and existing and existing > now:
            base = existing
        row.expires_at = base + timedelta(days=days)
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name, force_runtime=True)
        return self._wg_state(row)

    def wg_temp_block(self, client_name: str, days: int, *, actor: str | None = None) -> dict:
        row = self._get_wg(client_name)
        now = _now()
        row.is_temp_blocked = True
        row.is_permanent_blocked = False
        row.block_reason = "manual_temp"
        row.block_started_at = now
        row.block_days = days
        row.block_until = now + timedelta(days=days)
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name, force_runtime=True)
        return self._wg_state(row)

    def wg_permanent_block(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_wg(client_name)
        now = _now()
        row.is_temp_blocked = False
        row.is_permanent_blocked = True
        row.block_reason = "manual_permanent"
        row.block_started_at = now
        row.block_days = None
        row.block_until = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name, force_runtime=True)
        return self._wg_state(row)

    def wg_unblock(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_wg(client_name)
        if self._wg_state(row)["expired"]:
            raise ValueError("Клиент отключён по истечении срока. Продлите срок доступа.")
        traffic_state = self._wg_traffic_state(row)
        if traffic_state.get("traffic_limit_exceeded"):
            raise TrafficLimitExceededError()
        row.is_temp_blocked = False
        row.is_permanent_blocked = False
        row.block_reason = None
        row.block_started_at = None
        row.block_days = None
        row.block_until = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name, force_runtime=True)
        return self._wg_state(row)

    def wg_set_traffic_limit(
        self,
        client_name: str,
        limit_bytes: int,
        *,
        period_days: int | None = None,
        actor: str | None = None,
    ) -> dict:
        if int(limit_bytes) < 1:
            raise ValueError("Лимит трафика должен быть не меньше 1 байта")
        row = self._get_wg(client_name)
        row.traffic_limit_bytes = int(limit_bytes)
        if period_days is not None:
            if int(period_days) not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
                raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.")
            row.traffic_limit_period_days = int(period_days)
        else:
            row.traffic_limit_period_days = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name, traffic_limit_changed=True, force_runtime=True)
        return self._wg_state(row)

    def wg_clear_traffic_limit(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_wg(client_name)
        row.traffic_limit_bytes = None
        row.traffic_limit_period_days = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name, traffic_limit_changed=True, force_runtime=True)
        return self._wg_state(row)

    def get_wg_policy(self, client_name: str) -> dict:
        normalized = client_name.strip().lower()
        node_id = self._require_node_id()
        row = (
            self.db.query(WgAccessPolicy)
            .filter_by(node_id=node_id, client_name=normalized)
            .first()
        )
        if row is None:
            traffic_state = self._wg_traffic_state(None, client_name=normalized)
            return {
                "is_blocked": False,
                "block_mode": "none",
                **self._traffic_human_fields(traffic_state),
            }
        return self._wg_state(row)

    def get_all_policies(self, client_names: list[str]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for name in client_names:
            ovpn = self.get_openvpn_policy(name)
            wg = self.get_wg_policy(name)
            result[name] = {"openvpn": ovpn, "wireguard": wg}
        return result

    def reconcile_all_wg_policies(
        self,
        *,
        apply_runtime: bool = True,
        node_id: int | None = None,
        sync_all_runtime: bool = False,
    ) -> dict:
        target_node = node_id if node_id is not None else self.node_id
        if target_node is None:
            return {
                "wg_policy_reconcile": "skipped",
                "node_id": None,
                "blocked_clients": [],
                "unblocked_clients": [],
                "changed_clients": [],
                "clients_total": 0,
                "clients_changed": 0,
                "wg_runtime_calls": 0,
                "runtime": {"blocked": [], "unblocked": []},
            }

        now = _now()
        changed = False
        blocked_clients: list[str] = []
        unblocked_clients: list[str] = []
        changed_runtime_clients: list[tuple[str, bool]] = []

        self.wg_runtime_calls = 0
        rows = self.db.query(WgAccessPolicy).filter_by(node_id=target_node).all()
        for row in rows:
            before_blocked = bool(self._wg_state(row, now)["is_blocked"])
            before_reason = row.block_reason
            if self._cleanup_wg_temp_block(row, now):
                changed = True
            traffic_state = self._wg_traffic_state(row)
            if row.block_reason == "traffic_limit" and not traffic_state.get("traffic_limit_exceeded"):
                row.block_reason = None
                changed = True
            state = self._wg_state(row, now)
            target_reason = self._wg_target_reason(state)
            if row.block_reason != target_reason:
                row.block_reason = target_reason
                changed = True
            after_blocked = bool(state["is_blocked"])
            after_reason = row.block_reason
            if before_blocked != after_blocked or before_reason != after_reason:
                changed_runtime_clients.append((row.client_name, after_blocked))
            if after_blocked:
                blocked_clients.append(row.client_name)
            else:
                unblocked_clients.append(row.client_name)

        if changed:
            self.db.commit()

        runtime: dict[str, list] = {"blocked": [], "unblocked": []}
        runtime_targets: list[tuple[str, bool]] = []
        if apply_runtime:
            if sync_all_runtime:
                runtime_targets = [(name, False) for name in unblocked_clients]
                runtime_targets.extend((name, True) for name in blocked_clients)
            else:
                runtime_targets = list(changed_runtime_clients)

        applied_unblock = False
        for client_name, is_blocked in runtime_targets:
            result = self._apply_wg_client_runtime(client_name, is_blocked=is_blocked)
            bucket = "blocked" if is_blocked else "unblocked"
            runtime[bucket].append({"client_name": client_name, "result": result})
            if not is_blocked:
                applied_unblock = True

        if apply_runtime and applied_unblock and not sync_all_runtime:
            for item in self._reapply_all_blocked_runtime():
                runtime["blocked"].append(item)

        return {
            "wg_policy_reconcile": "ok",
            "node_id": target_node,
            "blocked_clients": blocked_clients,
            "unblocked_clients": unblocked_clients,
            "changed_clients": [name for name, _ in changed_runtime_clients],
            "clients_total": len(rows),
            "clients_changed": len(changed_runtime_clients),
            "wg_runtime_calls": self.wg_runtime_calls,
            "runtime": runtime,
        }

    def reconcile_all_traffic_limits(self, *, node_id: int | None = None) -> dict:
        target_node = node_id if node_id is not None else self.node_id
        if target_node is None:
            return {
                "traffic_limit_reconcile": "skipped",
                "changed": 0,
                "node_id": None,
                "clients_total": 0,
                "clients_changed": 0,
                "wg_runtime_calls": 0,
            }
        self.wg_runtime_calls = 0
        changed = 0
        wg_rows = self.db.query(WgAccessPolicy).filter_by(node_id=target_node).all()
        ovpn_rows = self.db.query(OpenVpnAccessPolicy).filter_by(node_id=target_node).all()
        for row in ovpn_rows:
            before = row.block_reason
            self.reconcile_openvpn(row.client_name)
            after_row = (
                self.db.query(OpenVpnAccessPolicy)
                .filter_by(node_id=target_node, client_name=row.client_name)
                .first()
            )
            if after_row and after_row.block_reason != before:
                changed += 1
        for row in wg_rows:
            before = row.block_reason
            self.reconcile_wg(row.client_name, apply_runtime=True)
            after_row = (
                self.db.query(WgAccessPolicy)
                .filter_by(node_id=target_node, client_name=row.client_name)
                .first()
            )
            if after_row and after_row.block_reason != before:
                changed += 1
        return {
            "traffic_limit_reconcile": "ok",
            "changed": changed,
            "node_id": target_node,
            "clients_total": len(ovpn_rows) + len(wg_rows),
            "clients_changed": changed,
            "wg_runtime_calls": self.wg_runtime_calls,
        }
