"""Пути mTLS и AntiZapret по умолчанию берутся из Settings, а не из литералов."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import antizapret_backup, node_agent_env, node_agent_provision


def test_agent_mtls_files_follow_configured_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = SimpleNamespace(
        node_agent_mtls_dir=tmp_path,
        node_agent_mtls_ca_cert=str(tmp_path / "ca.crt"),
    )
    monkeypatch.setattr(node_agent_env, "get_settings", lambda: settings)

    files = dict(node_agent_env._mtls_env_paths())

    assert files["NODE_AGENT_MTLS_SERVER_CERT"] == tmp_path / "agent.crt"
    assert files["NODE_AGENT_MTLS_SERVER_KEY"] == tmp_path / "agent.key"
    assert files["NODE_AGENT_MTLS_CA_CERT"] == tmp_path / "ca.crt"


def test_provisioning_mtls_paths_follow_configured_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    for name in (
        "NODE_AGENT_MTLS_CA_CERT",
        "NODE_AGENT_MTLS_SERVER_CERT",
        "NODE_AGENT_MTLS_SERVER_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = SimpleNamespace(
        node_agent_mtls_dir=tmp_path,
        node_agent_mtls_ca_cert=str(tmp_path / "ca.crt"),
    )
    monkeypatch.setattr(node_agent_provision, "get_settings", lambda: settings)

    paths = node_agent_provision._mtls_paths()

    assert paths["ca_cert"] == tmp_path / "ca.crt"
    assert paths["server_cert"] == tmp_path / "agent.crt"
    assert paths["server_key"] == tmp_path / "agent.key"


def test_ha_crypto_paths_use_configured_antizapret_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(
        antizapret_backup,
        "get_settings",
        lambda: SimpleNamespace(antizapret_path=tmp_path),
    )

    paths = antizapret_backup.ha_vpn_crypto_paths()

    assert tmp_path / "client" / "openvpn" in paths
    assert tmp_path / "client" / "wireguard" in paths
