import io
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import awg2


def _seed_awg2_tree(tmp_path: Path) -> None:
    amnezia = tmp_path / "amnezia"
    clients = tmp_path / "overlay" / "clients" / "antizapret"
    amnezia.mkdir(parents=True)
    clients.mkdir(parents=True)
    (amnezia / "antizapret-awg.conf").write_text("[Interface]\nPrivateKey = aaa=\n")
    (amnezia / "services.env").write_text("AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\n")
    (amnezia / "obfuscation.env").write_text("AWG_Jc=4\n")
    (clients / "antizapret-ivan-am.conf").write_text("[Interface]\n")
    # noise that must be excluded if under overlay
    stats = tmp_path / "overlay" / "stats.db"
    stats.write_bytes(b"sqlite")


def test_export_archive_contains_amnezia_and_clients_excludes_stats(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
    ):
        data = awg2.Awg2Service().export_state_archive()
    names = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz").getnames()
    assert any(n.startswith("amneziawg/") for n in names)
    assert any("clients/antizapret/antizapret-ivan-am.conf" in n for n in names)
    assert not any(n.endswith("stats.db") for n in names)


def test_import_archive_replaces_trees(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
    ):
        svc = awg2.Awg2Service()
        data = svc.export_state_archive()
        (tmp_path / "amnezia" / "antizapret-awg.conf").write_text("STALE\n")
        svc.import_state_archive(data)
    assert "PrivateKey" in (tmp_path / "amnezia" / "antizapret-awg.conf").read_text()


def test_import_archive_rejects_partial_archive_before_mutation(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"[Interface]\nPrivateKey = bbb=\n"
        info = tarfile.TarInfo(name="amneziawg/antizapret-awg.conf")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
    ):
        svc = awg2.Awg2Service()
        with pytest.raises(ValueError, match="must contain both amneziawg/ and clients/ files"):
            svc.import_state_archive(buffer.getvalue())
    assert (tmp_path / "amnezia" / "antizapret-awg.conf").read_text() == "[Interface]\nPrivateKey = aaa=\n"
    assert (tmp_path / "overlay" / "clients" / "antizapret" / "antizapret-ivan-am.conf").read_text() == "[Interface]\n"


def test_apply_runtime_prefers_syncconf_then_restart(tmp_path: Path, monkeypatch):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_SERVICES_ENV", tmp_path / "amnezia" / "services.env"),
        patch("app.services.awg2.subprocess.run", side_effect=fake_run),
        patch("app.services.awg2.shutil.which", return_value="/usr/bin/awg"),
    ):
        result = awg2.Awg2Service().apply_runtime()
    assert result["success"] is True
    assert any("syncconf" in c for c in calls) or any("systemctl" in c for c in calls)


def test_apply_runtime_fails_when_services_env_has_no_ifaces(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    (tmp_path / "amnezia" / "services.env").write_text("AZ_PORT=51820\n")
    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_SERVICES_ENV", tmp_path / "amnezia" / "services.env"),
    ):
        result = awg2.Awg2Service().apply_runtime()
    assert result["success"] is False
    assert result["errors"] == [
        {
            "interface": None,
            "stderr": "services.env does not define AZ_IFACE or VPN_IFACE",
        }
    ]
