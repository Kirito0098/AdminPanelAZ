"""Resolve node agent env file paths (systemd, start script, provision)."""

from __future__ import annotations

import os
from pathlib import Path

from app.services.node_update import resolve_repo_root


def resolve_node_agent_env_file() -> Path:
    """Primary env file used by provision and API key persistence."""
    override = os.environ.get("NODE_AGENT_ENV_FILE")
    if override:
        return Path(override)
    root = resolve_repo_root()
    if root is not None:
        return root / "backend" / "node_agent.env"
    return Path("/etc/adminpanelaz/node_agent.env")


def node_agent_env_targets() -> list[Path]:
    """All env files that should receive mTLS settings (install + legacy paths)."""
    seen: set[Path] = set()
    targets: list[Path] = []

    def add(path: Path) -> None:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen:
            return
        seen.add(resolved)
        targets.append(path)

    add(resolve_node_agent_env_file())
    root = resolve_repo_root()
    if root is not None:
        add(root / "backend" / "node_agent.env")
    add(Path("/etc/adminpanelaz/node_agent.env"))
    return targets


_MTLS_FILES = (
    ("NODE_AGENT_MTLS_SERVER_CERT", "/etc/adminpanelaz/mtls/agent.crt"),
    ("NODE_AGENT_MTLS_SERVER_KEY", "/etc/adminpanelaz/mtls/agent.key"),
    ("NODE_AGENT_MTLS_CA_CERT", "/etc/adminpanelaz/mtls/ca.crt"),
)


def _read_env_values(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def missing_mtls_files(env_file: Path) -> list[str]:
    """Certificate files the agent needs on its next start (mTLS on in env_file) but cannot find."""
    values = _read_env_values(env_file)
    if values.get("NODE_AGENT_MTLS_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return []
    paths = [Path(values.get(key) or default) for key, default in _MTLS_FILES]
    return [str(path) for path in paths if not path.is_file()]
