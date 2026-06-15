"""AntiZapret restore from backup archive tests."""

from __future__ import annotations

import os
import shutil
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.antizapret_backup import AntizapretBackupService


class AntizapretRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="az-restore-test-")
        self.install_dir = Path(self.tmp_dir) / "antizapret"
        self.install_dir.mkdir(parents=True)
        self.root_dir = Path(self.tmp_dir) / "root"
        self.root_dir.mkdir(parents=True)
        self.easyrsa_dst = Path(self.tmp_dir) / "etc" / "openvpn" / "easyrsa3" / "pki"
        self.wg_dst = Path(self.tmp_dir) / "etc" / "wireguard"
        self.config_dst = self.install_dir / "config"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_client_sh(self):
        script = self.install_dir / "client.sh"
        script.write_text("#!/bin/bash\necho recreate ok\n", encoding="utf-8")
        os.chmod(script, stat.S_IRWXU)
        doall = self.install_dir / "doall.sh"
        doall.write_text("#!/bin/bash\necho apply ok\n", encoding="utf-8")
        os.chmod(doall, stat.S_IRWXU)

    def _build_archive(self) -> Path:
        extract_layout = self.root_dir
        easyrsa = extract_layout / "easyrsa3" / "pki"
        easyrsa.mkdir(parents=True)
        (easyrsa / "ca.crt").write_text("ca-data", encoding="utf-8")
        wg = extract_layout / "wireguard"
        wg.mkdir(parents=True)
        (wg / "wg0.conf").write_text("[Interface]\n", encoding="utf-8")
        cfg = extract_layout / "config"
        cfg.mkdir(parents=True)
        (cfg / "test.conf").write_text("x=1", encoding="utf-8")
        archive = self.install_dir / "backup-test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name in ("easyrsa3", "wireguard", "config"):
                tar.add(extract_layout / name, arcname=name)
        return archive

    def test_restore_backup_copies_files(self):
        self._write_client_sh()
        archive = self._build_archive()
        service = AntizapretBackupService(install_dir=self.install_dir, timeout_seconds=30)

        with patch.object(service, "_copy_tree") as copy_tree, patch.object(service, "_copy_files") as copy_files, patch(
            "subprocess.run"
        ) as run_mock:
            run_mock.return_value = type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
            result = service.restore_backup(str(archive))

        assert copy_tree.called
        assert copy_files.call_count >= 2
        assert result["archive_name"] == archive.name
