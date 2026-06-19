"""AZ-WARP (WARPER) integration via warper_api on the VPN node."""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import HTTPException, status

from app.config import get_settings
from app.services.antizapret_settings import read_antizapret_settings

WARPER_BIN = Path("/usr/local/bin/warper")
WARPER_SCRIPT = Path("/root/warper/warper.sh")
WARPER_DIR = Path("/root/warper")
WARPER_API_DIR = WARPER_DIR / "py"
WARPER_API_INIT = WARPER_API_DIR / "warper_api" / "__init__.py"
WARPER_IP_RANGES_FILE = WARPER_DIR / "ip-ranges.txt"
WARPER_DOMAINS_FILE = WARPER_DIR / "domains.txt"
WARPER_TRAFFIC_FILE = WARPER_DIR / "traffic.json"
_BUILTIN_LIST_MARKERS = {
    "gemini": ("# --- GEMINI ---", "# --- END GEMINI ---"),
    "chatgpt": ("# --- CHATGPT ---", "# --- END CHATGPT ---"),
}

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


class WarperNotInstalledError(Exception):
    """WARPER is not installed on this node."""


class WarperConflictError(Exception):
    """ANTIZAPRET_WARP=y conflicts with WARPER domain routing."""


def detect_warper_installation() -> dict[str, Any]:
    """Probe standard AZ-WARP paths on the current machine (node agent host)."""
    bin_ok = WARPER_BIN.is_file()
    script_ok = WARPER_SCRIPT.is_file()
    api_ok = WARPER_API_INIT.is_file()
    missing: list[str] = []
    if not api_ok:
        missing.append("warper_api")
    if not bin_ok:
        missing.append("warper_bin")
    elif not WARPER_BIN.resolve().is_file():
        missing.append("warper_bin_broken_symlink")
    if script_ok and not bin_ok:
        missing.append("warper_symlink")
    return {
        "installed": api_ok and (bin_ok or script_ok),
        "warper_bin": bin_ok,
        "warper_script": script_ok,
        "warper_api": api_ok,
        "missing_components": missing,
    }


def is_warper_installed() -> bool:
    return bool(detect_warper_installation()["installed"])


def _antizapret_setup_path() -> Path:
    return get_settings().antizapret_path / "setup"


def _has_antizapret_warp_conflict() -> bool:
    settings = read_antizapret_settings(_antizapret_setup_path())
    return settings.get("ANTIZAPRET_WARP", "n").strip().lower() == "y"


def _ensure_installed() -> None:
    if not is_warper_installed():
        raise WarperNotInstalledError(
            "WARPER не установлен на узле. Установите AZ-WARP: "
            "curl -fsSL https://raw.githubusercontent.com/Liafanx/AZ-WARP/main/install.sh | bash"
        )


def _ensure_no_conflict() -> None:
    if _has_antizapret_warp_conflict():
        raise WarperConflictError(
            "ANTIZAPRET_WARP=y конфликтует с WARPER. Отключите встроенный WARP в «Конфиг AntiZapret»."
        )


def _normalize_cidr(cidr: str) -> str:
    value = (cidr or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный CIDR")
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Некорректный CIDR: {cidr}") from exc
    return str(network)


def _normalize_domain(domain: str) -> str:
    value = (domain or "").strip().lower()
    if not value or " " in value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный домен")
    if value.startswith("*."):
        value = value[2:]
    if not _DOMAIN_RE.match(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Некорректный домен: {domain}")
    return value


def _load_warper_api():
    api_path = str(WARPER_API_DIR)
    if api_path not in sys.path:
        sys.path.insert(0, api_path)
    from warper_api import WarperAPI  # noqa: PLC0415

    return WarperAPI()


def _result_or_raise(result: Any, *, default: Any = None) -> Any:
    """Normalize WarperResult or plain values from warper_api (some methods return str/int)."""
    if result is None:
        return default
    if isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, (list, dict)):
        return result
    ok = getattr(result, "ok", None)
    if ok is None:
        data = getattr(result, "data", None)
        return data if data is not None else result
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=getattr(result, "message", None) or "Ошибка WARPER",
        )
    if default is not None and result.data is None:
        return default
    return result.data if result.data is not None else {"message": result.message}


def _has_list_block(list_name: str, text: str | None = None) -> bool:
    marker = _BUILTIN_LIST_MARKERS.get(list_name)
    if not marker:
        return False
    if text is None:
        if not WARPER_DOMAINS_FILE.is_file():
            return False
        text = WARPER_DOMAINS_FILE.read_text(encoding="utf-8", errors="replace")
    return marker[0] in text


def get_domain_lists_status() -> dict[str, bool]:
    return {name: _has_list_block(name) for name in _BUILTIN_LIST_MARKERS}


def _parse_domains_file() -> list[dict[str, Any]]:
    if not WARPER_DOMAINS_FILE.is_file():
        return []
    has_gemini = _has_list_block("gemini")
    has_chatgpt = _has_list_block("chatgpt")
    items: list[dict[str, Any]] = []
    in_gemini = False
    in_chatgpt = False
    for raw_line in WARPER_DOMAINS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line == _BUILTIN_LIST_MARKERS["gemini"][0]:
            in_gemini, in_chatgpt = True, False
            continue
        if line == _BUILTIN_LIST_MARKERS["gemini"][1]:
            in_gemini = False
            continue
        if line == _BUILTIN_LIST_MARKERS["chatgpt"][0]:
            in_chatgpt, in_gemini = True, False
            continue
        if line == _BUILTIN_LIST_MARKERS["chatgpt"][1]:
            in_chatgpt = False
            continue
        if not line or line.startswith("#"):
            continue
        if in_gemini:
            items.append({"name": line, "domain": line, "type": "gemini", "enabled": has_gemini})
        elif in_chatgpt:
            items.append({"name": line, "domain": line, "type": "chatgpt", "enabled": has_chatgpt})
        else:
            items.append({"name": line, "domain": line, "type": "user", "enabled": True})
    return items


def _read_ip_ranges_file() -> list[str]:
    if not WARPER_IP_RANGES_FILE.is_file():
        return []
    ranges: list[str] = []
    for line in WARPER_IP_RANGES_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            ranges.append(value)
    return ranges


def _read_ip_ranges_file_text() -> str:
    if not WARPER_IP_RANGES_FILE.is_file():
        return ""
    return WARPER_IP_RANGES_FILE.read_text(encoding="utf-8", errors="replace")


def _extract_user_domains_text(text: str | None = None) -> str:
    if text is None:
        if not WARPER_DOMAINS_FILE.is_file():
            return "# Пользовательские домены:\n"
        text = WARPER_DOMAINS_FILE.read_text(encoding="utf-8", errors="replace")
    lines_out: list[str] = []
    in_gemini = False
    in_chatgpt = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == _BUILTIN_LIST_MARKERS["gemini"][0]:
            in_gemini, in_chatgpt = True, False
            continue
        if stripped == _BUILTIN_LIST_MARKERS["gemini"][1]:
            in_gemini = False
            continue
        if stripped == _BUILTIN_LIST_MARKERS["chatgpt"][0]:
            in_chatgpt, in_gemini = True, False
            continue
        if stripped == _BUILTIN_LIST_MARKERS["chatgpt"][1]:
            in_chatgpt = False
            continue
        if in_gemini or in_chatgpt:
            continue
        lines_out.append(line)
    body = "\n".join(lines_out).rstrip()
    return f"{body}\n" if body else "# Пользовательские домены:\n"


def _text_from_api_result(result: Any, *, fallback: str = "") -> str:
    if isinstance(result, str):
        return result
    unwrapped = _result_or_raise(result, default=fallback)
    if isinstance(unwrapped, str):
        return unwrapped
    if isinstance(unwrapped, dict):
        for key in ("text", "content", "data"):
            value = unwrapped.get(key)
            if isinstance(value, str):
                return value
    return fallback


def _normalize_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        items: list[str] = []
        for item in raw:
            if isinstance(item, str):
                items.append(item)
            elif isinstance(item, dict):
                for key in ("path", "name", "id", "key", "value"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        items.append(value)
                        break
        return items
    unwrapped = _result_or_raise(raw, default=[])
    return _normalize_string_list(unwrapped)


def build_user_domains_text_from_items(domains: list[Any]) -> str:
    lines = ["# Пользовательские домены:"]
    for item in domains:
        if isinstance(item, str):
            lines.append(item)
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {None, "user"}:
            continue
        domain = item.get("domain") or item.get("name")
        if isinstance(domain, str) and domain.strip():
            lines.append(domain.strip())
    body = "\n".join(lines).rstrip()
    return f"{body}\n"


def build_ip_ranges_text_from_items(ranges: list[Any]) -> str:
    lines: list[str] = []
    for item in ranges:
        if isinstance(item, str):
            value = item.strip()
            if value:
                lines.append(value)
            continue
        if not isinstance(item, dict):
            continue
        cidr = item.get("cidr") or item.get("range") or item.get("network")
        if isinstance(cidr, str) and cidr.strip():
            lines.append(cidr.strip())
    body = "\n".join(lines).rstrip()
    return f"{body}\n" if body else ""


def _http_exception_from_service(exc: Exception) -> HTTPException:
    if isinstance(exc, WarperNotInstalledError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, WarperConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def _read_traffic_hourly_map() -> dict[str, dict[str, int]]:
    if not WARPER_TRAFFIC_FILE.is_file():
        return {}
    try:
        raw = json.loads(WARPER_TRAFFIC_FILE.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    hourly = raw.get("hourly") if isinstance(raw, dict) else None
    if not isinstance(hourly, dict):
        return {}
    parsed: dict[str, dict[str, int]] = {}
    for key, value in hourly.items():
        if not isinstance(value, dict):
            continue
        try:
            parsed[str(key)] = {
                "rx": int(value.get("rx") or 0),
                "tx": int(value.get("tx") or 0),
            }
        except (TypeError, ValueError):
            continue
    return parsed


def _filter_traffic_hourly(hourly: dict[str, dict[str, int]], period: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items = sorted(hourly.items())
    if period == "today":
        prefix = now.strftime("%Y-%m-%dT")
        filtered = [(key, value) for key, value in items if key.startswith(prefix)]
    elif period == "week":
        cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H")
        filtered = [(key, value) for key, value in items if key >= cutoff]
    elif period == "month":
        cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H")
        filtered = [(key, value) for key, value in items if key >= cutoff]
    else:
        filtered = items
    return [{"ts": key, "rx": value["rx"], "tx": value["tx"]} for key, value in filtered]


def _format_traffic_chart_label(ts: str, period: str) -> str:
    if period == "today":
        hour = ts.split("T", 1)[1][:2] if "T" in ts else ts
        return f"{hour}:00"
    day = ts[:10]
    try:
        parsed = datetime.strptime(day, "%Y-%m-%d")
        return parsed.strftime("%d.%m")
    except ValueError:
        return day[5:]


def _chart_points_from_hourly(hourly_points: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    if not hourly_points:
        return []

    if period == "today":
        return [
            {
                "label": _format_traffic_chart_label(str(point["ts"]), period),
                "rx": int(point["rx"]),
                "tx": int(point["tx"]),
            }
            for point in hourly_points
        ]

    by_day: dict[str, dict[str, int]] = {}
    for point in hourly_points:
        day = str(point["ts"])[:10]
        bucket = by_day.setdefault(day, {"rx": 0, "tx": 0})
        bucket["rx"] += int(point["rx"])
        bucket["tx"] += int(point["tx"])

    return [
        {
            "label": _format_traffic_chart_label(day, period),
            "rx": values["rx"],
            "tx": values["tx"],
        }
        for day, values in sorted(by_day.items())
    ]


def _synthetic_traffic_chart(payload: dict[str, Any], period: str) -> list[dict[str, Any]]:
    rx = int(payload.get("period_rx") or payload.get("today_rx") or 0)
    tx = int(payload.get("period_tx") or payload.get("today_tx") or 0)
    if rx <= 0 and tx <= 0:
        return []
    labels = {"today": "Сегодня", "week": "Неделя", "month": "Месяц", "all": "Всё время"}
    return [{"label": labels.get(period, period), "rx": rx, "tx": tx}]


def _build_traffic_chart(period: str) -> list[dict[str, Any]]:
    hourly_points = _filter_traffic_hourly(_read_traffic_hourly_map(), period)
    return _chart_points_from_hourly(hourly_points, period)


def enrich_warper_traffic_payload(payload: dict[str, Any], period: str) -> dict[str, Any]:
    """Ensure chart data is present even when an older node agent omits it."""
    chart = payload.get("chart")
    if isinstance(chart, list) and chart:
        return payload

    hourly_points = payload.get("hourly_points")
    if isinstance(hourly_points, list) and hourly_points:
        rebuilt = _chart_points_from_hourly(hourly_points, period)
        if rebuilt:
            payload["chart"] = rebuilt
            return payload

    rebuilt = _build_traffic_chart(period)
    if rebuilt:
        payload["chart"] = rebuilt
        return payload

    synthetic = _synthetic_traffic_chart(payload, period)
    if synthetic:
        payload["chart"] = synthetic
    return payload


class WarperService:
    def __init__(self):
        self._api: Any | None = None

    def _api_client(self):
        _ensure_installed()
        if self._api is None:
            self._api = _load_warper_api()
        return self._api

    def is_installed(self) -> bool:
        return is_warper_installed()

    def get_health(self) -> dict[str, Any]:
        detection = detect_warper_installation()
        installed = bool(detection["installed"])
        conflict = _has_antizapret_warp_conflict()
        payload: dict[str, Any] = {
            "installed": installed,
            "active": False,
            "version": None,
            "conflict_antizapret_warp": conflict,
            "warper_bin": detection["warper_bin"],
            "warper_script": detection["warper_script"],
            "warper_api": detection["warper_api"],
            "missing_components": detection["missing_components"],
        }
        if not installed:
            return payload
        try:
            api = self._api_client()
            payload["version"] = getattr(api, "version", None) or _safe_version(api)
            payload["active"] = bool(api.is_active())
        except (WarperNotInstalledError, HTTPException):
            raise
        except Exception as exc:
            payload["health_error"] = str(exc)
        return payload

    def get_status(self) -> dict[str, Any]:
        api = self._api_client()
        return _result_or_raise(api.get_status(), default={})

    def doctor(self) -> list[dict[str, Any]]:
        api = self._api_client()
        raw = api.doctor()
        if hasattr(raw, "ok"):
            if isinstance(raw.data, list) and raw.data:
                return _normalize_doctor_checks(raw.data)
            stdout = getattr(raw, "raw_stdout", None) or ""
            if stdout:
                return _parse_doctor_stdout(stdout)
            if not raw.ok:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=getattr(raw, "message", None) or "Ошибка WARPER",
                )
            return []
        data = _result_or_raise(raw, default=[])
        if isinstance(data, list):
            return _normalize_doctor_checks(data)
        return _normalize_doctor_checks([data]) if data else []

    def toggle(self) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        return _result_or_raise(api.toggle(), default={"message": "OK"})

    def list_domains(self) -> list[Any]:
        api = self._api_client()
        try:
            raw = api.list_domains()
            if hasattr(raw, "ok"):
                if raw.ok:
                    data = raw.data if raw.data is not None else []
                    if isinstance(data, list) and data:
                        return _normalize_domain_items(data)
                    parsed = _parse_domains_file()
                    return parsed if parsed else (data if isinstance(data, list) else [])
                return _parse_domains_file()
            data = _result_or_raise(raw, default=[])
            return _normalize_domain_items(data) if isinstance(data, list) else []
        except HTTPException:
            return _parse_domains_file()

    def get_domain_lists_status(self) -> dict[str, bool]:
        return get_domain_lists_status()

    def add_domain(self, domain: str) -> dict[str, Any]:
        _ensure_no_conflict()
        normalized = _normalize_domain(domain)
        api = self._api_client()
        return _result_or_raise(api.add_domain(normalized), default={"message": "OK"})

    def remove_domain(self, domain: str) -> dict[str, Any]:
        _ensure_no_conflict()
        normalized = _normalize_domain(domain)
        api = self._api_client()
        return _result_or_raise(api.remove_domain(normalized), default={"message": "OK"})

    def sync_domains(self) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        return _result_or_raise(api.sync_domains(), default={"message": "OK"})

    def add_domains_bulk(self, domains: list[str]) -> dict[str, Any]:
        _ensure_no_conflict()
        added: list[str] = []
        errors: list[dict[str, str]] = []
        for raw in domains:
            value = (raw or "").strip()
            if not value or value.startswith("#"):
                continue
            try:
                normalized = _normalize_domain(value)
                self.add_domain(normalized)
                added.append(normalized)
            except HTTPException as exc:
                errors.append({"domain": value, "error": str(exc.detail)})
        return {"added": added, "added_count": len(added), "errors": errors}

    def set_domain_list(self, name: str, *, enable: bool) -> dict[str, Any]:
        _ensure_no_conflict()
        list_name = name.strip().lower()
        if list_name not in {"gemini", "chatgpt"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Поддерживаются списки: gemini, chatgpt")
        api = self._api_client()
        action = api.enable_list if enable else api.disable_list
        return _result_or_raise(action(list_name), default={"message": "OK"})

    def get_user_domains_text(self) -> str:
        api = self._api_client()
        getter = getattr(api, "get_user_domains_text", None)
        if callable(getter):
            try:
                return _text_from_api_result(getter(), fallback=_extract_user_domains_text())
            except HTTPException:
                return _extract_user_domains_text()
        return _extract_user_domains_text()

    def save_user_domains_text(self, text: str) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        saver = getattr(api, "save_user_domains_text", None)
        if not callable(saver):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="save_user_domains_text недоступен в warper_api",
            )
        return _result_or_raise(saver(text), default={"message": "OK"})

    def get_ip_ranges_text(self) -> str:
        api = self._api_client()
        getter = getattr(api, "get_ip_ranges_text", None)
        if callable(getter):
            try:
                return _text_from_api_result(getter(), fallback=_read_ip_ranges_file_text())
            except HTTPException:
                return _read_ip_ranges_file_text()
        return _read_ip_ranges_file_text()

    def save_ip_ranges_text(self, text: str) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        saver = getattr(api, "save_ip_ranges_text", None)
        if not callable(saver):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="save_ip_ranges_text недоступен в warper_api",
            )
        return _result_or_raise(saver(text), default={"message": "OK"})

    def list_ip_ranges(self) -> list[Any]:
        api = self._api_client()
        try:
            raw = api.list_ip_ranges()
            if hasattr(raw, "ok"):
                if raw.ok:
                    data = raw.data if raw.data is not None else []
                    return data if isinstance(data, list) else []
                return _read_ip_ranges_file()
            data = _result_or_raise(raw, default=[])
            return data if isinstance(data, list) else []
        except HTTPException:
            return _read_ip_ranges_file()

    def add_ip_range(self, cidr: str) -> dict[str, Any]:
        _ensure_no_conflict()
        normalized = _normalize_cidr(cidr)
        api = self._api_client()
        return _result_or_raise(api.add_ip_range(normalized), default={"message": "OK"})

    def remove_ip_range(self, cidr: str) -> dict[str, Any]:
        _ensure_no_conflict()
        normalized = _normalize_cidr(cidr)
        api = self._api_client()
        return _result_or_raise(api.remove_ip_range(normalized), default={"message": "OK"})

    def sync_ip_ranges(self) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        return _result_or_raise(api.sync_ip_ranges(), default={"message": "OK"})

    def set_ip_route_mode(self, mode: str) -> dict[str, Any]:
        _ensure_no_conflict()
        allowed = {"antizapret", "all_vpn", "all"}
        if mode not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Режим должен быть одним из: {', '.join(sorted(allowed))}")
        api = self._api_client()
        return _result_or_raise(api.set_ip_route_mode(mode), default={"message": "OK"})

    def set_ip_export(self, *, enable: bool) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        return _result_or_raise(api.set_ip_export(enable), default={"message": "OK"})

    def get_traffic(self, period: str = "today") -> dict[str, Any]:
        allowed = {"today", "week", "month", "all"}
        if period not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Период должен быть одним из: {', '.join(sorted(allowed))}")
        api = self._api_client()
        payload = _result_or_raise(api.get_traffic(period), default={})
        if not isinstance(payload, dict):
            payload = {}
        hourly_points = _filter_traffic_hourly(_read_traffic_hourly_map(), period)
        payload["hourly_points"] = hourly_points
        payload["chart"] = _chart_points_from_hourly(hourly_points, period)
        if not payload["chart"]:
            payload["chart"] = _synthetic_traffic_chart(payload, period)
        return payload

    def get_logs(self, lines: int = 200) -> list[str]:
        lines = max(1, min(int(lines), 2000))
        api = self._api_client()
        data = _result_or_raise(api.get_logs(lines), default=[])
        if isinstance(data, list):
            return [str(line) for line in data]
        return [str(data)] if data else []

    def get_mode(self) -> dict[str, Any]:
        api = self._api_client()
        mode = api.get_mode()
        if isinstance(mode, str):
            payload: dict[str, Any] = {"outbound_mode": mode, "mode": mode}
        else:
            unwrapped = _result_or_raise(mode, default={})
            payload = unwrapped if isinstance(unwrapped, dict) else {"mode": unwrapped}

        # Реальные параметры берём из полного status JSON (вложенные ключи).
        try:
            raw_status = _result_or_raise(api.get_status(), default={})
        except Exception:
            raw_status = {}
        if isinstance(raw_status, dict):
            singbox = raw_status.get("singbox") if isinstance(raw_status.get("singbox"), dict) else {}
            subnet_block = raw_status.get("subnet") if isinstance(raw_status.get("subnet"), dict) else {}
            outbound = raw_status.get("outbound_mode")
            if isinstance(outbound, str) and outbound:
                payload.setdefault("outbound_mode", outbound)
                payload.setdefault("mode", outbound)
            if isinstance(singbox.get("mtu"), int):
                payload["mtu"] = singbox["mtu"]
            if isinstance(singbox.get("log_level"), str):
                payload["log_level"] = singbox["log_level"]
            fake = subnet_block.get("fake")
            if isinstance(fake, str) and fake:
                payload["subnet"] = fake
            fullvpn_raw = raw_status.get("fullvpn_warp_resolve")
            if isinstance(fullvpn_raw, bool):
                payload["fullvpn"] = fullvpn_raw
            elif isinstance(fullvpn_raw, str):
                payload["fullvpn"] = fullvpn_raw.strip().lower() in {"y", "yes", "1", "true", "on"}
            if isinstance(raw_status.get("autopatch_enabled"), bool):
                payload["autopatch"] = raw_status["autopatch_enabled"]
            if isinstance(raw_status.get("warp_keys_source"), str):
                payload.setdefault("warp_keys_source", raw_status["warp_keys_source"])

        # Fallback на отдельные геттеры, если status не дал значений.
        if "mtu" not in payload:
            getter = getattr(api, "get_mtu", None)
            if callable(getter):
                try:
                    value = getter()
                    if isinstance(value, int):
                        payload["mtu"] = value
                except Exception:
                    pass
        if "log_level" not in payload:
            getter = getattr(api, "get_log_level", None)
            if callable(getter):
                try:
                    value = getter()
                    if isinstance(value, str):
                        payload["log_level"] = value
                except Exception:
                    pass
        return payload

    def list_warp_keys(self) -> list[str]:
        api = self._api_client()
        lister = getattr(api, "list_warp_keys", None)
        if not callable(lister):
            return []
        try:
            return _normalize_string_list(lister())
        except HTTPException:
            return []

    def list_wg_configs(self) -> list[str]:
        api = self._api_client()
        lister = getattr(api, "list_wg_configs", None)
        if not callable(lister):
            return []
        try:
            return _normalize_string_list(lister())
        except HTTPException:
            return []

    def set_mode_warp(self, key_source: str | None = None) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        setter = getattr(api, "set_mode_warp", None)
        if not callable(setter):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="set_mode_warp недоступен в warper_api")
        if key_source is None:
            return _result_or_raise(setter(), default={"message": "OK"})
        allowed = {"system", "generate"}
        source = key_source.strip().lower()
        if source not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="key_source должен быть system или generate",
            )
        return _result_or_raise(setter(source), default={"message": "OK"})

    def set_mode_slave(self, host: str, port: int, key: str) -> dict[str, Any]:
        _ensure_no_conflict()
        host_value = (host or "").strip()
        key_value = (key or "").strip()
        if not host_value or not key_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите host и key")
        if not 1 <= int(port) <= 65535:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Порт должен быть 1–65535")
        api = self._api_client()
        setter = getattr(api, "set_mode_slave", None)
        if not callable(setter):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="set_mode_slave недоступен в warper_api")
        return _result_or_raise(setter(host_value, int(port), key_value), default={"message": "OK"})

    def set_mode_wg(self, config_path: str) -> dict[str, Any]:
        _ensure_no_conflict()
        path_value = (config_path or "").strip()
        if not path_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите путь к .conf")
        api = self._api_client()
        setter = getattr(api, "set_mode_wg", None)
        if not callable(setter):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="set_mode_wg недоступен в warper_api")
        return _result_or_raise(setter(path_value), default={"message": "OK"})

    def set_fullvpn(self, *, enable: bool) -> dict[str, Any]:
        _ensure_no_conflict()
        api = self._api_client()
        setter = getattr(api, "set_fullvpn", None)
        if not callable(setter):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="set_fullvpn недоступен в warper_api")
        return _result_or_raise(setter(enable), default={"message": "OK"})

    def set_subnet(self, subnet: str) -> dict[str, Any]:
        _ensure_no_conflict()
        subnet_value = (subnet or "").strip()
        if not subnet_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите подсеть")
        try:
            ipaddress.ip_network(subnet_value, strict=False)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Некорректная подсеть: {subnet}") from exc
        api = self._api_client()
        setter = getattr(api, "set_subnet", None)
        if not callable(setter):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="set_subnet недоступен в warper_api")
        return _result_or_raise(setter(subnet_value), default={"message": "OK"})

    def set_mtu(self, mtu: int) -> dict[str, Any]:
        _ensure_no_conflict()
        if not 1280 <= int(mtu) <= 1500:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MTU должен быть в диапазоне 1280–1500")
        api = self._api_client()
        return _result_or_raise(api.set_mtu(int(mtu)), default={"message": "OK"})

    def set_log_level(self, level: str) -> dict[str, Any]:
        _ensure_no_conflict()
        allowed = {"debug", "info", "warn", "error"}
        level = level.strip().lower()
        if level not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Уровень логов: {', '.join(sorted(allowed))}")
        api = self._api_client()
        return _result_or_raise(api.set_log_level(level), default={"message": "OK"})

    def singbox_action(self, action: Literal["start", "stop", "restart"]) -> dict[str, Any]:
        _ensure_no_conflict()
        default = {"message": f"sing-box {action}: ok", "success": True}
        try:
            api = self._api_client()
            method = getattr(api, f"singbox_{action}", None)
            if callable(method):
                return _result_or_raise(method(), default=default)
        except HTTPException:
            raise
        except Exception:
            pass
        return _singbox_systemctl(action)

    def _catalog_method(self, name: str):
        api = self._api_client()
        method = getattr(api, name, None)
        if not callable(method):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{name} недоступен в warper_api. Обновите AZ-WARP на узле (нужна версия ≥ 1.3.8).",
            )
        return method

    def catalog_search(self, query: str = "") -> list[dict[str, Any]]:
        method = self._catalog_method("catalog_search")
        data = _result_or_raise(method((query or "").strip()), default=[])
        return data if isinstance(data, list) else []

    def catalog_show(self, name: str) -> dict[str, Any]:
        list_name = (name or "").strip().lower()
        if not list_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите имя категории")
        method = self._catalog_method("catalog_show")
        data = _result_or_raise(method(list_name), default={})
        return data if isinstance(data, dict) else {}

    def catalog_add(self, name: str) -> dict[str, Any]:
        _ensure_no_conflict()
        list_name = (name or "").strip().lower()
        if not list_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите имя категории")
        method = self._catalog_method("catalog_add")
        return _result_or_raise(method(list_name), default={"message": "OK"})

    def catalog_remove(self, name: str) -> dict[str, Any]:
        _ensure_no_conflict()
        list_name = (name or "").strip().lower()
        if not list_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите имя категории")
        method = self._catalog_method("catalog_remove")
        return _result_or_raise(method(list_name), default={"message": "OK"})

    def catalog_update(self, name: str = "") -> dict[str, Any]:
        _ensure_no_conflict()
        list_name = (name or "").strip().lower()
        method = self._catalog_method("catalog_update")
        return _result_or_raise(method(list_name), default={"message": "OK"})

    def catalog_list_installed(self) -> list[dict[str, Any]]:
        method = self._catalog_method("catalog_list_installed")
        data = _result_or_raise(method(), default=[])
        return data if isinstance(data, list) else []

    def catalog_refresh_cache(self) -> dict[str, Any]:
        method = self._catalog_method("catalog_refresh_cache")
        return _result_or_raise(method(), default={"message": "OK"})

    def _updates_method(self, name: str):
        api = self._api_client()
        method = getattr(api, name, None)
        if not callable(method):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{name} недоступен в warper_api. Обновите AZ-WARP на узле (нужна версия ≥ 1.4.0).",
            )
        return method

    def check_for_updates(self, *, force: bool = False) -> dict[str, Any]:
        result = self._updates_method("check_for_updates")(force=force)
        if hasattr(result, "data") and isinstance(result.data, dict):
            payload = dict(result.data)
            message = getattr(result, "message", None)
            if message:
                payload["message"] = message
            return payload
        unwrapped = _result_or_raise(result, default={})
        return unwrapped if isinstance(unwrapped, dict) else {"raw": unwrapped}

    def apply_update(self, timeout: int = 600) -> dict[str, Any]:
        timeout = max(60, min(int(timeout), 900))
        return _result_or_raise(self._updates_method("update")(timeout=timeout), default={"message": "OK"})

    def iter_update_stream_events(self) -> Iterator[dict[str, Any]]:
        stream_fn = self._updates_method("update_stream")
        proc, err = stream_fn()
        if err:
            yield {"event": "error", "detail": err}
            return
        if proc is None:
            yield {"event": "error", "detail": "Не удалось запустить обновление"}
            return
        try:
            stdout = proc.stdout
            if stdout is None:
                yield {"event": "error", "detail": "stdout обновления недоступен"}
                return
            for line in iter(stdout.readline, ""):
                if line:
                    yield {"event": "log", "line": line.rstrip("\n")}
            rc = proc.wait(timeout=600)
            yield {"event": "done", "return_code": rc, "success": rc == 0}
        except Exception as exc:
            yield {"event": "error", "detail": str(exc)}
        finally:
            if proc.poll() is None:
                proc.kill()


def _singbox_systemctl(action: Literal["start", "stop", "restart"]) -> dict[str, Any]:
    """Fallback when warper_api singbox_* methods are missing or fail."""
    try:
        proc = subprocess.run(
            ["systemctl", action, "sing-box"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Таймаут: sing-box {action}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось выполнить systemctl {action} sing-box: {exc}",
        ) from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        detail = f"sing-box {action}: ошибка"
        if stderr:
            detail = f"{detail} ({stderr[:300]})"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    return {"message": f"sing-box {action}: ok", "success": True}


_DOCTOR_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _normalize_doctor_checks(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"status": "info", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("check") or item.get("name") or item.get("message") or ""
        raw_status = str(item.get("status") or item.get("result") or "info").lower()
        if raw_status in {"ok", "pass", "1", "true", "success"}:
            check_status = "ok"
        elif raw_status in {"error", "fail", "failed", "0", "false"}:
            check_status = "error"
        elif raw_status in {"warn", "warning"}:
            check_status = "warn"
        else:
            check_status = "info"
        normalized.append({"status": check_status, "text": str(text)})
    return normalized


def _parse_doctor_stdout(stdout: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        line = _DOCTOR_ANSI_RE.sub("", raw_line).strip()
        if not line:
            continue
        if line.startswith("==") or line.startswith("--") or "WARPER DOCTOR" in line:
            continue
        if "Диагностика завершена" in line:
            continue
        check_status = "info"
        if line.startswith("✔"):
            check_status = "ok"
        elif line.startswith("✘"):
            check_status = "error"
        elif line.startswith("!"):
            check_status = "warn"
        text = re.sub(r"^[✔✘!]\s*", "", line)
        checks.append({"status": check_status, "text": text})
    return checks


def _normalize_domain_items(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"name": item, "domain": item, "type": "user", "enabled": True})
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("domain") or ""
        normalized.append(
            {
                **item,
                "name": name,
                "domain": item.get("domain") or name,
                "type": item.get("type") or "user",
                "enabled": item.get("enabled", item.get("status") == "1"),
            }
        )
    return normalized


def _safe_version(api: Any) -> str | None:
    try:
        result = api.get_version()
        if result and getattr(result, "ok", False):
            data = result.data
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                return data.get("version")
    except Exception:
        return None
    return None


def run_warper_action(operation: str, **kwargs: Any) -> Any:
    """Dispatch for node agent; converts service exceptions to HTTPException."""
    service = WarperService()
    actions = {
        "health": lambda: service.get_health(),
        "status": lambda: service.get_status(),
        "doctor": lambda: service.doctor(),
        "toggle": lambda: service.toggle(),
        "list_domains": lambda: service.list_domains(),
        "domain_lists_status": lambda: service.get_domain_lists_status(),
        "add_domain": lambda: service.add_domain(kwargs["domain"]),
        "remove_domain": lambda: service.remove_domain(kwargs["domain"]),
        "sync_domains": lambda: service.sync_domains(),
        "add_domains_bulk": lambda: service.add_domains_bulk(kwargs["domains"]),
        "set_domain_list": lambda: service.set_domain_list(kwargs["name"], enable=kwargs["enable"]),
        "get_user_domains_text": lambda: service.get_user_domains_text(),
        "save_user_domains_text": lambda: service.save_user_domains_text(kwargs["text"]),
        "get_ip_ranges_text": lambda: service.get_ip_ranges_text(),
        "save_ip_ranges_text": lambda: service.save_ip_ranges_text(kwargs["text"]),
        "list_warp_keys": lambda: service.list_warp_keys(),
        "list_wg_configs": lambda: service.list_wg_configs(),
        "set_mode_warp": lambda: service.set_mode_warp(kwargs.get("key_source")),
        "set_mode_slave": lambda: service.set_mode_slave(kwargs["host"], kwargs["port"], kwargs["key"]),
        "set_mode_wg": lambda: service.set_mode_wg(kwargs["config_path"]),
        "set_fullvpn": lambda: service.set_fullvpn(enable=kwargs["enable"]),
        "set_subnet": lambda: service.set_subnet(kwargs["subnet"]),
        "list_ip_ranges": lambda: service.list_ip_ranges(),
        "add_ip_range": lambda: service.add_ip_range(kwargs["cidr"]),
        "remove_ip_range": lambda: service.remove_ip_range(kwargs["cidr"]),
        "sync_ip_ranges": lambda: service.sync_ip_ranges(),
        "set_ip_route_mode": lambda: service.set_ip_route_mode(kwargs["mode"]),
        "set_ip_export": lambda: service.set_ip_export(enable=kwargs["enable"]),
        "get_traffic": lambda: service.get_traffic(kwargs.get("period", "today")),
        "get_logs": lambda: service.get_logs(kwargs.get("lines", 200)),
        "get_mode": lambda: service.get_mode(),
        "set_mtu": lambda: service.set_mtu(kwargs["mtu"]),
        "set_log_level": lambda: service.set_log_level(kwargs["level"]),
        "singbox_action": lambda: service.singbox_action(kwargs["action"]),
        "catalog_search": lambda: service.catalog_search(kwargs.get("query", "")),
        "catalog_show": lambda: service.catalog_show(kwargs["name"]),
        "catalog_add": lambda: service.catalog_add(kwargs["name"]),
        "catalog_remove": lambda: service.catalog_remove(kwargs["name"]),
        "catalog_update": lambda: service.catalog_update(kwargs.get("name", "")),
        "catalog_list_installed": lambda: service.catalog_list_installed(),
        "catalog_refresh_cache": lambda: service.catalog_refresh_cache(),
        "check_for_updates": lambda: service.check_for_updates(force=kwargs.get("force", False)),
        "apply_update": lambda: service.apply_update(kwargs.get("timeout", 600)),
    }
    if operation not in actions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown action")
    try:
        return actions[operation]()
    except (WarperNotInstalledError, WarperConflictError, HTTPException) as exc:
        raise _http_exception_from_service(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Ошибка WARPER",
        ) from exc
