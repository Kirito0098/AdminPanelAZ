"""CLIENT_ISOLATION / DNS_WARP: старый числовой формат DNS_WARP панель не перезаписывает."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.antizapret_params import needs_antizapret_restart
from app.services.antizapret_settings import read_antizapret_settings, update_antizapret_settings


def _setup(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "setup"
    path.write_text(body, encoding="utf-8")
    return path


def test_dns_warp_numeric_legacy_is_shown_as_flag(tmp_path):
    path = _setup(tmp_path, "DNS_WARP=2\n")
    assert read_antizapret_settings(path)["DNS_WARP"] == "y"

    path.write_text("DNS_WARP=1\n", encoding="utf-8")
    assert read_antizapret_settings(path)["DNS_WARP"] == "n"


def test_dns_warp_y_n_is_read_as_is(tmp_path):
    path = _setup(tmp_path, "DNS_WARP=y\n")
    assert read_antizapret_settings(path)["DNS_WARP"] == "y"


def test_dns_warp_legacy_format_refuses_write(tmp_path):
    path = _setup(tmp_path, "DNS_WARP=2\n")

    with pytest.raises(ValueError, match="старый формат"):
        update_antizapret_settings(path, {"DNS_WARP": "n"})

    assert path.read_text(encoding="utf-8") == "DNS_WARP=2\n"


def test_dns_warp_new_format_is_written(tmp_path):
    path = _setup(tmp_path, "ANTIZAPRET_WARP=2\nVPN_WARP=1\nDNS_WARP=n\n")
    result = update_antizapret_settings(path, {"DNS_WARP": "y"})

    assert result["changes"] == 1
    assert "DNS_WARP=y\n" in path.read_text(encoding="utf-8")


def test_dns_warp_refused_on_old_setup_without_numeric_warp(tmp_path):
    path = _setup(tmp_path, "ANTIZAPRET_WARP=n\nVPN_WARP=n\n")

    with pytest.raises(ValueError, match="старом формате"):
        update_antizapret_settings(path, {"DNS_WARP": "y"})

    assert "DNS_WARP" not in path.read_text(encoding="utf-8")


def test_client_isolation_is_written(tmp_path):
    path = _setup(tmp_path, "CLIENT_ISOLATION=y\n")
    result = update_antizapret_settings(path, {"client_isolation": False})

    assert result["changes"] == 1
    assert "CLIENT_ISOLATION=n\n" in path.read_text(encoding="utf-8")


def test_runtime_restart_keys():
    assert needs_antizapret_restart({"client_isolation": "y"})
    assert needs_antizapret_restart({"DNS_WARP": "y"})
    assert needs_antizapret_restart({"restrict_forward": "y"})
    assert not needs_antizapret_restart({"ANTIZAPRET_ADBLOCK": "y"})
    assert not needs_antizapret_restart({})
