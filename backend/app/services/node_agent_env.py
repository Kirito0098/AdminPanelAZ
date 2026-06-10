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
