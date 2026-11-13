"""Single apply pipeline: sync providers → doall.sh → client profiles → multihome.

Routing apply, manual doall and the CIDR deploy used to run these steps with
their own order, progress texts and result keys. The order is fixed here:

    sync → doall → recreate profiles → openvpn multihome

Lock-free by design: the enqueue guards keep one running task per type
(``routing_apply``, ``run_doall``) and ``cidr_tasks`` serializes the CIDR
pipeline; there is no cross-type heavy lock, so this helper adds none.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.services.openvpn_multihome import maybe_ensure_openvpn_multihome
from app.services.openvpn_profile_repair import recreate_openvpn_profiles

ProgressCallback = Callable[[int, str, str | None], None]

# Per-step progress; the task runner owns 0 and 100.
_STEP_PROGRESS: dict[str, tuple[int, str]] = {
    "sync": (5, "Синхронизация провайдеров…"),
    "doall": (10, "AntiZapret: запуск doall.sh…"),
    "profiles": (65, "AntiZapret: пересоздание профилей клиентов…"),
    "multihome": (90, "AntiZapret: восстановление OpenVPN multihome…"),
}


def _step_text(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def apply_routing_changes(
    adapter: Any,
    *,
    sync: bool = True,
    doall: bool = True,
    ips_only: bool = True,
    recreate_profiles: bool = False,
    hosts: list[str] | None = None,
    ensure_multihome: bool = False,
    run_config_queue: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run the configured apply steps in a fixed order and report each step.

    Result keys, present only for the steps that ran: ``sync`` (adapter payload),
    ``doall_output`` (doall text), ``profiles`` (client.sh 7 text),
    ``openvpn_multihome`` (adapter payload), ``config_queue`` (flag echoed for the
    task report; the queue itself is owned by ``config_apply_queue``).

    Errors propagate as-is: a failed doall aborts before profiles, a failed
    profiles step keeps the already applied doall (no rollback), and multihome is
    skipped in both cases.
    """
    result: dict[str, Any] = {}

    if sync:
        if progress:
            progress(*_STEP_PROGRESS["sync"], None)
        result["sync"] = adapter.sync_cidr_providers()

    if doall:
        if progress:
            progress(*_STEP_PROGRESS["doall"], None)
        # ``ips_only`` skips the ~100 MB hosts download: CIDR routes never read those lists.
        result["doall_output"] = adapter.apply_config_changes(ips_only=ips_only)

    if recreate_profiles:
        if progress:
            progress(*_STEP_PROGRESS["profiles"], None)
        profiles = recreate_openvpn_profiles(adapter, hosts=hosts)
        if not profiles.success:
            raise RuntimeError(
                profiles.errors[0] if profiles.errors else "Ошибка пересоздания профилей"
            )
        result["profiles"] = profiles.output

    if ensure_multihome and doall:
        if progress:
            progress(*_STEP_PROGRESS["multihome"], None)
        multihome = maybe_ensure_openvpn_multihome(
            adapter, enabled=True, restart_if_unchanged=False
        )
        if multihome is not None:
            result["openvpn_multihome"] = multihome

    if run_config_queue:
        result["config_queue"] = True

    return result


def format_apply_output(result: dict[str, Any]) -> str:
    """Step outputs as one log text, in step order (task ``output`` field)."""
    parts = [
        _step_text(result.get("sync")),
        _step_text(result.get("doall_output")),
        _step_text(result.get("profiles")),
        _step_text(result.get("openvpn_multihome")),
    ]
    return "\n".join(part for part in parts if part).strip()
