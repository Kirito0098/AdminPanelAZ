from pathlib import Path

from app.services.antizapret_params import ANTIZAPRET_PARAMS, KNOWN_SETTING_KEYS
from app.services.antizapret_settings import read_antizapret_settings, update_antizapret_settings


def test_adblock_params_replace_block_ads():
    keys = {p["key"] for p in ANTIZAPRET_PARAMS}
    assert "block_ads" not in keys
    assert "ANTIZAPRET_ADBLOCK" in keys
    assert "VPN_ADBLOCK" in keys
    assert "ANTIZAPRET_ADBLOCK" in KNOWN_SETTING_KEYS
    assert "VPN_ADBLOCK" in KNOWN_SETTING_KEYS


def test_read_legacy_block_ads_as_antizapret_adblock(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("BLOCK_ADS=y\nROUTE_ALL=n\n", encoding="utf-8")
    settings = read_antizapret_settings(setup)
    assert settings["ANTIZAPRET_ADBLOCK"] == "y"
    assert settings["VPN_ADBLOCK"] == "n"


def test_read_prefers_antizapret_adblock_over_legacy(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_ADBLOCK=n\nBLOCK_ADS=y\nVPN_ADBLOCK=y\n", encoding="utf-8")
    settings = read_antizapret_settings(setup)
    assert settings["ANTIZAPRET_ADBLOCK"] == "n"
    assert settings["VPN_ADBLOCK"] == "y"


def test_update_migrates_block_ads_line(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("BLOCK_ADS=n\n", encoding="utf-8")
    result = update_antizapret_settings(setup, {"ANTIZAPRET_ADBLOCK": "y", "VPN_ADBLOCK": "y"})
    assert result["success"] is True
    content = setup.read_text(encoding="utf-8")
    assert "ANTIZAPRET_ADBLOCK=y" in content
    assert "VPN_ADBLOCK=y" in content
    assert "BLOCK_ADS=" not in content


def test_update_accepts_legacy_block_ads_key(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_ADBLOCK=n\n", encoding="utf-8")
    result = update_antizapret_settings(setup, {"block_ads": "y"})
    assert result["success"] is True
    assert "ANTIZAPRET_ADBLOCK=y" in setup.read_text(encoding="utf-8")
