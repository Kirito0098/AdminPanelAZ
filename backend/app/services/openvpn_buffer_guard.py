from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings as get_app_settings
from app.models import (
    Node,
    OpenVpnBufferGuardEvent,
    OpenVpnBufferGuardMode,
    OpenVpnBufferGuardSettings,
)
from app.services.admin_notify import admin_notify_service
from app.services.openvpn_buffer_guard_parse import summarize_enobufs
from app.services.openvpn_management import openvpn_management_service

ALLOWED_UNITS = frozenset({"antizapret-udp", "antizapret-tcp", "vpn-udp", "vpn-tcp"})


def normalize_watch_unit(unit: str) -> str | None:
    """Normalize a requested OpenVPN server unit name to a short watch key.

    Accepts raw variants like:
    - "antizapret-udp"
    - "openvpn-server@vpn-udp"
    - "openvpn-server@vpn-udp.service"
    - "vpn-tcp.service"
    Returns the short name ("antizapret-udp", "vpn-udp", "vpn-tcp") if it is in
    the allowlist, otherwise ``None``.
    """
    u = (unit or "").strip()
    if not u:
        return None
    if u.startswith("openvpn-server@"):
        u = u.split("@", 1)[1]
    if u.endswith(".service"):
        u = u[: -len(".service")]
    return u if u in ALLOWED_UNITS else None


def journal_unit_name(unit: str) -> str | None:
    """Return full systemd unit name for an allowed watch unit."""
    name = normalize_watch_unit(unit)
    if not name:
        return None
    return f"openvpn-server@{name}.service"


def fetch_unit_journal(unit: str, window_seconds: int) -> dict:
    """Fetch recent journal entries for an OpenVPN server unit.

    Returns a dict:
    { "ok": bool, "unit": str, "text": str, "error": str | None }
    """
    name = normalize_watch_unit(unit)
    if not name:
        return {"ok": False, "unit": unit, "text": "", "error": "Недопустимый unit"}

    svc = journal_unit_name(name)
    if svc is None:
        return {"ok": False, "unit": unit, "text": "", "error": "Недопустимый unit"}

    window_seconds = max(5, min(int(window_seconds), 600))
    try:
        result = subprocess.run(
            ["journalctl", "-u", svc, f"--since=-{window_seconds} seconds", "--no-pager", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "unit": name, "text": "", "error": str(exc)}

    # 1 is "no entries"; treat as success with empty text.
    if result.returncode not in (0, 1):
        err = (result.stderr or result.stdout or "journalctl failed").strip()
        return {"ok": False, "unit": name, "text": "", "error": err}

    return {"ok": True, "unit": name, "text": result.stdout or "", "error": None}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_watch_units(raw_json: str | None) -> list[str]:
    try:
        data = json.loads(raw_json or "[]")
    except Exception:
        data = []
    units: list[str] = []
    for item in data if isinstance(data, list) else []:
        name = normalize_watch_unit(str(item))
        if name and name not in units:
            units.append(name)
    if not units:
        units = ["antizapret-udp", "vpn-udp"]
    # Enforce allowlist defensively.
    return [u for u in units if normalize_watch_unit(u)]


MODE_RECOMMENDED_THRESHOLD: dict[str, int] = {
    OpenVpnBufferGuardMode.notify.value: 40,
    OpenVpnBufferGuardMode.kill.value: 80,
    OpenVpnBufferGuardMode.kill_restart.value: 120,
    OpenVpnBufferGuardMode.kill_restart_temp_ban.value: 150,
}


def recommended_threshold(mode: str) -> int:
    return int(MODE_RECOMMENDED_THRESHOLD.get(str(mode or "").strip(), 40))


def recommended_by_mode() -> dict[str, int]:
    return dict(MODE_RECOMMENDED_THRESHOLD)


DEFAULT_SETTINGS: dict = {
    "enabled": False,
    "mode": OpenVpnBufferGuardMode.notify.value,
    "threshold_count": 40,
    "window_seconds": 60,
    "escalate_after_seconds": 30,
    "cooldown_minutes": 15,
    "temp_ban_minutes": 60,
    "watch_units": ["antizapret-udp", "vpn-udp"],
}


def get_settings(db: Session, node_id: int) -> OpenVpnBufferGuardSettings:
    row = db.query(OpenVpnBufferGuardSettings).filter_by(node_id=node_id).first()
    if row is None:
        row = OpenVpnBufferGuardSettings(
            node_id=node_id,
            enabled=bool(DEFAULT_SETTINGS["enabled"]),
            mode=str(DEFAULT_SETTINGS["mode"]),
            threshold_count=int(DEFAULT_SETTINGS["threshold_count"]),
            window_seconds=int(DEFAULT_SETTINGS["window_seconds"]),
            escalate_after_seconds=int(DEFAULT_SETTINGS["escalate_after_seconds"]),
            cooldown_minutes=int(DEFAULT_SETTINGS["cooldown_minutes"]),
            temp_ban_minutes=int(DEFAULT_SETTINGS["temp_ban_minutes"]),
            watch_units_json=json.dumps(DEFAULT_SETTINGS["watch_units"], ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def upsert_settings(db: Session, node_id: int, payload: dict) -> OpenVpnBufferGuardSettings:
    row = get_settings(db, node_id)
    if "enabled" in payload:
        row.enabled = bool(payload["enabled"])
    if "mode" in payload and payload["mode"]:
        mode_value = str(payload["mode"])
        try:
            mode_enum = OpenVpnBufferGuardMode(mode_value)
            row.mode = mode_enum.value
        except ValueError:
            # Keep previous mode on invalid value.
            pass
    if "threshold_count" in payload and payload["threshold_count"] is not None:
        row.threshold_count = max(1, int(payload["threshold_count"]))
    if "window_seconds" in payload and payload["window_seconds"] is not None:
        row.window_seconds = max(5, int(payload["window_seconds"]))
    if "escalate_after_seconds" in payload and payload["escalate_after_seconds"] is not None:
        row.escalate_after_seconds = max(0, int(payload["escalate_after_seconds"]))
    if "cooldown_minutes" in payload and payload["cooldown_minutes"] is not None:
        row.cooldown_minutes = max(0, int(payload["cooldown_minutes"]))
    if "temp_ban_minutes" in payload and payload["temp_ban_minutes"] is not None:
        row.temp_ban_minutes = max(1, int(payload["temp_ban_minutes"]))
    if "watch_units" in payload and payload["watch_units"] is not None:
        units = [normalize_watch_unit(str(u)) for u in payload["watch_units"]]
        units = [u for u in units if u]
        if units:
            row.watch_units_json = json.dumps(units, ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_events(db: Session, node_id: int, limit: int = 20) -> list[OpenVpnBufferGuardEvent]:
    return (
        db.query(OpenVpnBufferGuardEvent)
        .filter(OpenVpnBufferGuardEvent.node_id == node_id)
        .order_by(OpenVpnBufferGuardEvent.created_at.desc())
        .limit(int(limit))
        .all()
    )


def _node_for_id(db: Session, node_id: int) -> Node | None:
    return db.query(Node).filter(Node.id == node_id).first()


def _node_antizapret_path(node: Node) -> Path:
    settings = get_app_settings()
    try:
        meta = json.loads(node.node_metadata or "{}")
    except Exception:
        meta = {}
    raw_path = meta.get("antizapret_path")
    return Path(str(raw_path)) if raw_path else settings.antizapret_path


def _kill_client(node: Node | None, adapter, unit: str, common_name: str) -> dict:
    """Kill client session, preferring adapter for remote nodes."""
    # Prefer explicit kill-by-unit on the adapter so that remote nodes
    # can target the specific OpenVPN profile that produced ENOBUFS.
    kill_by_unit = getattr(adapter, "kill_openvpn_client", None)
    if callable(kill_by_unit):
        return kill_by_unit(unit, common_name)

    if node is not None and node.is_local:
        # Local panel host: kill via management socket for the specific profile.
        return openvpn_management_service.kill_client(unit, common_name)

    # Remote nodes (or unknown) — fall back to disconnect-by-name if available.
    disconnect = getattr(adapter, "disconnect_openvpn_client", None)
    if callable(disconnect):
        return disconnect(common_name)

    # Fallback to management socket best-effort.
    return openvpn_management_service.kill_client(unit, common_name)


def _error_text(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        detail = detail.get("message") or detail
    return str(detail or exc)


def _action_outcome(action: dict) -> str:
    kind = action.get("type")
    ok = bool(action.get("success", True))
    result = action.get("result")
    message = str(result.get("message") or "") if isinstance(result, dict) else str(result or "")
    if kind == "kill":
        return "клиент отключён" if ok else f"отключить клиента не удалось: {message}"
    if kind == "escalation_check":
        return f"журнал после отключения не прочитан, перезапуск не проверялся: {message}"
    if kind == "restart":
        return "сервер перезапущен" if ok else f"перезапуск не удался: {message}"
    if kind == "temp_ban":
        return f"бан до {action.get('ban_expires_at')}"
    return str(kind)


def _apply_temp_ban(
    db: Session,
    node: Node | None,
    adapter,
    client_name: str,
    minutes: int,
) -> datetime | None:
    """Add client to banned_clients via AccessPolicyService and return ban_expires_at."""
    if node is None or not client_name or adapter is None:
        return None
    try:
        from app.services.access_policy import AccessPolicyService  # local import to avoid import cycles
    except Exception:
        return None

    antizapret_path = _node_antizapret_path(node)
    try:
        svc = AccessPolicyService(
            db,
            antizapret_path=antizapret_path,
            node_id=node.id,
            node_name=node.name,
            adapter=adapter,
        )
        banned = svc.read_banned_clients()
        if client_name not in banned:
            banned.add(client_name)
            svc.write_banned_clients(banned)
    except Exception:
        return None

    return _now_utc() + timedelta(minutes=max(1, int(minutes)))


def _recent_auto_event(db: Session, node_id: int, since: datetime, *criteria) -> bool:
    last_event = (
        db.query(OpenVpnBufferGuardEvent)
        .filter(
            OpenVpnBufferGuardEvent.node_id == node_id,
            OpenVpnBufferGuardEvent.manual.is_(False),
            *criteria,
        )
        .order_by(OpenVpnBufferGuardEvent.created_at.desc())
        .first()
    )
    if last_event is None or last_event.created_at is None:
        return False
    last_ts = last_event.created_at
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    return last_ts > since


def run_guard_pass(
    db: Session,
    adapter,
    node_id: int,
    *,
    manual: bool = False,
) -> list[dict]:
    """Run one buffer-guard pass for a node.

    Returns one dict per watched unit with summary and actions.
    """
    settings_row = get_settings(db, node_id)
    now = _now_utc()
    cooldown = timedelta(minutes=max(0, int(settings_row.cooldown_minutes)))

    # Cooldown: skip automatic runs after a recent automatic threshold event.
    # Manual scans and journal sample failures (error_count == 0) do not pause the guard.
    if not manual and _recent_auto_event(db, node_id, now - cooldown, OpenVpnBufferGuardEvent.error_count > 0):
        return []

    node = _node_for_id(db, node_id)
    try:
        mode_enum = OpenVpnBufferGuardMode(settings_row.mode)
    except ValueError:
        mode_enum = OpenVpnBufferGuardMode.kill_restart

    watch_units = _parse_watch_units(settings_row.watch_units_json)
    apply_actions = bool(settings_row.enabled) and not manual
    threshold = max(1, int(settings_row.threshold_count))

    results: list[dict] = []

    for unit in watch_units:
        sample = adapter.sample_openvpn_journal(unit, int(settings_row.window_seconds))

        # Journal sample failure must not be treated as "0 ENOBUFS".
        # Record a failed event, notify, and skip kill/restart for this unit.
        # A failure that keeps repeating is reported once per cooldown window.
        if not bool(sample.get("ok", True)):
            error_message = str(sample.get("error") or "journal sample failed")
            actions: list[dict] = []
            ban_expires_at: datetime | None = None
            event_result_label = "failed"
            already_reported = not manual and _recent_auto_event(
                db,
                node_id,
                now - cooldown,
                OpenVpnBufferGuardEvent.unit == unit,
                OpenVpnBufferGuardEvent.error_count == 0,
            )

            if not already_reported:
                try:
                    admin_notify_service.send(
                        db,
                        "openvpn_buffer_guard",
                        target_name="",
                        target_type="openvpn",
                        details=f"journal sample failed for {unit}: {error_message}",
                        node_id=node.id if node else None,
                        node_name=node.name if node else None,
                    )
                except Exception:
                    # Notifications are best-effort; failure must not break the guard.
                    pass

                event_detail = {
                    "sample_ok": False,
                    "error": error_message,
                }
                event = OpenVpnBufferGuardEvent(
                    node_id=node_id,
                    created_at=now,
                    unit=unit,
                    common_name=None,
                    real_address=None,
                    error_count=0,
                    window_seconds=int(settings_row.window_seconds),
                    mode=mode_enum.value,
                    actions_json=json.dumps(actions, ensure_ascii=False),
                    result=event_result_label,
                    detail=json.dumps(event_detail, ensure_ascii=False),
                    manual=manual,
                    ban_expires_at=ban_expires_at,
                )
                db.add(event)
                db.commit()

            results.append(
                {
                    "unit": unit,
                    "total": 0,
                    "threshold": threshold,
                    "threshold_exceeded": False,
                    "mode": mode_enum.value,
                    "top_cn": None,
                    "top_real_address": None,
                    "manual": manual,
                    "actions": actions,
                    "result": event_result_label,
                }
            )
            continue

        text = str(sample.get("text") or "")
        summary = summarize_enobufs(text)
        total = int(summary.get("total") or 0)
        top_cn = summary.get("top_cn")
        top_real = summary.get("top_real_address")
        exceeded = total >= threshold

        actions: list[dict] = []
        ban_expires_at: datetime | None = None
        event_result = "skipped"

        if exceeded:
            # Notify admins — label wiring will be finalized in a later task.
            # Mode-specific actions (manual runs are always findings-only).
            # Agent errors are recorded as failed actions: the event must be written
            # so that the cooldown starts and the admin sees what failed.
            if mode_enum != OpenVpnBufferGuardMode.notify and apply_actions and top_cn:
                try:
                    kill_result = _kill_client(node, adapter, unit, top_cn)
                    kill_ok = bool(kill_result.get("success"))
                except Exception as exc:
                    kill_result = {"success": False, "message": _error_text(exc)}
                    kill_ok = False
                actions.append(
                    {
                        "type": "kill",
                        "unit": unit,
                        "client_name": top_cn,
                        "success": kill_ok,
                        "result": kill_result,
                    }
                )

            if mode_enum in (OpenVpnBufferGuardMode.kill_restart, OpenVpnBufferGuardMode.kill_restart_temp_ban) and apply_actions:
                delay = max(0, int(settings_row.escalate_after_seconds))
                if delay:
                    time.sleep(float(delay))

                # Use a short post-kill window close to the escalation delay
                # so that pre-kill ENOBUFS do not force a restart.
                second_window = max(5, int(settings_row.escalate_after_seconds or settings_row.window_seconds))
                try:
                    second = adapter.sample_openvpn_journal(unit, int(second_window))
                except Exception as exc:
                    second = {"ok": False, "error": _error_text(exc)}
                if not bool(second.get("ok", True)):
                    actions.append(
                        {
                            "type": "escalation_check",
                            "unit": unit,
                            "success": False,
                            "result": str(second.get("error") or "journal sample failed"),
                        }
                    )
                second_summary = summarize_enobufs(str(second.get("text") or ""))
                second_total = int(second_summary.get("total") or 0)
                if second_total >= max(1, threshold // 2):
                    # Restart via adapter with allowlisted units only.
                    short_name = normalize_watch_unit(unit)
                    if short_name:
                        service_name = f"openvpn-server@{short_name}"
                        try:
                            restart_result = adapter.restart_service(service_name)
                            restart_ok = True
                        except Exception as exc:
                            restart_result = _error_text(exc)
                            restart_ok = False
                        actions.append(
                            {
                                "type": "restart",
                                "service": service_name,
                                "success": restart_ok,
                                "result": restart_result,
                            }
                        )

            if mode_enum == OpenVpnBufferGuardMode.kill_restart_temp_ban and top_cn:
                ban_expires_at = _apply_temp_ban(
                    db,
                    node,
                    adapter if apply_actions else None,
                    top_cn,
                    settings_row.temp_ban_minutes,
                )
                if ban_expires_at is not None:
                    actions.append(
                        {
                            "type": "temp_ban",
                            "client_name": top_cn,
                            "ban_expires_at": ban_expires_at.isoformat(),
                        }
                    )

            # Derive high-level result label from actions that succeeded.
            kinds = {str(a.get("type") or "") for a in actions if a.get("success", True)}
            if "temp_ban" in kinds:
                event_result_label = "banned"
            elif "restart" in kinds:
                event_result_label = "restarted"
            elif "kill" in kinds:
                event_result_label = "killed"
            elif actions:
                event_result_label = "failed"
            else:
                # Threshold exceeded but no actions (notify / manual-only).
                event_result_label = "notified"

            try:
                admin_notify_service.send(
                    db,
                    "openvpn_buffer_guard",
                    target_name=top_cn or "",
                    target_type="openvpn",
                    details="; ".join([f"{total} ENOBUFS in {unit}", *(_action_outcome(a) for a in actions)]),
                    node_id=node.id if node else None,
                    node_name=node.name if node else None,
                )
            except Exception:
                pass

            event = OpenVpnBufferGuardEvent(
                node_id=node_id,
                created_at=now,
                unit=unit,
                common_name=top_cn,
                real_address=top_real,
                error_count=total,
                window_seconds=int(settings_row.window_seconds),
                mode=mode_enum.value,
                actions_json=json.dumps(actions, ensure_ascii=False),
                result=event_result_label,
                detail=json.dumps(summary, ensure_ascii=False),
                manual=manual,
                ban_expires_at=ban_expires_at,
            )
            db.add(event)
            db.commit()
            event_result = event.result

        results.append(
            {
                "unit": unit,
                "total": total,
                "threshold": threshold,
                "threshold_exceeded": exceeded,
                "mode": mode_enum.value,
                "top_cn": top_cn,
                "top_real_address": top_real,
                "manual": manual,
                "actions": actions,
                "result": event_result,
            }
        )

    return results


def process_temp_ban_expiries(db: Session) -> list[dict]:
    """Lift temporary guard bans whose ban_expires_at has passed.

    The client leaves banned_clients only if its access policy (admin block, expiry,
    traffic limit) and newer guard bans do not keep it there.
    Returns a summary per processed client.
    """
    try:
        from app.services.access_policy import AccessPolicyService  # local import to avoid import cycles
        from app.services.node_manager import get_adapter_for_node  # local import to avoid cycles
    except Exception:
        return []

    now = _now_utc()
    expired_events = (
        db.query(OpenVpnBufferGuardEvent)
        .filter(
            OpenVpnBufferGuardEvent.ban_expires_at.isnot(None),
            OpenVpnBufferGuardEvent.ban_expires_at <= now,
        )
        .order_by(OpenVpnBufferGuardEvent.node_id.asc(), OpenVpnBufferGuardEvent.id.asc())
        .all()
    )
    if not expired_events:
        return []

    settings = get_app_settings()
    results: list[dict] = []

    # Group by (node, client) so we can resolve per-node adapters.
    grouped: dict[tuple[int, str], list[OpenVpnBufferGuardEvent]] = {}
    for ev in expired_events:
        if not ev.common_name:
            continue
        key = (ev.node_id, ev.common_name)
        grouped.setdefault(key, []).append(ev)

    adapter_cache: dict[int, object | None] = {}

    for (node_id, client_name), events in grouped.items():
        node = _node_for_id(db, node_id)
        if node is None:
            continue

        if node_id not in adapter_cache:
            try:
                adapter_cache[node_id] = get_adapter_for_node(node)
            except Exception:
                # If adapter resolution fails (e.g. node misconfigured or offline),
                # keep bans as-is and move on.
                adapter_cache[node_id] = None

        adapter_for_node = adapter_cache.get(node_id)
        if adapter_for_node is None:
            continue

        try:
            try:
                meta = json.loads(node.node_metadata or "{}")
            except Exception:
                meta = {}
            raw_path = meta.get("antizapret_path")
            antizapret_path = Path(str(raw_path)) if raw_path else settings.antizapret_path
            svc = AccessPolicyService(
                db,
                antizapret_path=antizapret_path,
                node_id=node.id,
                node_name=node.name,
                adapter=adapter_for_node,
            )
            svc.reconcile_openvpn(client_name)
            unbanned = client_name not in svc.read_banned_clients()
            for ev in events:
                ev.ban_expires_at = None
            db.commit()
            results.append(
                {
                    "node_id": node_id,
                    "client_name": client_name,
                    "unbanned": unbanned,
                }
            )
        except Exception:
            # If banned_clients write failed, we must not clear ban_expires_at.
            continue

    return results
