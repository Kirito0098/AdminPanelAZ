from pathlib import Path

import pytest

from app.services.antizapret_settings import (
    build_schema,
    choice_write_mismatch_warnings,
    normalize_choice_settings,
    read_antizapret_settings,
    update_antizapret_settings,
)


def test_schema_exposes_warp_choices():
    by_key = {field["key"]: field for field in build_schema()}
    assert by_key["ANTIZAPRET_WARP"]["type"] == "choice"
    assert [opt["value"] for opt in by_key["ANTIZAPRET_WARP"]["options"]] == ["1", "2", "3", "4"]
    assert [opt["value"] for opt in by_key["VPN_WARP"]["options"]] == ["1", "2"]
    assert by_key["WARP_PROTECTION"]["type"] == "flag"
    assert "options" not in by_key["WARP_PROTECTION"]


def test_read_numeric_values(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=3\nVPN_WARP=2\nWARP_PROTECTION=y\n", encoding="utf-8")
    settings = read_antizapret_settings(setup)
    assert settings["ANTIZAPRET_WARP"] == "3"
    assert settings["VPN_WARP"] == "2"
    assert settings["WARP_PROTECTION"] == "y"


def test_read_legacy_yn_as_numeric(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=y\nVPN_WARP=n\n", encoding="utf-8")
    settings = read_antizapret_settings(setup)
    assert settings["ANTIZAPRET_WARP"] == "2"
    assert settings["VPN_WARP"] == "1"
    assert settings["WARP_PROTECTION"] == "n"


def test_read_missing_uses_default(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ROUTE_ALL=n\n", encoding="utf-8")
    settings = read_antizapret_settings(setup)
    assert settings["ANTIZAPRET_WARP"] == "1"
    assert settings["VPN_WARP"] == "1"


def test_write_numeric_format(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=1\nVPN_WARP=1\n", encoding="utf-8")
    update_antizapret_settings(setup, {"ANTIZAPRET_WARP": "4", "VPN_WARP": "2", "WARP_PROTECTION": "y"})
    content = setup.read_text(encoding="utf-8")
    assert "ANTIZAPRET_WARP=4\n" in content
    assert "VPN_WARP=2\n" in content
    assert "WARP_PROTECTION=y\n" in content


def test_write_missing_key_uses_numeric(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ROUTE_ALL=n\n", encoding="utf-8")
    update_antizapret_settings(setup, {"ANTIZAPRET_WARP": "y"})
    assert "ANTIZAPRET_WARP=2\n" in setup.read_text(encoding="utf-8")


def test_write_keeps_legacy_yn_format(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=n\nVPN_WARP=y\n", encoding="utf-8")
    update_antizapret_settings(setup, {"ANTIZAPRET_WARP": "2", "VPN_WARP": "1"})
    content = setup.read_text(encoding="utf-8")
    assert "ANTIZAPRET_WARP=y\n" in content
    assert "VPN_WARP=n\n" in content


def test_legacy_format_rejects_selective_modes(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Обновите AntiZapret-VPN"):
        update_antizapret_settings(setup, {"ANTIZAPRET_WARP": "3"})
    assert setup.read_text(encoding="utf-8") == "ANTIZAPRET_WARP=n\n"


def test_invalid_choice_rejected(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="VPN_WARP"):
        update_antizapret_settings(setup, {"VPN_WARP": "4"})


def test_normalize_choice_settings_maps_old_agent_values():
    settings = normalize_choice_settings({"ANTIZAPRET_WARP": "y", "VPN_WARP": "n", "ROUTE_ALL": "y"})
    assert settings == {"ANTIZAPRET_WARP": "2", "VPN_WARP": "1", "ROUTE_ALL": "y"}


def test_mismatch_warning_for_old_agent():
    warnings = choice_write_mismatch_warnings({"ANTIZAPRET_WARP": "3"}, {"ANTIZAPRET_WARP": "n"})
    assert len(warnings) == 1
    assert "node agent" in warnings[0]
    assert choice_write_mismatch_warnings({"ANTIZAPRET_WARP": "2"}, {"ANTIZAPRET_WARP": "y"}) == []
