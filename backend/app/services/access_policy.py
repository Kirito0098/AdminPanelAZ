"""Client block/expiry policies for OpenVPN and WireGuard (ported from AdminAntizapret)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import OpenVpnAccessPolicy, WgAccessPolicy
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
    def __init__(self, db: Session, *, antizapret_path):
        self.db = db
        self.banned_clients_file = antizapret_path / "config" / "banned_clients"
        self.client_connect_script = antizapret_path / "client-connect.sh"
        self._ban_check_block = (
            '# BEGIN adminpanel ban check\n'
            'if [ -f /root/antizapret/config/banned_clients ]; then\n'
            '  if grep -qxF "$common_name" /root/antizapret/config/banned_clients 2>/dev/null; then\n'
            '    echo "Client $common_name is banned" >&2\n'
            '    exit 1\n'
            '  fi\n'
            'fi\n'
            '# END adminpanel ban check'
        )

    def read_banned_clients(self) -> set[str]:
        if not self.banned_clients_file.exists():
            return set()
        banned: set[str] = set()
        for line in self.banned_clients_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                banned.add(line)
        return banned

    def write_banned_clients(self, clients: set[str]) -> None:
        self.banned_clients_file.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(clients, key=str.lower)
        content = "\n".join(ordered) + ("\n" if ordered else "")
        self.banned_clients_file.write_text(content, encoding="utf-8")
        self._ensure_ban_check_block()

    def _ensure_ban_check_block(self) -> None:
        if not self.client_connect_script.exists():
            return
        content = self.client_connect_script.read_text(encoding="utf-8", errors="replace")
        if self._ban_check_block in content:
            return
        if content.startswith("#!"):
            idx = content.find("\n")
            if idx == -1:
                new_content = content + "\n\n" + self._ban_check_block + "\n"
            else:
                new_content = content[: idx + 1] + "\n" + self._ban_check_block + "\n" + content[idx + 1 :].lstrip("\n")
        else:
            new_content = self._ban_check_block + "\n" + content.lstrip("\n")
        self.client_connect_script.write_text(new_content, encoding="utf-8")

    # ── OpenVPN ──────────────────────────────────────────────────────────

    def _get_ovpn(self, client_name: str) -> OpenVpnAccessPolicy:
        row = self.db.query(OpenVpnAccessPolicy).filter_by(client_name=client_name).first()
        if row is None:
            row = OpenVpnAccessPolicy(client_name=client_name)
            self.db.add(row)
            self.db.flush()
        return row

    def _ovpn_state(self, row: OpenVpnAccessPolicy, now: datetime | None = None) -> dict:
        now = _as_utc(now) or _now()
        block_until = _as_utc(row.block_until)
        temp = bool(row.is_temp_blocked and block_until and block_until > now)
        perm = bool(row.is_permanent_blocked)
        blocked = temp or perm
        return {
            "is_blocked": blocked,
            "block_mode": "permanent" if perm else ("temp" if temp else "none"),
            "blocked_days_left": (block_until - now).days if temp and block_until else None,
            "block_duration_days": row.block_days,
        }

    def reconcile_openvpn(self, client_name: str) -> None:
        row = self.db.query(OpenVpnAccessPolicy).filter_by(client_name=client_name).first()
        banned = self.read_banned_clients()
        if row is None:
            if client_name in banned:
                banned.discard(client_name)
                self.write_banned_clients(banned)
            return
        now = _now()
        if row.is_temp_blocked and row.block_until and _as_utc(row.block_until) <= now:
            row.is_temp_blocked = False
            row.block_until = None
            row.block_days = None
            row.block_reason = None
        state = self._ovpn_state(row, now)
        if state["is_blocked"]:
            banned.add(client_name)
        else:
            banned.discard(client_name)
        self.write_banned_clients(banned)
        self.db.commit()

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

    def get_openvpn_policy(self, client_name: str) -> dict:
        row = self.db.query(OpenVpnAccessPolicy).filter_by(client_name=client_name).first()
        if row is None:
            return {"is_blocked": client_name in self.read_banned_clients(), "block_mode": "none"}
        return self._ovpn_state(row)

    # ── WireGuard ────────────────────────────────────────────────────────

    def _get_wg(self, client_name: str) -> WgAccessPolicy:
        normalized = client_name.strip().lower()
        row = self.db.query(WgAccessPolicy).filter_by(client_name=normalized).first()
        if row is None:
            row = WgAccessPolicy(client_name=normalized)
            self.db.add(row)
            self.db.flush()
        return row

    def _wg_state(self, row: WgAccessPolicy, now: datetime | None = None) -> dict:
        now = _as_utc(now) or _now()
        expires = _as_utc(row.expires_at)
        block_until = _as_utc(row.block_until)
        expired = bool(expires and expires <= now)
        temp = bool(row.is_temp_blocked and block_until and block_until > now)
        perm = bool(row.is_permanent_blocked)
        blocked = expired or temp or perm
        mode = "expired" if expired else ("permanent" if perm else ("temp" if temp else "none"))
        return {
            "is_blocked": blocked,
            "block_mode": mode,
            "expired": expired,
            "access_days_left": (expires - now).days if expires and expires > now else None,
            "blocked_days_left": (block_until - now).days if temp and block_until else None,
            "expires_at": expires.isoformat() if expires else None,
        }

    def reconcile_wg(self, client_name: str, *, apply_runtime: bool = True) -> None:
        normalized = client_name.strip().lower()
        row = self.db.query(WgAccessPolicy).filter_by(client_name=normalized).first()
        if row is None:
            return
        now = _now()
        if row.is_temp_blocked and row.block_until and _as_utc(row.block_until) <= now:
            row.is_temp_blocked = False
            row.block_until = None
            row.block_days = None
            row.block_reason = None
        state = self._wg_state(row, now)
        if apply_runtime:
            if state["is_blocked"]:
                block_client_runtime(normalized)
            else:
                unblock_client_runtime(normalized)
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
        self.reconcile_wg(client_name)
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
        self.reconcile_wg(client_name)
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
        self.reconcile_wg(client_name)
        return self._wg_state(row)

    def wg_unblock(self, client_name: str, *, actor: str | None = None) -> dict:
        row = self._get_wg(client_name)
        if self._wg_state(row)["expired"]:
            raise ValueError("Клиент отключён по истечении срока. Продлите срок доступа.")
        row.is_temp_blocked = False
        row.is_permanent_blocked = False
        row.block_reason = None
        row.block_started_at = None
        row.block_days = None
        row.block_until = None
        row.updated_by = actor
        self.db.commit()
        self.reconcile_wg(client_name)
        return self._wg_state(row)

    def get_wg_policy(self, client_name: str) -> dict:
        normalized = client_name.strip().lower()
        row = self.db.query(WgAccessPolicy).filter_by(client_name=normalized).first()
        if row is None:
            return {"is_blocked": False, "block_mode": "none"}
        return self._wg_state(row)

    def get_all_policies(self, client_names: list[str]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for name in client_names:
            ovpn = self.get_openvpn_policy(name)
            wg = self.get_wg_policy(name)
            result[name] = {"openvpn": ovpn, "wireguard": wg}
        return result
