"""Tests for HA replica restore (wipe + replace, no client.sh 7)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.antizapret_backup import AntizapretBackupService, wipe_ha_vpn_crypto_paths


def test_wipe_ha_vpn_crypto_paths_removes_pki_wireguard_and_profiles(tmp_path, monkeypatch):
    install_dir = tmp_path / "antizapret"
    install_dir.mkdir()
    easyrsa = tmp_path / "easyrsa3"
    (easyrsa / "pki").mkdir(parents=True)
    (easyrsa / "pki" / "ca.crt").write_text("ca", encoding="utf-8")
    wg_dir = tmp_path / "wireguard"
    wg_dir.mkdir()
    (wg_dir / "antizapret.conf").write_text("wg", encoding="utf-8")
    (wg_dir / "extra.conf").write_text("old", encoding="utf-8")
    ovpn_dir = install_dir / "client" / "openvpn" / "vpn"
    ovpn_dir.mkdir(parents=True)
    (ovpn_dir / "x.ovpn").write_text("ovpn", encoding="utf-8")
    wg_profiles = install_dir / "client" / "wireguard" / "vpn"
    wg_profiles.mkdir(parents=True)
    (wg_profiles / "a.conf").write_text("profile", encoding="utf-8")

    monkeypatch.setattr("app.services.antizapret_backup._HA_EASYRSA3_ROOT", easyrsa)
    monkeypatch.setattr("app.services.antizapret_backup._HA_WIREGUARD_DIR", wg_dir)

    wipe_ha_vpn_crypto_paths(install_dir=install_dir)

    assert not easyrsa.exists()
    assert list(wg_dir.glob("*.conf")) == []
    assert not (install_dir / "client" / "openvpn").exists()
    assert not (install_dir / "client" / "wireguard").exists()


def test_restore_backup_for_ha_replica_skips_client_sh_7(tmp_path, monkeypatch):
    install_dir = tmp_path / "antizapret"
    install_dir.mkdir()
    (install_dir / "client.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (install_dir / "client.sh").chmod(0o755)

    archive = tmp_path / "backup.tar.gz"
    import tarfile

    extract_root = tmp_path / "extract"
    (extract_root / "easyrsa3" / "pki").mkdir(parents=True)
    (extract_root / "easyrsa3" / "pki" / "index.txt").write_text("V", encoding="utf-8")
    (extract_root / "wireguard").mkdir()
    (extract_root / "wireguard" / "antizapret.conf").write_text("[Interface]", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(extract_root / "easyrsa3", arcname="easyrsa3")
        tar.add(extract_root / "wireguard", arcname="wireguard")

    service = AntizapretBackupService(install_dir=install_dir, timeout_seconds=30)
    wipe_mock = MagicMock()
    monkeypatch.setattr("app.services.antizapret_backup.wipe_ha_vpn_crypto_paths", wipe_mock)
    monkeypatch.setattr(service, "_run_client_sh_7", MagicMock(side_effect=AssertionError("sh7 must not run")))
    monkeypatch.setattr(service, "_restart_legacy_services", MagicMock())
    monkeypatch.setattr(service, "_run_doall_sh", lambda: "")

    easyrsa_dst = tmp_path / "dst_easyrsa3"
    wg_dst = tmp_path / "dst_wg"
    monkeypatch.setattr(service, "_copy_tree", lambda src, dst: easyrsa_dst.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(service, "_copy_files", lambda src, dst: wg_dst.mkdir(parents=True, exist_ok=True))

    result = service.restore_backup_for_ha_replica(archive)

    wipe_mock.assert_called_once()
    assert result.get("ha_replica") is True
