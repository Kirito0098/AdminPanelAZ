"""Tests for WG runtime block/unblock helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services import wg_runtime


def test_block_client_runtime_returns_structured_result(tmp_path: Path):
    config = tmp_path / "antizapret.conf"
    config.write_text(
        "# Client = alice\n"
        "[Peer]\n"
        "PublicKey = abc123key\n"
        "AllowedIPs = 10.0.0.2/32\n",
        encoding="utf-8",
    )
    files = {"antizapret": config}

    with patch.object(wg_runtime, "WG_CONFIG_FILES", files):
        with patch.object(wg_runtime, "_collect_client_peers", return_value=[("antizapret", "abc123key")]):
            with patch.object(wg_runtime, "_run") as run_mock:
                run_mock.return_value = MagicMock(returncode=0, stderr="")
                result = wg_runtime.block_client_runtime("alice")

    assert result["success"] is True
    assert result["removed_count"] == 1
    assert result["error_count"] == 0


def test_unblock_falls_back_to_syncconf_when_no_peer_specs(tmp_path: Path):
    files = {"antizapret": tmp_path / "missing.conf"}

    with patch.object(wg_runtime, "WG_CONFIG_FILES", files):
        with patch.object(wg_runtime, "_peer_specs_for_client", return_value=[]):
            with patch.object(wg_runtime, "_collect_client_peers", return_value=[]):
                with patch.object(wg_runtime, "_sync_interface_from_stripped_config", return_value=(True, "")) as sync_mock:
                    result = wg_runtime.unblock_client_runtime("alice")

    sync_mock.assert_called_once_with("antizapret")
    assert result["success"] is True
    assert result["synced_count"] == 1
