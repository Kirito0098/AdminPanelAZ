"""Node agent must not serve or write files outside AntiZapret backup / profile locations."""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.antizapret import AntiZapretService
from app.services.antizapret_backup import resolve_backup_archive
from app.services.node_adapter import LocalNodeAdapter


@pytest.fixture()
def az_root(tmp_path):
    root = tmp_path / "antizapret"
    (root / "client" / "openvpn" / "antizapret").mkdir(parents=True)
    (root / "backup-1.2.3.4.tar.gz").write_bytes(b"archive")
    (root / "client.sh").write_text("#!/bin/sh\n")
    (tmp_path / "secret.txt").write_text("secret")
    return root


def test_resolve_backup_archive_finds_bare_backup_name(az_root):
    assert resolve_backup_archive("backup-1.2.3.4.tar.gz", [az_root]) == az_root / "backup-1.2.3.4.tar.gz"


@pytest.mark.parametrize(
    "name",
    [
        "client.sh",
        "../secret.txt",
        "backup-x.tar.gz/../../secret.txt",
        "missing-backup.tar.gz",
        "",
    ],
)
def test_resolve_backup_archive_rejects_non_backup_names(az_root, name):
    assert resolve_backup_archive(name, [az_root]) is None


def test_resolve_backup_archive_rejects_absolute_path(az_root):
    assert resolve_backup_archive(str(az_root / "backup-1.2.3.4.tar.gz"), [az_root]) is None
    assert resolve_backup_archive(str(az_root.parent / "secret.txt"), [az_root]) is None


def test_resolve_backup_archive_rejects_symlink_escape(az_root):
    os.symlink(az_root.parent / "secret.txt", az_root / "backup-link.tar.gz")
    assert resolve_backup_archive("backup-link.tar.gz", [az_root]) is None


def test_local_adapter_download_rejects_absolute_path(az_root):
    adapter = LocalNodeAdapter(service=AntiZapretService(base_path=az_root))
    with pytest.raises(HTTPException):
        adapter.download_antizapret_backup(str(az_root.parent / "secret.txt"))
    assert adapter.download_antizapret_backup("backup-1.2.3.4.tar.gz") == b"archive"


def test_agent_download_rejects_arbitrary_path(az_root, monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)

    from fastapi.testclient import TestClient

    import node_agent.main as agent_main

    headers = {"X-Node-Key": agent_main.NODE_AGENT_API_KEY}
    with patch.object(agent_main, "ANTIZAPRET_PATH", az_root):
        client = TestClient(agent_main.app)
        leaked = client.get(
            "/backups/antizapret/download",
            params={"name": str(az_root.parent / "secret.txt")},
            headers=headers,
        )
        ok = client.get(
            "/backups/antizapret/download",
            params={"name": "backup-1.2.3.4.tar.gz"},
            headers=headers,
        )

    assert leaked.status_code in (400, 404)
    assert b"secret" not in leaked.content
    assert ok.status_code == 200
    assert ok.content == b"archive"


def test_profile_path_rejects_sibling_with_client_dir_prefix(az_root):
    service = AntiZapretService(base_path=az_root)
    with pytest.raises(HTTPException) as exc:
        service.write_profile_file(str(az_root / "client.sh"), "pwned")
    assert exc.value.status_code == 403
    assert (az_root / "client.sh").read_text() == "#!/bin/sh\n"
    with pytest.raises(HTTPException):
        service.read_profile_file(str(az_root / "client.sh"))


def test_profile_write_rejects_non_profile_suffix(az_root):
    service = AntiZapretService(base_path=az_root)
    target = az_root / "client" / "openvpn" / "antizapret" / "hook.sh"
    with pytest.raises(HTTPException) as exc:
        service.write_profile_file(str(target), "pwned")
    assert exc.value.status_code == 403
    assert not target.exists()


def test_profile_write_allows_profile_files(az_root):
    service = AntiZapretService(base_path=az_root)
    ovpn = az_root / "client" / "openvpn" / "antizapret" / "ivan.ovpn"
    wg = az_root / "client" / "wireguard" / "vpn" / "ivan-wg.conf"
    service.write_profile_file(str(ovpn), "ovpn")
    service.write_profile_file(str(wg), "wg")
    assert ovpn.read_text() == "ovpn"
    assert service.read_profile_file(str(wg)) == "wg"
