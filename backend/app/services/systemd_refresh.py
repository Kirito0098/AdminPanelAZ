"""Refresh installed systemd units from repo templates (update migration)."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REFRESH_TIMEOUT = 60.0
PANEL_UNIT_DST = Path("/etc/systemd/system/adminpanelaz.service")
NODE_UNIT_DST = Path("/etc/systemd/system/adminpanelaz-node.service")
_STALE_MARKERS = ("start.sh", "start_node_agent.sh")


def _unit_text_is_stale(text: str) -> bool:
    lower = text.lower()
    if "systemd-exec-panel.sh" in lower or "systemd-exec-node.sh" in lower:
        return False
    return any(marker in text for marker in _STALE_MARKERS)


def unit_file_needs_migration(unit_path: Path) -> bool:
    """True when installed unit still points at legacy start.sh / start_node_agent.sh."""
    if not unit_path.is_file():
        return False
    try:
        return _unit_text_is_stale(unit_path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def refresh_installed_systemd_units(
    repo_root: Path,
    *,
    panel: bool = True,
    node: bool = True,
) -> dict[str, Any]:
    """Rewrite /etc/systemd unit(s) from repo templates; daemon-reload via install scripts.

    Critical for 2.19+: old ExecStart=…/start.sh breaks after start.sh is removed/replaced.
    No service restart — caller schedules systemctl restart.
    """
    script = repo_root / "scripts" / "refresh-systemd-units.sh"
    if not script.is_file():
        return {
            "success": False,
            "skipped": False,
            "output": "",
            "error": f"Не найден {script}",
        }

    want_panel = panel and PANEL_UNIT_DST.is_file()
    want_node = node and NODE_UNIT_DST.is_file()
    if not want_panel and not want_node:
        return {
            "success": True,
            "skipped": True,
            "output": "Установленных systemd unit’ов нет — пропуск",
            "error": None,
        }

    env = {
        **os.environ,
        "REFRESH_PANEL": "1" if want_panel else "0",
        "REFRESH_NODE": "1" if want_node else "0",
    }
    try:
        result = subprocess.run(
            ["bash", str(script)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=REFRESH_TIMEOUT,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "skipped": False, "output": "", "error": "Таймаут refresh-systemd-units"}
    except OSError as exc:
        return {"success": False, "skipped": False, "output": "", "error": str(exc)}

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    success = result.returncode == 0
    return {
        "success": success,
        "skipped": False,
        "output": output,
        "error": None if success else output or f"refresh-systemd-units failed (exit {result.returncode})",
    }


def migrate_stale_systemd_units_on_startup(
    repo_root: Path | None,
    *,
    panel: bool = True,
    node: bool = False,
) -> dict[str, Any]:
    """If installed unit still references start.sh, rewrite from repo (no restart).

    Covers the chicken-egg of UI update: old in-memory code restarts via legacy ExecStart;
    compat start.sh shim boots new code; this migrates the unit for the next restart.
    """
    if not repo_root:
        return {"success": True, "skipped": True, "output": "no repo", "error": None}

    need_panel = panel and unit_file_needs_migration(PANEL_UNIT_DST)
    need_node = node and unit_file_needs_migration(NODE_UNIT_DST)
    if not need_panel and not need_node:
        return {"success": True, "skipped": True, "output": "units ok", "error": None}

    result = refresh_installed_systemd_units(repo_root, panel=need_panel, node=need_node)
    if result.get("success"):
        logger.info(
            "Migrated stale systemd unit(s) from start.sh → systemd-exec (panel=%s node=%s)",
            need_panel,
            need_node,
        )
    else:
        logger.warning("Failed to migrate stale systemd units: %s", result.get("error"))
    return result
