from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import awg2


def test_add_client_runs_both_tunnels_and_rolls_back(tmp_path: Path):
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "clients").mkdir()
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ok"
        result.stderr = ""
        add_calls = [c for c in calls if "add" in c]
        if len(add_calls) == 2:
            result.returncode = 1
            result.stderr = "boom"
        return result

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_CLIENT_DIR", overlay / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_CLIENT_LOCK", tmp_path / "lock"),
        patch("app.services.awg2.subprocess.run", side_effect=fake_run),
    ):
        svc = awg2.Awg2Service()
        with pytest.raises(RuntimeError, match="boom"):
            svc.add_client("ivan")
    assert any(c[-3:] == ["add", "ivan", "antizapret"] or c[-3:] == ["add", "ivan", "vpn"] for c in calls)
    assert any(c[-3:] == ["del", "ivan", "antizapret"] for c in calls)


def test_add_client_rolls_back_orphan_conf_when_first_tunnel_fails(tmp_path: Path):
    """If awg-client writes conf then dies (e.g. QR overflow), still delete it."""
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    overlay = tmp_path / "overlay"
    clients = overlay / "clients"
    (clients / "antizapret").mkdir(parents=True)
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ok"
        result.stderr = ""
        if "add" in cmd and "antizapret" in cmd:
            (clients / "antizapret" / "antizapret-ivan-am.conf").write_text("[Interface]\n")
            result.returncode = 1
            result.stderr = "DataOverflowError"
        return result

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_CLIENT_DIR", clients),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_CLIENT_LOCK", tmp_path / "lock"),
        patch("app.services.awg2.subprocess.run", side_effect=fake_run),
    ):
        svc = awg2.Awg2Service()
        with pytest.raises(RuntimeError, match="DataOverflowError"):
            svc.add_client("ivan")

    assert any(c[-3:] == ["del", "ivan", "antizapret"] for c in calls)
    assert not any(c[-3:] == ["add", "ivan", "vpn"] for c in calls)


def test_read_profile_file_allows_awg2_root_and_blocks_outside(tmp_path: Path):
    clients = tmp_path / "clients"
    conf = clients / "antizapret" / "antizapret-ivan-am.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("[Interface]\n")
    outside = tmp_path / "elsewhere" / "ivan.conf"
    outside.parent.mkdir(parents=True)
    outside.write_text("blocked\n")
    with patch.object(awg2, "AWG2_CLIENT_DIR", clients):
        svc = awg2.Awg2Service()
        assert svc.read_profile_file(str(conf)) == "[Interface]\n"
        with pytest.raises(HTTPException) as exc:
            svc.read_profile_file(str(outside))
    assert exc.value.status_code == 403
