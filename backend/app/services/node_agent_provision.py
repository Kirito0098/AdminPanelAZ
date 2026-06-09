"""mTLS certificate provisioning on a node agent (write files, env, optional restart)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from app.services.node_update import resolve_repo_root, restart_node_agent

_DIR_MODE = 0o700
_KEY_MODE = 0o600
_CERT_MODE = 0o644

_MIN_PEM_LEN = 64
_CERT_MARKER_PAIRS = (("BEGIN CERTIFICATE", "END CERTIFICATE"),)
_KEY_MARKER_PAIRS = (
    ("BEGIN RSA PRIVATE KEY", "END RSA PRIVATE KEY"),
    ("BEGIN PRIVATE KEY", "END PRIVATE KEY"),
    ("BEGIN EC PRIVATE KEY", "END EC PRIVATE KEY"),
)


def _mtls_paths() -> dict[str, Path]:
    return {
        "ca_cert": Path(os.environ.get("NODE_AGENT_MTLS_CA_CERT", "/etc/adminpanelaz/mtls/ca.crt")),
        "server_cert": Path(
            os.environ.get("NODE_AGENT_MTLS_SERVER_CERT", "/etc/adminpanelaz/mtls/agent.crt")
        ),
        "server_key": Path(
            os.environ.get("NODE_AGENT_MTLS_SERVER_KEY", "/etc/adminpanelaz/mtls/agent.key")
        ),
    }


def _node_agent_env_file() -> Path:
    return Path(os.environ.get("NODE_AGENT_ENV_FILE", "/etc/adminpanelaz/node_agent.env"))


def _validate_pem(name: str, content: str, *, marker_pairs: tuple[tuple[str, str], ...]) -> None:
    text = (content or "").strip()
    if len(text) < _MIN_PEM_LEN:
        raise ValueError(f"{name}: PEM слишком короткий")
    if any(begin in text and end in text for begin, end in marker_pairs):
        return
    expected = " или ".join(f"{begin!r}" for begin, _ in marker_pairs)
    raise ValueError(f"{name}: ожидается PEM с маркером {expected}")


def validate_mtls_bundle(ca_pem: str, agent_cert_pem: str, agent_key_pem: str) -> None:
    _validate_pem("ca_pem", ca_pem, marker_pairs=_CERT_MARKER_PAIRS)
    _validate_pem("agent_cert_pem", agent_cert_pem, marker_pairs=_CERT_MARKER_PAIRS)
    _validate_pem("agent_key_pem", agent_key_pem, marker_pairs=_KEY_MARKER_PAIRS)


def _write_pem(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, _DIR_MODE)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    os.chmod(path, mode)


def persist_mtls_files(ca_pem: str, agent_cert_pem: str, agent_key_pem: str) -> dict[str, str]:
    """Write CA, server cert, and server key to NODE_AGENT_MTLS_* paths."""
    validate_mtls_bundle(ca_pem, agent_cert_pem, agent_key_pem)
    paths = _mtls_paths()
    _write_pem(paths["ca_cert"], ca_pem, mode=_CERT_MODE)
    _write_pem(paths["server_cert"], agent_cert_pem, mode=_CERT_MODE)
    _write_pem(paths["server_key"], agent_key_pem, mode=_KEY_MODE)
    return {key: str(path) for key, path in paths.items()}


def _env_set_line(key: str, value: str) -> str:
    return f"{key}={value}"


def persist_node_agent_env_mtls(paths: dict[str, str]) -> None:
    """Enable mTLS in node_agent.env and persist cert paths."""
    env_file = _node_agent_env_file()
    updates = {
        "NODE_AGENT_MTLS_ENABLED": "true",
        "NODE_AGENT_MTLS_CA_CERT": paths["ca_cert"],
        "NODE_AGENT_MTLS_SERVER_CERT": paths["server_cert"],
        "NODE_AGENT_MTLS_SERVER_KEY": paths["server_key"],
    }

    lines: list[str] = []
    if env_file.is_file():
        lines = env_file.read_text(encoding="utf-8").splitlines()

    result: list[str] = []
    seen: set[str] = set()
    key_pattern = re.compile(r"^([A-Z0-9_]+)=")

    for line in lines:
        match = key_pattern.match(line)
        if match and match.group(1) in updates:
            key = match.group(1)
            result.append(_env_set_line(key, updates[key]))
            seen.add(key)
        else:
            result.append(line)

    for key, value in updates.items():
        if key not in seen:
            result.append(_env_set_line(key, value))

    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(result) + "\n", encoding="utf-8")


def provision_mtls(
    *,
    ca_pem: str,
    agent_cert_pem: str,
    agent_key_pem: str,
    restart: bool = True,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Persist mTLS materials, update env, and optionally restart the node agent."""
    paths = persist_mtls_files(ca_pem, agent_cert_pem, agent_key_pem)
    persist_node_agent_env_mtls(paths)

    restart_result: dict[str, Any] | None = None
    if restart:
        root = repo_root or resolve_repo_root()
        if root is None:
            restart_result = {
                "method": "none",
                "success": False,
                "output": "",
                "error": "Репозиторий node agent не найден для перезапуска",
            }
        else:
            restart_result = restart_node_agent(root)

    success = restart_result is None or restart_result.get("success", False)
    message = "mTLS материалы записаны"
    if restart_result is not None:
        if restart_result.get("success"):
            message += f", перезапуск ({restart_result.get('method', 'unknown')})"
        else:
            message += f", перезапуск не выполнен: {restart_result.get('error', 'ошибка')}"

    return {
        "success": success,
        "message": message,
        "mtls_enabled": True,
        "paths": paths,
        "restart": restart_result,
    }
