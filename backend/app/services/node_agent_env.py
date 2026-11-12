"""Resolve node agent env file paths (systemd, start script, provision)."""

from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings
from app.services.node_update import resolve_repo_root
from app.services.shared_helpers import read_kv_file


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


def _mtls_env_paths() -> tuple[tuple[str, Path], ...]:
    """Agent-side mTLS files, derived from the panel's configured mTLS directory."""
    settings = get_settings()
    return (
        ("NODE_AGENT_MTLS_SERVER_CERT", settings.node_agent_mtls_dir / "agent.crt"),
        ("NODE_AGENT_MTLS_SERVER_KEY", settings.node_agent_mtls_dir / "agent.key"),
        ("NODE_AGENT_MTLS_CA_CERT", Path(settings.node_agent_mtls_ca_cert)),
    )


def _read_env_values(env_file: Path) -> dict[str, str]:
    return read_kv_file(env_file, errors=None)


def missing_mtls_files(env_file: Path) -> list[str]:
    """Certificate files the agent needs on its next start (mTLS on in env_file) but cannot find."""
    values = _read_env_values(env_file)
    if values.get("NODE_AGENT_MTLS_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return []
    paths = [Path(values.get(key) or default) for key, default in _mtls_env_paths()]
    return [str(path) for path in paths if not path.is_file()]
