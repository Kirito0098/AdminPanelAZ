# backend/tests/test_awg2_obfuscation.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import awg2


def test_get_obfuscation_reads_meta(tmp_path: Path):
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    (amnezia / "obfuscation.meta").write_text(
        "META_PRESET=medium\nMETA_TEMPLATE=web\nMETA_MTU=1280\nMETA_HOST=example.com\n"
    )
    (amnezia / "obfuscation.env").write_text("AWG_Jc=4\nAWG_S1=10\n")
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
    ):
        (tmp_path / "overlay").mkdir(exist_ok=True)
        data = awg2.Awg2Service().get_obfuscation()
    assert data["preset"] == "medium"
    assert data["template"] == "web"
    assert data["params"]["Jc"] == "4"


def test_apply_obfuscation_cli_args(tmp_path: Path):
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    obf_bin = tmp_path / "awg-obfuscation"
    obf_bin.write_text("#!/bin/sh\n")
    obf_bin.chmod(0o755)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stdout = "ok"
        r.stderr = ""
        return r

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OBFUSCATION_BIN", obf_bin),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_CLIENT_LOCK", tmp_path / "lock"),
        patch("app.services.awg2.subprocess.run", side_effect=fake_run),
    ):
        awg2.Awg2Service().apply_obfuscation(preset="high", template="web", mtu=1280)

    flat = [" ".join(c) for c in calls]
    assert any("awg-obfuscation" in s and "--preset" in s and "high" in s and "--apply" in s for s in flat)
    assert any("regen-all" in s for s in flat)


def test_apply_rejects_bad_preset(tmp_path: Path):
    with pytest.raises(ValueError):
        awg2.Awg2Service().apply_obfuscation(preset="nope", template="web")
