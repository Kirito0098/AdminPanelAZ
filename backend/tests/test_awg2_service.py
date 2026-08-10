from pathlib import Path
from unittest.mock import patch

from app.services import awg2


def test_detect_not_installed(tmp_path: Path):
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", tmp_path / "missing-bin"),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
    ):
        data = awg2.detect_awg2_installation()
    assert data["installed"] is False
    assert "awg_client" in data["missing_components"]


def test_detect_installed_when_bin_and_dirs_exist(tmp_path: Path):
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
    ):
        data = awg2.detect_awg2_installation()
    assert data["installed"] is True
    assert data["missing_components"] == []


def test_get_health_includes_install_command(tmp_path: Path):
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", tmp_path / "x"),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "o"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "a"),
    ):
        health = awg2.Awg2Service().get_health()
    assert health["installed"] is False
    assert "blindtechnique/az-awg2" in health["install_command"]
    assert "--update" in awg2.AWG2_UPDATE_CMD
