"""Tests for systemd unit refresh / stale-migration helpers."""

from pathlib import Path

from app.services.systemd_refresh import (
    _unit_text_is_stale,
    refresh_installed_systemd_units,
    unit_file_needs_migration,
)


def test_unit_text_stale_legacy_start_sh():
    text = "ExecStart=/opt/AdminPanelAZ/start.sh watchdog prod\n"
    assert _unit_text_is_stale(text) is True


def test_unit_text_not_stale_when_systemd_exec():
    text = "ExecStart=/opt/AdminPanelAZ/scripts/systemd-exec-panel.sh\n"
    assert _unit_text_is_stale(text) is False


def test_unit_text_not_stale_when_both_present_prefers_new():
    # Should not happen, but new marker wins
    text = (
        "ExecStart=/opt/AdminPanelAZ/scripts/systemd-exec-panel.sh\n"
        "# was start.sh\n"
    )
    assert _unit_text_is_stale(text) is False


def test_unit_file_needs_migration(tmp_path: Path):
    unit = tmp_path / "adminpanelaz.service"
    unit.write_text("ExecStart=/opt/x/start.sh watchdog prod\n", encoding="utf-8")
    assert unit_file_needs_migration(unit) is True
    unit.write_text("ExecStart=/opt/x/scripts/systemd-exec-panel.sh\n", encoding="utf-8")
    assert unit_file_needs_migration(unit) is False


def test_refresh_skipped_when_no_units(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.services.systemd_refresh.PANEL_UNIT_DST",
        tmp_path / "missing-panel.service",
    )
    monkeypatch.setattr(
        "app.services.systemd_refresh.NODE_UNIT_DST",
        tmp_path / "missing-node.service",
    )
    script = tmp_path / "scripts" / "refresh-systemd-units.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    result = refresh_installed_systemd_units(tmp_path, panel=True, node=True)
    assert result["success"] is True
    assert result["skipped"] is True


def test_refresh_missing_script(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.services.systemd_refresh.PANEL_UNIT_DST",
        tmp_path / "adminpanelaz.service",
    )
    (tmp_path / "adminpanelaz.service").write_text("ExecStart=x\n", encoding="utf-8")
    result = refresh_installed_systemd_units(tmp_path, panel=True, node=False)
    assert result["success"] is False
    assert "Не найден" in (result["error"] or "")
