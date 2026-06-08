"""Read/write AntiZapret setup file ({antizapret_path}/setup)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.antizapret_params import ANTIZAPRET_PARAMS, KNOWN_SETTING_KEYS


def normalize_flag(v: Any) -> str:
    if isinstance(v, (bool, int)):
        return "y" if v else "n"
    s = str(v).lower().strip()
    return "y" if s in ("y", "yes", "true", "1", "on") else "n"


def build_schema() -> list[dict[str, str]]:
    return [
        {
            "key": p["key"],
            "html_id": p["html_id"],
            "type": p["type"],
            "env": p.get("env", ""),
            "param_label": p.get("param_label", p.get("env", "")),
            "title": p.get("title", ""),
            "description": p.get("description", ""),
        }
        for p in ANTIZAPRET_PARAMS
    ]


def read_antizapret_settings(setup_path: Path) -> dict[str, str]:
    """Read setup file and return {key: value} for all ANTIZAPRET_PARAMS."""
    try:
        content = setup_path.read_text(encoding="utf-8")
    except OSError:
        content = ""

    settings: dict[str, str] = {}
    for p in ANTIZAPRET_PARAMS:
        key, env, typ, default = p["key"], p["env"], p["type"], p["default"]
        if typ == "string":
            m = re.search(rf"^{re.escape(env)}=(.+)$", content, re.M | re.I)
            settings[key] = m.group(1).strip() if m else default
        else:
            m = re.search(rf"^{re.escape(env)}=([yn])$", content, re.M | re.I)
            settings[key] = m.group(1).lower() if m else default
    return settings


def update_antizapret_settings(setup_path: Path, new_settings: dict[str, Any]) -> dict[str, Any]:
    """Apply partial updates to setup file. Unknown keys are ignored."""
    if not isinstance(new_settings, dict):
        raise ValueError("Ожидается JSON-объект")

    desired: dict[str, str] = {}
    for p in ANTIZAPRET_PARAMS:
        key = p["key"]
        if key not in new_settings:
            continue
        v = new_settings[key]
        env = p["env"]
        desired[env] = normalize_flag(v) if p["type"] == "flag" else str(v).strip()

    if not desired:
        return {
            "success": True,
            "message": "Нечего обновлять",
            "changes": 0,
            "needs_apply": False,
        }

    try:
        lines = setup_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        lines = []

    new_lines: list[str] = []
    found: set[str] = set()
    changes = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        key_part = stripped.split("=", 1)[0].strip()
        if key_part in desired:
            val = desired[key_part]
            comment = " " + stripped.split("#", 1)[1].strip() if "#" in stripped else ""
            new_lines.append(f"{key_part}={val}{comment}\n")
            found.add(key_part)
            changes += 1
        else:
            new_lines.append(line)

    for env, val in desired.items():
        if env not in found:
            new_lines.append(f"{env}={val}\n")
            changes += 1

    if changes > 0:
        setup_path.parent.mkdir(parents=True, exist_ok=True)
        setup_path.write_text("".join(new_lines), encoding="utf-8")

    return {
        "success": True,
        "message": "Настройки сохранены" if changes > 0 else "Нечего обновлять",
        "changes": changes,
        "needs_apply": changes > 0,
    }


def filter_known_keys(updates: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in updates.items() if k in KNOWN_SETTING_KEYS}
