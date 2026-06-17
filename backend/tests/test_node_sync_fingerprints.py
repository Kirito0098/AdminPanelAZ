"""Fingerprint collection for node sync parity verify."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.services.node_sync.fingerprints import collect_antizapret_fingerprints


def test_config_fingerprint_ignores_warper_include_ips():
    tmp_dir = tempfile.mkdtemp(prefix="fp-test-")
    try:
        install_dir = Path(tmp_dir) / "antizapret"
        config_dir = install_dir / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "include-ips.txt").write_text("10.0.0.0/8\n", encoding="utf-8")

        without_warper = collect_antizapret_fingerprints(install_dir)
        assert "antizapret/config" in without_warper
        baseline = without_warper["antizapret/config"]

        (config_dir / "warper-include-ips.txt").write_text("192.0.2.0/24\n", encoding="utf-8")
        with_warper = collect_antizapret_fingerprints(install_dir)
        assert with_warper["antizapret/config"] == baseline
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
