"""IP whitelist and scanner blocking settings (simplified port from AdminAntizapret)."""

import ipaddress
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services.env_file import EnvFileService
from app.services.firewall_tools_check import check_firewall_tools
from app.services.panel_port_firewall import panel_port_firewall
from app.services.panel_publish_info import is_whitelist_port_firewall_applicable
from app.services.public_download_settings import is_public_download_enabled, set_public_download_enabled


def _get(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


class SecurityService:
    def _env_file(self) -> EnvFileService:
        from pathlib import Path

        env_path = Path(__file__).resolve().parents[2] / ".env"
        return EnvFileService(env_path)

    def _firewall_whitelist_entries(self, settings: dict) -> list[str]:
        entries = list(settings.get("allowed_ips") or [])
        for row in settings.get("temp_whitelist") or []:
            ip = (row.get("ip") if isinstance(row, dict) else None) or ""
            ip = str(ip).strip()
            if ip:
                entries.append(ip)
        return entries

    def is_whitelist_port_firewall_active(self, db: Session) -> bool:
        settings = self.get_settings(db)
        return (
            bool(settings.get("ip_restriction_enabled"))
            and bool(settings.get("whitelist_firewall"))
            and self.is_whitelist_port_firewall_applicable()
        )

    def is_whitelist_port_firewall_applicable(self) -> bool:
        env = self._env_file()
        return is_whitelist_port_firewall_applicable(get_env_value=env.get_env_value)

    def get_settings(self, db: Session) -> dict:
        allowed_raw = _get(db, "security_allowed_ips", "")
        allowed = [ip.strip() for ip in allowed_raw.split(",") if ip.strip()]
        temp_raw = _get(db, "security_temp_whitelist", "[]")
        try:
            temp_list = json.loads(temp_raw)
        except json.JSONDecodeError:
            temp_list = []
        now = datetime.now(timezone.utc)
        active_temp = [
            e for e in temp_list
            if datetime.fromisoformat(e["expires_at"].replace("Z", "+00:00")) > now
        ]
        fw_status = check_firewall_tools()
        applicable = self.is_whitelist_port_firewall_applicable()
        whitelist_firewall = _get(db, "security_whitelist_firewall", "false") == "true"
        result = {
            "ip_restriction_enabled": _get(db, "security_ip_restriction", "false") == "true",
            "allowed_ips": allowed,
            "block_scanners": _get(db, "security_block_scanners", "false") == "true",
            "scanner_max_attempts": int(_get(db, "security_scanner_max_attempts", "5") or "5"),
            "scanner_ban_seconds": int(_get(db, "security_scanner_ban_seconds", "3600") or "3600"),
            "temp_whitelist": active_temp,
            "qr_download_ttl_seconds": int(_get(db, "qr_download_ttl_seconds", "600") or "600"),
            "qr_download_max_downloads": int(_get(db, "qr_download_max_downloads", "1") or "1"),
            "qr_download_pin_set": bool(_get(db, "qr_download_pin", "")),
            "public_download_enabled": is_public_download_enabled(db),
            "whitelist_firewall": whitelist_firewall,
            "whitelist_firewall_applicable": applicable,
            "whitelist_firewall_active": False,
            "firewall_tools_ready": fw_status.fully_ready,
            "firewall_tools_detail": fw_status.operational_detail,
        }
        result["whitelist_firewall_active"] = (
            bool(result["ip_restriction_enabled"])
            and bool(result["whitelist_firewall"])
            and applicable
        )
        return result

    def update_settings(self, db: Session, payload: dict) -> dict:
        if "ip_restriction_enabled" in payload:
            _set(db, "security_ip_restriction", "true" if payload["ip_restriction_enabled"] else "false")
        if "allowed_ips" in payload:
            validated = []
            for ip in payload["allowed_ips"]:
                ip = ip.strip()
                if not ip:
                    continue
                try:
                    ipaddress.ip_network(ip, strict=False)
                    validated.append(ip)
                except ValueError:
                    continue
            _set(db, "security_allowed_ips", ",".join(validated))
        if "block_scanners" in payload:
            _set(db, "security_block_scanners", "true" if payload["block_scanners"] else "false")
        if "scanner_max_attempts" in payload:
            _set(db, "security_scanner_max_attempts", str(max(1, min(20, int(payload["scanner_max_attempts"])))))
        if "scanner_ban_seconds" in payload:
            _set(db, "security_scanner_ban_seconds", str(max(60, min(86400, int(payload["scanner_ban_seconds"])))))
        if "qr_download_ttl_seconds" in payload:
            _set(db, "qr_download_ttl_seconds", str(max(60, min(3600, int(payload["qr_download_ttl_seconds"])))))
        if "qr_download_max_downloads" in payload:
            val = int(payload["qr_download_max_downloads"])
            _set(db, "qr_download_max_downloads", str(val if val in (1, 3, 5) else 1))
        if "qr_download_pin" in payload:
            _set(db, "qr_download_pin", (payload["qr_download_pin"] or "").strip())
        if "public_download_enabled" in payload:
            set_public_download_enabled(db, bool(payload["public_download_enabled"]))
        if "whitelist_firewall" in payload:
            requested = bool(payload["whitelist_firewall"])
            if requested and not self.is_whitelist_port_firewall_applicable():
                requested = False
            _set(db, "security_whitelist_firewall", "true" if requested else "false")
        db.commit()
        return self.get_settings(db)

    def sync_whitelist_port_firewall(self, db: Session) -> bool:
        settings = self.get_settings(db)
        try:
            if not self.is_whitelist_port_firewall_applicable():
                if settings.get("whitelist_firewall"):
                    _set(db, "security_whitelist_firewall", "false")
                    db.commit()
                panel_port_firewall.disable()
                return False

            if not self.is_whitelist_port_firewall_active(db):
                panel_port_firewall.disable()
                return False

            entries = self._firewall_whitelist_entries(settings)
            return panel_port_firewall.sync(entries)
        except Exception:
            return False

    def add_temp_whitelist(self, db: Session, ip: str, hours: int) -> dict:
        try:
            ipaddress.ip_address(ip.strip())
        except ValueError as exc:
            raise ValueError("Некорректный IP-адрес") from exc
        temp_raw = _get(db, "security_temp_whitelist", "[]")
        try:
            temp_list = json.loads(temp_raw)
        except json.JSONDecodeError:
            temp_list = []
        expires = datetime.now(timezone.utc) + timedelta(hours=hours)
        temp_list.append({"ip": ip.strip(), "expires_at": expires.isoformat(), "hours": hours})
        _set(db, "security_temp_whitelist", json.dumps(temp_list))
        db.commit()
        return self.get_settings(db)

    def remove_temp_whitelist(self, db: Session, ip: str) -> dict:
        ip = ip.strip()
        temp_raw = _get(db, "security_temp_whitelist", "[]")
        try:
            temp_list = json.loads(temp_raw)
        except json.JSONDecodeError:
            temp_list = []
        temp_list = [e for e in temp_list if e.get("ip") != ip]
        _set(db, "security_temp_whitelist", json.dumps(temp_list))
        db.commit()
        return self.get_settings(db)

    def is_ip_allowed(self, db: Session, client_ip: str) -> bool:
        settings = self.get_settings(db)
        if not settings["ip_restriction_enabled"]:
            return True
        if not settings["allowed_ips"]:
            return True
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        for entry in settings["allowed_ips"] + [e["ip"] for e in settings["temp_whitelist"]]:
            try:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                elif addr == ipaddress.ip_address(entry):
                    return True
            except ValueError:
                continue
        return False
