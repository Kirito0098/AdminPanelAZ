import io
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models import VpnType
from app.services.antizapret import AntiZapretService
from app.services.node_sync import vpn_state_sync
from app.services.node_sync.replicate import (
    ReplicateOperation,
    _handle_client_create,
    _handle_client_delete,
    _handle_client_renew_cert,
)


def test_sync_wireguard_state_from_primary_copies_configs_profiles_and_applies_runtime():
    primary = MagicMock()
    replica = MagicMock()
    primary.read_wireguard_server_config.side_effect = lambda iface: f"{iface}-primary"
    replica.apply_wireguard_runtime.return_value = {"success": True, "synced": ["antizapret", "vpn"]}
    primary.export_wireguard_client_profiles_archive.return_value = _sample_profile_archive()

    vpn_state_sync.sync_wireguard_state_from_primary(primary, replica, client_name="test-1")

    assert replica.write_wireguard_server_config.call_args_list == [
        (("antizapret", "antizapret-primary"),),
        (("vpn", "vpn-primary"),),
    ]
    replica.apply_wireguard_runtime.assert_called_once()
    replica.import_wireguard_client_profiles_archive.assert_called_once()
    replica.recreate_profiles.assert_not_called()
    primary.export_easyrsa3_archive.assert_not_called()


def test_sync_wireguard_state_falls_back_to_per_client_profiles_when_archive_empty():
    primary = MagicMock()
    replica = MagicMock()
    primary.read_wireguard_server_config.return_value = "conf"
    replica.apply_wireguard_runtime.return_value = {"success": True, "synced": ["antizapret"]}
    primary.export_wireguard_client_profiles_archive.return_value = _empty_archive()
    primary.get_profile_files.return_value = [
        {"path": "/root/antizapret/client/wireguard/vpn/vpn-test-1-wg.conf"},
    ]
    primary.read_profile_file.return_value = "profile-content"

    vpn_state_sync.sync_wireguard_state_from_primary(primary, replica, client_name="test-1")

    replica.write_profile_file.assert_called_once_with(
        "/root/antizapret/client/wireguard/vpn/vpn-test-1-wg.conf",
        "profile-content",
    )
    replica.import_wireguard_client_profiles_archive.assert_not_called()


def test_sync_openvpn_pki_from_primary_imports_archive_and_restarts():
    primary = MagicMock()
    replica = MagicMock()
    primary.export_easyrsa3_archive.return_value = b"archive-bytes"

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    primary.export_easyrsa3_archive.assert_called_once()
    replica.import_easyrsa3_archive.assert_called_once_with(b"archive-bytes")
    replica.recreate_profiles.assert_called_once()


def test_sync_wireguard_state_continues_when_runtime_apply_fails():
    primary = MagicMock()
    replica = MagicMock()
    primary.read_wireguard_server_config.return_value = "conf"
    primary.export_wireguard_client_profiles_archive.return_value = _sample_profile_archive()
    replica.apply_wireguard_runtime.return_value = {
        "success": False,
        "errors": [{"interface": "vpn", "stderr": "sync failed"}],
    }

    vpn_state_sync.sync_wireguard_state_from_primary(primary, replica)

    replica.import_wireguard_client_profiles_archive.assert_called_once()


def test_antizapret_wireguard_server_config_roundtrip(tmp_path, monkeypatch):
    wg_dir = tmp_path / "wireguard"
    wg_dir.mkdir()
    monkeypatch.setattr(
        "app.services.antizapret.WIREGUARD_SERVER_CONFIG_DIR",
        wg_dir,
    )
    service = AntiZapretService(base_path=tmp_path)

    service.write_wireguard_server_config("antizapret", "[Interface]\nPrivateKey = x\n")
    assert service.read_wireguard_server_config("antizapret") == "[Interface]\nPrivateKey = x\n"

    with pytest.raises(HTTPException):
        service.read_wireguard_server_config("invalid")


def test_antizapret_export_easyrsa3_archive_contains_pki_files(tmp_path, monkeypatch):
    easyrsa_root = tmp_path / "easyrsa3" / "pki"
    easyrsa_root.mkdir(parents=True)
    (easyrsa_root / "ca.crt").write_text("ca-data", encoding="utf-8")
    (easyrsa_root / "index.txt").write_text("V\t123", encoding="utf-8")

    monkeypatch.setattr("app.services.antizapret.EASYRSA3_ROOT", tmp_path / "easyrsa3")
    service = AntiZapretService(base_path=tmp_path)
    archive = service.export_easyrsa3_archive()

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        names = tar.getnames()

    assert "easyrsa3/pki/ca.crt" in names
    assert "easyrsa3/pki/index.txt" in names


def test_handle_client_create_uses_crypto_sync(monkeypatch):
    primary_config = MagicMock()
    primary_config.client_name = "alice"
    primary_config.vpn_type = VpnType.wireguard
    primary_config.id = 10
    primary_config.owner_id = 1
    primary_config.cert_expire_days = None
    primary_config.description = None

    group = MagicMock()
    group.id = 1
    group.primary_node_id = 1

    replica_node = MagicMock()
    replica_node.id = 2
    replica_node.name = "replica-1"
    replica_adapter = MagicMock()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.get.return_value = replica_node

    primary_adapter = MagicMock()
    monkeypatch.setattr(
        "app.services.node_sync.replicate._primary_adapter",
        lambda _db, _group: primary_adapter,
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.iter_replica_adapters",
        lambda _db, _group: iter([(replica_node, replica_adapter)]),
    )
    sync_mock = MagicMock()
    monkeypatch.setattr("app.services.node_sync.replicate.sync_vpn_crypto_from_primary", sync_mock)

    result = _handle_client_create(db, group, {"primary_config": primary_config})

    sync_mock.assert_called_once_with(
        primary_adapter,
        replica_adapter,
        VpnType.wireguard,
        client_name="alice",
    )
    replica_adapter.add_wireguard_client.assert_not_called()
    assert len(result.successes) == 1
    assert result.successes[0]["node_id"] == 2
    assert result.errors == []


def test_handle_client_create_records_partial_failure(monkeypatch):
    primary_config = MagicMock()
    primary_config.client_name = "bob"
    primary_config.vpn_type = VpnType.openvpn
    primary_config.id = 11
    primary_config.owner_id = 1
    primary_config.cert_expire_days = 365
    primary_config.description = "test"

    group = MagicMock()
    group.id = 2
    group.primary_node_id = 1

    replica_node = MagicMock()
    replica_node.id = 3
    replica_node.name = "replica-2"
    replica_adapter = MagicMock()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.get.return_value = replica_node

    monkeypatch.setattr(
        "app.services.node_sync.replicate._primary_adapter",
        lambda _db, _group: MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.iter_replica_adapters",
        lambda _db, _group: iter([(replica_node, replica_adapter)]),
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.sync_vpn_crypto_from_primary",
        MagicMock(side_effect=RuntimeError("replica offline")),
    )

    result = _handle_client_create(db, group, {"primary_config": primary_config})

    assert result.successes == []
    assert len(result.errors) == 1
    assert result.errors[0]["node_name"] == "replica-2"


def test_handle_client_delete_syncs_crypto_from_primary(monkeypatch):
    primary_config = MagicMock()
    primary_config.id = 20

    shadow = MagicMock()
    shadow.node_id = 4
    shadow.client_name = "carol"
    shadow.vpn_type = VpnType.wireguard
    shadow.id = 40

    group = MagicMock()
    group.primary_node_id = 1

    replica_node = MagicMock()
    replica_node.id = 4
    replica_node.name = "replica-3"
    replica_adapter = MagicMock()

    db = MagicMock()
    db.get.return_value = replica_node

    primary_adapter = MagicMock()
    monkeypatch.setattr(
        "app.services.node_sync.replicate._primary_adapter",
        lambda _db, _group: primary_adapter,
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_shadow_configs",
        lambda _db, _group, _cfg: [shadow],
    )
    sync_mock = MagicMock()
    monkeypatch.setattr("app.services.node_sync.replicate.sync_vpn_crypto_from_primary", sync_mock)
    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_adapter_for_node",
        lambda _node: replica_adapter,
    )

    result = _handle_client_delete(db, group, {"primary_config": primary_config})

    sync_mock.assert_called_once_with(
        primary_adapter,
        replica_adapter,
        VpnType.wireguard,
    )
    replica_adapter.delete_wireguard_client.assert_not_called()
    assert result.successes == [{"node_id": 4, "config_id": 40}]
    db.delete.assert_called_once_with(shadow)


def test_handle_client_renew_cert_syncs_openvpn_pki(monkeypatch):
    primary_config = MagicMock()
    primary_config.client_name = "dave"
    primary_config.vpn_type = VpnType.openvpn
    primary_config.id = 30

    shadow = MagicMock()
    shadow.node_id = 5
    shadow.id = 50

    group = MagicMock()
    group.primary_node_id = 1

    replica_node = MagicMock()
    replica_node.id = 5
    replica_node.name = "replica-4"

    db = MagicMock()

    primary_adapter = MagicMock()
    replica_adapter = MagicMock()
    monkeypatch.setattr(
        "app.services.node_sync.replicate._primary_adapter",
        lambda _db, _group: primary_adapter,
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_shadow_configs",
        lambda _db, _group, _cfg: [shadow],
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_replica_nodes",
        lambda _db, _group: [replica_node],
    )
    monkeypatch.setattr(
        "app.services.node_sync.replicate.get_adapter_for_node",
        lambda _node: replica_adapter,
    )
    sync_mock = MagicMock()
    monkeypatch.setattr("app.services.node_sync.replicate.sync_openvpn_pki_from_primary", sync_mock)

    result = _handle_client_renew_cert(
        db,
        group,
        {"primary_config": primary_config, "cert_expire_days": 180},
    )

    sync_mock.assert_called_once_with(primary_adapter, replica_adapter)
    assert result.operation == ReplicateOperation.CLIENT_RENEW_CERT
    assert result.successes == [{"node_id": 5, "config_id": 50}]
    assert shadow.cert_expire_days == 180


def _empty_archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz"):
        pass
    return buffer.getvalue()


def _sample_profile_archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        data = b"[Interface]\nPrivateKey = test\n"
        info = tarfile.TarInfo(name="client/wireguard/vpn/vpn-test-wg.conf")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()
