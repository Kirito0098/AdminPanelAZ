"""WARP_MTU: optional number param of the AntiZapret setup file."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.antizapret_params import ANTIZAPRET_PARAMS
from app.services.antizapret_settings import (
    build_schema,
    normalize_number,
    read_antizapret_settings,
    setting_write_mismatch_warnings,
    update_antizapret_settings,
)

WARP_MTU = next(p for p in ANTIZAPRET_PARAMS if p["key"] == "WARP_MTU")


@pytest.mark.parametrize(
    ("value", "expected"), [("", ""), (None, ""), ("  ", ""), ("1280", "1280"), (" 0576 ", "576"), (1500, "1500")]
)
def test_normalize_number_accepts_empty_and_range(value, expected):
    assert normalize_number(WARP_MTU, value) == expected


@pytest.mark.parametrize("value", ["575", "1501", "-1", "12.5", "abc", "1280 # x"])
def test_normalize_number_rejects_out_of_range(value):
    with pytest.raises(ValueError, match="WARP_MTU"):
        normalize_number(WARP_MTU, value)


def test_schema_exposes_number_limits():
    (field,) = [item for item in build_schema() if item["key"] == "WARP_MTU"]

    assert (field["type"], field["min"], field["max"], field["placeholder"]) == ("number", 576, 1500, "1280")


def test_read_missing_or_commented_value(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=3\n", encoding="utf-8")
    assert read_antizapret_settings(setup)["WARP_MTU"] == ""

    setup.write_text("WARP_MTU=1380 # tuned\n", encoding="utf-8")
    assert read_antizapret_settings(setup)["WARP_MTU"] == "1380"


def test_update_replaces_existing_value(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=3\nWARP_MTU=1280\n", encoding="utf-8")

    update_antizapret_settings(setup, {"WARP_MTU": "1380"})

    assert setup.read_text(encoding="utf-8") == "ANTIZAPRET_WARP=3\nWARP_MTU=1380\n"


def test_update_appends_value_only_when_set(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=3\n", encoding="utf-8")

    update_antizapret_settings(setup, {"WARP_MTU": ""})
    assert "WARP_MTU" not in setup.read_text(encoding="utf-8")

    update_antizapret_settings(setup, {"WARP_MTU": "1400"})
    assert read_antizapret_settings(setup)["WARP_MTU"] == "1400"


def test_update_rejects_invalid_value(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("WARP_MTU=1280\n", encoding="utf-8")

    with pytest.raises(ValueError):
        update_antizapret_settings(setup, {"WARP_MTU": "9000"})
    assert setup.read_text(encoding="utf-8") == "WARP_MTU=1280\n"


@pytest.mark.parametrize("requested", ["", "1280"])
def test_old_agent_without_key_and_default_value_is_not_warned(requested):
    assert setting_write_mismatch_warnings({"WARP_MTU": requested}, {"ANTIZAPRET_WARP": "3"}) == []


def test_old_agent_without_key_and_custom_value_is_warned():
    (warning,) = setting_write_mismatch_warnings({"WARP_MTU": "1380"}, {"ANTIZAPRET_WARP": "3"})

    assert "WARP_MTU" in warning
    assert "1380" in warning
    assert "node agent" in warning


def test_new_agent_with_key_is_not_warned():
    assert setting_write_mismatch_warnings({"WARP_MTU": "1380"}, {"WARP_MTU": "1380"}) == []
