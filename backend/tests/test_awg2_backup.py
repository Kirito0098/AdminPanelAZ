import asyncio
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import UploadFile

from app.routers import awg2 as awg2_router
from app.services import awg2


def _seed_awg2_tree(tmp_path: Path, *, with_expiry: bool = True) -> None:
    amnezia = tmp_path / "amnezia"
    clients_az = tmp_path / "overlay" / "clients" / "antizapret"
    clients_vpn = tmp_path / "overlay" / "clients" / "vpn"
    amnezia.mkdir(parents=True)
    clients_az.mkdir(parents=True)
    clients_vpn.mkdir(parents=True)

    (amnezia / "antizapret-awg.conf").write_text("[Interface]\nPrivateKey = aaa=\n", encoding="utf-8")
    (amnezia / "services.env").write_text("AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\n", encoding="utf-8")
    (clients_az / "antizapret-ivan-am.conf").write_text("[Interface]\n", encoding="utf-8")
    (clients_vpn / "vpn-ivan-am.conf").write_text("[Interface]\n", encoding="utf-8")
    if with_expiry:
        (tmp_path / "overlay" / "expiry.tsv").write_text(
            "ivan\tantizapret\t1893456000\n",
            encoding="utf-8",
        )

    # Noise that must never leak into the narrow archive.
    (tmp_path / "overlay" / "stats.db").write_bytes(b"sqlite")
    (tmp_path / "overlay" / "clients" / "venv" / "ignored.txt").parent.mkdir(parents=True)
    (tmp_path / "overlay" / "clients" / "venv" / "ignored.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "amnezia" / "__pycache__" / "ignored.pyc").parent.mkdir(parents=True)
    (tmp_path / "amnezia" / "__pycache__" / "ignored.pyc").write_bytes(b"compiled")
    (tmp_path / "overlay" / "openvpn").mkdir(parents=True)
    (tmp_path / "overlay" / "openvpn" / "server.conf").write_text("ovpn", encoding="utf-8")


async def _read_streaming_response(response) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


def test_export_narrow_backup_contains_only_expected_members(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_EXPIRY_TSV", tmp_path / "overlay" / "expiry.tsv"),
    ):
        data = awg2.Awg2Service().export_narrow_backup()

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        names = archive.getnames()
        manifest = archive.extractfile("MANIFEST").read().decode("utf-8")

    assert "kind=az-awg2-narrow-backup" in manifest
    assert "MANIFEST" in names
    assert "awgstate/expiry.tsv" in names
    assert "amneziawg/antizapret-awg.conf" in names
    assert "clients/antizapret/antizapret-ivan-am.conf" in names
    assert "clients/vpn/vpn-ivan-am.conf" in names
    assert all(
        name == "MANIFEST"
        or name.startswith("amneziawg/")
        or name.startswith("clients/")
        or name == "awgstate/expiry.tsv"
        for name in names
    )
    assert not any(
        "stats.db" in name
        or "/venv/" in f"/{name}/"
        or "__pycache__" in name
        or name.startswith("openvpn/")
        or name.startswith("config/")
        or name.startswith("knot/")
        or name.startswith("client/")
        for name in names
    )


def test_export_narrow_backup_skips_missing_expiry(tmp_path: Path):
    _seed_awg2_tree(tmp_path, with_expiry=False)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_EXPIRY_TSV", tmp_path / "overlay" / "expiry.tsv"),
    ):
        data = awg2.Awg2Service().export_narrow_backup()

    names = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz").getnames()
    assert "MANIFEST" in names
    assert "awgstate/expiry.tsv" not in names


def test_import_narrow_backup_rejects_wrong_manifest_kind_before_mutation(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")
    original_conf = (tmp_path / "amnezia" / "antizapret-awg.conf").read_text(encoding="utf-8")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        conf_bytes = b"[Interface]\nPrivateKey = bbb=\n"
        conf_info = tarfile.TarInfo(name="amneziawg/antizapret-awg.conf")
        conf_info.size = len(conf_bytes)
        archive.addfile(conf_info, io.BytesIO(conf_bytes))

        client_bytes = b"[Interface]\n"
        client_info = tarfile.TarInfo(name="clients/antizapret/antizapret-ivan-am.conf")
        client_info.size = len(client_bytes)
        archive.addfile(client_info, io.BytesIO(client_bytes))

        manifest_bytes = b"kind=az-awg2-state\n"
        manifest_info = tarfile.TarInfo(name="MANIFEST")
        manifest_info.size = len(manifest_bytes)
        archive.addfile(manifest_info, io.BytesIO(manifest_bytes))

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_EXPIRY_TSV", tmp_path / "overlay" / "expiry.tsv"),
    ):
        service = awg2.Awg2Service()
        try:
            service.import_narrow_backup(buffer.getvalue())
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "MANIFEST kind must be az-awg2-narrow-backup" in str(exc)

    assert (tmp_path / "amnezia" / "antizapret-awg.conf").read_text(encoding="utf-8") == original_conf


def test_import_narrow_backup_rejects_forbidden_members_before_mutation(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")
    original_conf = (tmp_path / "amnezia" / "antizapret-awg.conf").read_text(encoding="utf-8")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        manifest_bytes = b"kind=az-awg2-narrow-backup\n"
        manifest_info = tarfile.TarInfo(name="MANIFEST")
        manifest_info.size = len(manifest_bytes)
        archive.addfile(manifest_info, io.BytesIO(manifest_bytes))

        conf_bytes = b"[Interface]\nPrivateKey = bbb=\n"
        conf_info = tarfile.TarInfo(name="amneziawg/antizapret-awg.conf")
        conf_info.size = len(conf_bytes)
        archive.addfile(conf_info, io.BytesIO(conf_bytes))

        client_bytes = b"[Interface]\n"
        client_info = tarfile.TarInfo(name="clients/antizapret/antizapret-ivan-am.conf")
        client_info.size = len(client_bytes)
        archive.addfile(client_info, io.BytesIO(client_bytes))

        forbidden_bytes = b"secret"
        forbidden_info = tarfile.TarInfo(name="openvpn/server.conf")
        forbidden_info.size = len(forbidden_bytes)
        archive.addfile(forbidden_info, io.BytesIO(forbidden_bytes))

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_EXPIRY_TSV", tmp_path / "overlay" / "expiry.tsv"),
    ):
        service = awg2.Awg2Service()
        try:
            service.import_narrow_backup(buffer.getvalue())
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "forbidden member: openvpn/server.conf" in str(exc)

    assert (tmp_path / "amnezia" / "antizapret-awg.conf").read_text(encoding="utf-8") == original_conf


def test_import_narrow_backup_replaces_trees_and_clears_missing_expiry(tmp_path: Path):
    _seed_awg2_tree(tmp_path)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        manifest_bytes = b"kind=az-awg2-narrow-backup\n"
        manifest_info = tarfile.TarInfo(name="MANIFEST")
        manifest_info.size = len(manifest_bytes)
        archive.addfile(manifest_info, io.BytesIO(manifest_bytes))

        conf_bytes = b"[Interface]\nPrivateKey = fresh=\n"
        conf_info = tarfile.TarInfo(name="amneziawg/antizapret-awg.conf")
        conf_info.size = len(conf_bytes)
        archive.addfile(conf_info, io.BytesIO(conf_bytes))

        client_bytes = b"[Interface]\nAddress = 10.0.0.2/32\n"
        client_info = tarfile.TarInfo(name="clients/vpn/vpn-petr-am.conf")
        client_info.size = len(client_bytes)
        archive.addfile(client_info, io.BytesIO(client_bytes))

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", tmp_path / "overlay"),
        patch.object(awg2, "AWG2_CLIENT_DIR", tmp_path / "overlay" / "clients"),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", tmp_path / "amnezia"),
        patch.object(awg2, "AWG2_EXPIRY_TSV", tmp_path / "overlay" / "expiry.tsv"),
    ):
        service = awg2.Awg2Service()
        service.import_narrow_backup(buffer.getvalue())

    assert (tmp_path / "amnezia" / "antizapret-awg.conf").read_text(encoding="utf-8") == (
        "[Interface]\nPrivateKey = fresh=\n"
    )
    assert not (tmp_path / "overlay" / "clients" / "antizapret").exists()
    assert (tmp_path / "overlay" / "clients" / "vpn" / "vpn-petr-am.conf").read_text(encoding="utf-8") == (
        "[Interface]\nAddress = 10.0.0.2/32\n"
    )
    assert not (tmp_path / "overlay" / "expiry.tsv").exists()


def test_awg2_backup_route_streams_archive():
    adapter = MagicMock()
    adapter.export_awg2_backup.return_value = b"archive-bytes"

    with patch.object(awg2_router, "get_active_adapter", return_value=adapter):
        response = awg2_router.awg2_backup(db=MagicMock(), _=SimpleNamespace())

    body = asyncio.run(_read_streaming_response(response))
    assert body == b"archive-bytes"
    assert response.media_type == "application/gzip"
    assert response.headers["content-disposition"] == 'attachment; filename="az-awg2-backup.tar.gz"'
    adapter.export_awg2_backup.assert_called_once_with()


def test_awg2_restore_route_calls_runtime_and_ha_sync():
    adapter = MagicMock()
    adapter.restore_awg2_backup.return_value = {"success": True, "synced": ["antizapret-awg"]}
    node = SimpleNamespace(id=1, name="node-1", host="10.0.0.1")
    upload = UploadFile(filename="narrow-backup.tar.gz", file=io.BytesIO(b"payload"))

    with (
        patch.object(awg2_router, "get_active_node", return_value=node),
        patch.object(awg2_router, "get_active_adapter", return_value=adapter),
        patch.object(
            awg2_router,
            "_ha_sync_awg2_from_active",
            return_value={"attempted": True, "errors": [{"node_name": "replica-1", "error": "down"}]},
        ),
    ):
        result = asyncio.run(awg2_router.awg2_restore(archive=upload, db=MagicMock(), _=SimpleNamespace()))

    assert result["message"] == "AZ-AWG2 восстановлен из бэкапа"
    assert result["runtime"]["success"] is True
    assert result["ha"]["errors"][0]["node_name"] == "replica-1"
    assert result["node_id"] == 1
    adapter.restore_awg2_backup.assert_called_once_with(b"payload", "narrow-backup.tar.gz")
