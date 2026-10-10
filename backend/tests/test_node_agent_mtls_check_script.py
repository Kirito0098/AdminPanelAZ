"""install.sh helper: warn when node agent mTLS is on but certificate files are missing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "node-agent-mtls-check.sh"
ALL_CERTS = ("agent.crt", "agent.key", "ca.crt")


def _warning(env_file: Path) -> str:
    result = subprocess.run(
        ["bash", "-c", 'set -euo pipefail; source "$1"; node_agent_mtls_warning "$2"', "_", str(SCRIPT), str(env_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _env(tmp_path: Path, enabled: str, *present: str) -> Path:
    env_file = tmp_path / "node_agent.env"
    env_file.write_text(
        f"NODE_AGENT_MTLS_ENABLED={enabled}\n"
        f"NODE_AGENT_MTLS_SERVER_CERT={tmp_path / 'agent.crt'}\n"
        f"NODE_AGENT_MTLS_SERVER_KEY={tmp_path / 'agent.key'}\n"
        f"NODE_AGENT_MTLS_CA_CERT={tmp_path / 'ca.crt'}\n",
        encoding="utf-8",
    )
    for name in present:
        (tmp_path / name).write_text(name, encoding="utf-8")
    return env_file


def test_warns_about_each_missing_certificate(tmp_path):
    warning = _warning(_env(tmp_path, "true", "ca.crt"))

    assert warning.startswith("mTLS node agent включён")
    assert str(tmp_path / "agent.crt") in warning
    assert str(tmp_path / "agent.key") in warning
    assert str(tmp_path / "ca.crt") not in warning


@pytest.mark.parametrize("enabled", ["1", "YES", "True"])
def test_flag_spellings_match_the_agent(tmp_path, enabled):
    assert "сертификатов нет" in _warning(_env(tmp_path, enabled))


@pytest.mark.parametrize("enabled, present", [("false", ()), ("true", ALL_CERTS)])
def test_no_warning_when_agent_can_start(tmp_path, enabled, present):
    assert _warning(_env(tmp_path, enabled, *present)) == ""


def test_missing_env_file_is_silent(tmp_path):
    assert _warning(tmp_path / "absent.env") == ""
