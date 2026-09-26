"""PKI/profile imports and HA restore check the whole archive before touching live files."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import antizapret as az_mod
from app.services import antizapret_backup as backup_mod
from app.services.antizapret import AntiZapretService
from app.services.antizapret_backup import AntizapretBackupService


def _tar(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _big_tar(prefix: str) -> bytes:
    import os

    return _tar({f"{prefix}/f{i}.bin": os.urandom(4096) for i in range(40)})


def _truncated(data: bytes) -> bytes:
    return data[: len(data) // 2]


def _tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


# --- easyrsa3 import -------------------------------------------------------


@pytest.fixture
def easyrsa(tmp_path, monkeypatch):
    openvpn = tmp_path / "etc-openvpn"
    root = openvpn / "easyrsa3"
    (root / "pki" / "private").mkdir(parents=True)
    (root / "pki" / "ca.crt").write_text("old-ca")
    (root / "pki" / "private" / "ca.key").write_text("old-key")
    monkeypatch.setattr(az_mod, "EASYRSA3_ROOT", root)
    return root


def _service(tmp_path) -> AntiZapretService:
    base = tmp_path / "antizapret"
    base.mkdir(exist_ok=True)
    return AntiZapretService(base_path=base)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"not a gzip archive", id="garbage"),
        pytest.param(_truncated(_big_tar("easyrsa3/pki")), id="truncated"),
        pytest.param(_tar({"other/file.txt": b"x"}), id="no-easyrsa3"),
    ],
)
def test_bad_easyrsa3_archive_keeps_current_pki(tmp_path, easyrsa, data):
    before = _tree(easyrsa)
    with pytest.raises(HTTPException) as exc:
        _service(tmp_path).import_easyrsa3_archive(data)
    assert exc.value.status_code == 400
    assert _tree(easyrsa) == before
    assert _names(easyrsa.parent) == ["easyrsa3"]


def test_easyrsa3_import_replaces_pki(tmp_path, easyrsa):
    data = _tar({"easyrsa3/pki/ca.crt": b"new-ca", "easyrsa3/pki/index.txt": b"V", "etc/passwd": b"evil"})
    _service(tmp_path).import_easyrsa3_archive(data)
    assert _tree(easyrsa) == {"pki/ca.crt": "new-ca", "pki/index.txt": "V"}
    assert _names(easyrsa.parent) == ["easyrsa3"]


def test_easyrsa3_import_creates_missing_pki(tmp_path, easyrsa):
    import shutil

    shutil.rmtree(easyrsa)
    _service(tmp_path).import_easyrsa3_archive(_tar({"easyrsa3/pki/ca.crt": b"new-ca"}))
    assert _tree(easyrsa) == {"pki/ca.crt": "new-ca"}


def test_easyrsa3_install_failure_restores_pki(tmp_path, easyrsa, monkeypatch):
    before = _tree(easyrsa)

    def fail(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(az_mod, "_install_staged", fail)
    with pytest.raises(OSError):
        _service(tmp_path).import_easyrsa3_archive(_tar({"easyrsa3/pki/ca.crt": b"new-ca"}))
    assert _tree(easyrsa) == before
    assert _names(easyrsa.parent) == ["easyrsa3"]


def test_easyrsa3_import_ignores_unrelated_unsafe_members(tmp_path, easyrsa):
    data = _tar({"easyrsa3/pki/ca.crt": b"new-ca", "../outside.txt": b"x", "/abs.txt": b"x"})
    _service(tmp_path).import_easyrsa3_archive(data)
    assert _tree(easyrsa) == {"pki/ca.crt": "new-ca"}
    assert not (easyrsa.parent.parent / "outside.txt").exists()


# --- client profile imports ------------------------------------------------


def _profiles(tmp_path) -> AntiZapretService:
    service = _service(tmp_path)
    for sub, name in (("openvpn", "a.ovpn"), ("wireguard", "a.conf"), ("amneziawg", "a.conf")):
        path = service.client_dir / sub / "vpn" / name
        path.parent.mkdir(parents=True)
        path.write_text(f"old-{sub}")
    return service


PROFILE_IMPORTS = [
    pytest.param("import_openvpn_client_profiles_archive", ("openvpn",), id="openvpn"),
    pytest.param("import_wireguard_client_profiles_archive", ("wireguard", "amneziawg"), id="wireguard"),
]


@pytest.mark.parametrize(("method", "subdirs"), PROFILE_IMPORTS)
def test_truncated_profiles_archive_keeps_profiles(tmp_path, method, subdirs):
    service = _profiles(tmp_path)
    before = _tree(service.client_dir)
    with pytest.raises(HTTPException) as exc:
        getattr(service, method)(_truncated(_big_tar(f"client/{subdirs[0]}/vpn")))
    assert exc.value.status_code == 400
    assert _tree(service.client_dir) == before
    assert _names(service.base_path) == ["client"]


@pytest.mark.parametrize(("method", "subdirs"), PROFILE_IMPORTS)
def test_profiles_archive_without_its_files_keeps_profiles(tmp_path, method, subdirs):
    service = _profiles(tmp_path)
    before = _tree(service.client_dir)
    with pytest.raises(HTTPException) as exc:
        getattr(service, method)(_tar({"client/other/x": b"x"}))
    assert exc.value.status_code == 400
    assert _tree(service.client_dir) == before


@pytest.mark.parametrize(("method", "subdirs"), PROFILE_IMPORTS)
def test_profiles_import_replaces_only_its_dirs(tmp_path, method, subdirs):
    service = _profiles(tmp_path)
    getattr(service, method)(_tar({f"client/{subdirs[0]}/vpn/new.conf": b"new", "client/other/x": b"x"}))
    tree = _tree(service.client_dir)
    assert tree[f"{subdirs[0]}/vpn/new.conf"] == "new"
    for sub in subdirs:
        assert not any(k.startswith(f"{sub}/") and k.endswith(("a.ovpn", "a.conf")) for k in tree), tree
    for sub in {"openvpn", "wireguard", "amneziawg"} - set(subdirs):
        assert tree[f"{sub}/vpn/" + ("a.ovpn" if sub == "openvpn" else "a.conf")] == f"old-{sub}"
    assert "other/x" not in tree
    assert _names(service.base_path) == ["client"]


@pytest.mark.parametrize(("method", "subdirs"), PROFILE_IMPORTS)
def test_profiles_install_failure_restores_profiles(tmp_path, monkeypatch, method, subdirs):
    service = _profiles(tmp_path)
    before = _tree(service.client_dir)

    def fail(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(az_mod, "_install_staged", fail)
    with pytest.raises(OSError):
        getattr(service, method)(_tar({f"client/{subdirs[0]}/vpn/new.conf": b"new"}))
    assert _tree(service.client_dir) == before
    assert _names(service.base_path) == ["client"]
    assert _names(service.client_dir) == ["amneziawg", "openvpn", "wireguard"]


# --- HA replica restore ----------------------------------------------------


@pytest.fixture
def replica(tmp_path, monkeypatch):
    etc = tmp_path / "etc"
    easyrsa = etc / "openvpn" / "easyrsa3"
    (easyrsa / "pki").mkdir(parents=True)
    (easyrsa / "pki" / "ca.crt").write_text("replica-ca")
    wg = etc / "wireguard"
    wg.mkdir()
    (wg / "antizapret.conf").write_text("replica-wg")
    (wg / "extra.conf").write_text("replica-extra")
    (wg / "params").write_text("keep")
    knot = etc / "knot-resolver"
    install = tmp_path / "antizapret"
    for sub in ("openvpn", "wireguard", "amneziawg"):
        (install / "client" / sub).mkdir(parents=True)
        (install / "client" / sub / "p.txt").write_text(f"replica-{sub}")
    (install / "config").mkdir()
    monkeypatch.setattr(backup_mod, "_HA_EASYRSA3_ROOT", easyrsa)
    monkeypatch.setattr(backup_mod, "_HA_WIREGUARD_DIR", wg)
    monkeypatch.setattr(backup_mod, "_KNOT_RESOLVER_DIR", knot)
    service = AntizapretBackupService(install_dir=install, timeout_seconds=30)
    monkeypatch.setattr(service, "_run_doall_sh", lambda: "")
    return service, tmp_path


def _primary_archive(tmp_path, *, truncate=False) -> Path:
    data = _tar(
        {
            "easyrsa3/pki/ca.crt": b"primary-ca",
            "wireguard/antizapret.conf": b"primary-wg",
            "config/include-hosts.txt": b"example.com",
            "knot-resolver/kresd.conf": b"primary-knot",
            **({f"easyrsa3/pki/big{i}.bin": bytes(4096) + bytes([i]) * 4096 for i in range(40)} if truncate else {}),
        }
    )
    archive = tmp_path / "backup-primary.tar.gz"
    archive.write_bytes(_truncated(data) if truncate else data)
    return archive


def _state(tmp_path) -> dict[str, str]:
    return {**_tree(tmp_path / "etc"), **{f"az/{k}": v for k, v in _tree(tmp_path / "antizapret").items()}}


def test_truncated_ha_archive_leaves_replica_intact(replica):
    service, tmp_path = replica
    archive = _primary_archive(tmp_path, truncate=True)
    before = _state(tmp_path)
    with pytest.raises(Exception):
        service.restore_backup_for_ha_replica(archive)
    assert _state(tmp_path) == before


def test_ha_copy_failure_restores_replica(replica, monkeypatch):
    service, tmp_path = replica
    archive = _primary_archive(tmp_path)
    before = _state(tmp_path)
    real_copy_files = service._copy_files

    def copy_then_fail(src, dst):
        real_copy_files(src, dst)
        raise OSError("disk full")

    monkeypatch.setattr(service, "_copy_files", copy_then_fail)
    with pytest.raises(OSError):
        service.restore_backup_for_ha_replica(archive)
    after = _state(tmp_path)
    overwritten = ("az/config/", "knot-resolver/")
    assert {k: v for k, v in after.items() if not k.startswith(overwritten)} == {
        k: v for k, v in before.items() if not k.startswith(overwritten)
    }
    assert _names(tmp_path / "etc" / "openvpn") == ["easyrsa3"]
    assert _names(tmp_path / "etc" / "wireguard") == ["antizapret.conf", "extra.conf", "params"]
    assert _names(tmp_path / "antizapret" / "client") == ["amneziawg", "openvpn", "wireguard"]


def test_ha_restore_replaces_crypto_and_drops_profiles(replica):
    service, tmp_path = replica
    result = service.restore_backup_for_ha_replica(_primary_archive(tmp_path))
    assert result["ha_replica"] is True
    state = _state(tmp_path)
    assert state["openvpn/easyrsa3/pki/ca.crt"] == "primary-ca"
    assert state["wireguard/antizapret.conf"] == "primary-wg"
    assert "wireguard/extra.conf" not in state
    assert state["wireguard/params"] == "keep"
    assert state["az/config/include-hosts.txt"] == "example.com"
    assert state["knot-resolver/kresd.conf"] == "primary-knot"
    assert not any(k.startswith("az/client/") for k in state)
    assert _names(tmp_path / "etc" / "openvpn") == ["easyrsa3"]
    assert _names(tmp_path / "etc" / "wireguard") == ["antizapret.conf", "params"]


def test_ha_archive_without_pki_leaves_replica_intact(replica):
    service, tmp_path = replica
    archive = tmp_path / "backup-primary.tar.gz"
    archive.write_bytes(_tar({"wireguard/antizapret.conf": b"primary-wg", "config/include-hosts.txt": b"x"}))
    before = _state(tmp_path)
    with pytest.raises(RuntimeError, match="easyrsa3"):
        service.restore_backup_for_ha_replica(archive)
    assert _state(tmp_path) == before
