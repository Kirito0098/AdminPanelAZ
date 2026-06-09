"""Tests for panel-side mTLS certificate generation and storage."""

from __future__ import annotations

import stat

import pytest

from app.config import Settings
from app.services import node_mtls_certs as svc


@pytest.fixture()
def mtls_settings(tmp_path, monkeypatch):
    mtls_dir = tmp_path / "mtls"
    settings = Settings(node_agent_mtls_dir=mtls_dir)
    monkeypatch.setattr("app.services.node_mtls_certs.get_settings", lambda: settings)
    return mtls_dir


def test_panel_mtls_ready_false_before_ensure(mtls_settings):
    assert svc.panel_mtls_ready() is False


def test_ensure_panel_mtls_materials_creates_ca_and_panel(mtls_settings):
    paths = svc.ensure_panel_mtls_materials()

    assert paths.ca_cert.is_file()
    assert paths.ca_key.is_file()
    assert paths.panel_cert.is_file()
    assert paths.panel_key.is_file()
    assert svc.panel_mtls_ready() is True


def test_ensure_panel_mtls_materials_is_idempotent(mtls_settings):
    first = svc.ensure_panel_mtls_materials()
    second = svc.ensure_panel_mtls_materials()

    assert first.ca_cert.read_bytes() == second.ca_cert.read_bytes()
    assert first.panel_key.read_bytes() == second.panel_key.read_bytes()


def test_file_permissions(mtls_settings):
    svc.ensure_panel_mtls_materials()
    svc.generate_agent_cert_for_node(1, "node-one")

    root_mode = stat.S_IMODE(mtls_settings.stat().st_mode)
    assert root_mode == 0o700

    node_dir = mtls_settings / "nodes" / "1"
    assert stat.S_IMODE(node_dir.stat().st_mode) == 0o700

    for key_path in (
        mtls_settings / "ca.key",
        mtls_settings / "panel.key",
        node_dir / "agent.key",
    ):
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600

    for cert_path in (
        mtls_settings / "ca.crt",
        mtls_settings / "panel.crt",
        node_dir / "agent.crt",
    ):
        assert stat.S_IMODE(cert_path.stat().st_mode) == 0o644


def test_generate_agent_cert_per_node_unique_keys(mtls_settings):
    svc.ensure_panel_mtls_materials()

    agent1 = svc.generate_agent_cert_for_node(1, "alpha")
    agent2 = svc.generate_agent_cert_for_node(2, "beta")

    assert agent1.agent_key.read_bytes() != agent2.agent_key.read_bytes()
    assert agent1.agent_cert.read_bytes() != agent2.agent_cert.read_bytes()
    assert agent1.agent_cert.parent == mtls_settings / "nodes" / "1"
    assert agent2.agent_cert.parent == mtls_settings / "nodes" / "2"


def test_generate_agent_cert_requires_panel_materials(mtls_settings):
    with pytest.raises(RuntimeError, match="ensure_panel_mtls_materials"):
        svc.generate_agent_cert_for_node(1, "node")


def test_read_agent_bundle_for_node(mtls_settings):
    svc.ensure_panel_mtls_materials()
    svc.generate_agent_cert_for_node(3, "gamma")

    bundle = svc.read_agent_bundle_for_node(3)

    assert "BEGIN CERTIFICATE" in bundle.ca_pem
    assert "BEGIN CERTIFICATE" in bundle.agent_cert_pem
    assert "BEGIN RSA PRIVATE KEY" in bundle.agent_key_pem or "BEGIN PRIVATE KEY" in bundle.agent_key_pem
    assert bundle.ca_pem.strip().endswith("-----END CERTIFICATE-----")


def test_read_agent_bundle_missing_raises(mtls_settings):
    svc.ensure_panel_mtls_materials()

    with pytest.raises(FileNotFoundError):
        svc.read_agent_bundle_for_node(99)


def test_get_panel_mtls_status_before_ensure(mtls_settings):
    status = svc.get_panel_mtls_status()

    assert status["ready"] is False
    assert status["writable"] is True
    assert status["mtls_dir"] == str(mtls_settings)
    assert status["ca_cert"] == str(mtls_settings / "ca.crt")
    assert status["agent_certs_count"] == 0


def test_get_panel_mtls_status_after_agent_certs(mtls_settings):
    svc.ensure_panel_mtls_materials()
    svc.generate_agent_cert_for_node(1, "one")
    svc.generate_agent_cert_for_node(2, "two")

    status = svc.get_panel_mtls_status()

    assert status["ready"] is True
    assert status["writable"] is True
    assert status["agent_certs_count"] == 2
