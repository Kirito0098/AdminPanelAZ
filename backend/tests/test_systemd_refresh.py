"""Tests for systemd unit refresh / stale-migration helpers."""

from pathlib import Path

from app.services.systemd_refresh import (
    _unit_text_is_stale,
    migrate_stale_systemd_units_on_startup,
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


def _units(tmp_path: Path, monkeypatch, *, panel=False, node=False, proxy=False):
    for name, attr, present in (
        ("adminpanelaz.service", "PANEL_UNIT_DST", panel),
        ("adminpanelaz-node.service", "NODE_UNIT_DST", node),
        ("adminpanelaz-proxy.service", "PROXY_UNIT_DST", proxy),
    ):
        unit = tmp_path / "units" / name
        unit.parent.mkdir(exist_ok=True)
        if present:
            unit.write_text(present if isinstance(present, str) else "ExecStart=x\n", encoding="utf-8")
        monkeypatch.setattr(f"app.services.systemd_refresh.{attr}", unit)
    script = tmp_path / "scripts" / "refresh-systemd-units.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        '#!/bin/bash\necho "panel=$REFRESH_PANEL node=$REFRESH_NODE proxy=$REFRESH_PROXY" > "$(dirname "$0")/called"\n',
        encoding="utf-8",
    )
    return script.parent / "called"


def test_unit_with_agent_api_key_needs_migration():
    for key in ("NODE_AGENT_API_KEY", "PROXY_AGENT_API_KEY"):
        text = f"ExecStart=/opt/x/scripts/systemd-exec-node.sh\nEnvironment={key}=secret\n"
        assert _unit_text_is_stale(text) is True


def test_refresh_proxy_only_host(tmp_path: Path, monkeypatch):
    called = _units(tmp_path, monkeypatch, proxy=True)
    result = refresh_installed_systemd_units(tmp_path, panel=True, node=True)
    assert result["success"] is True and result["skipped"] is False
    assert called.read_text().strip() == "panel=0 node=0 proxy=1"


def test_refresh_without_proxy_does_not_touch_proxy_unit(tmp_path: Path, monkeypatch):
    called = _units(tmp_path, monkeypatch, node=True, proxy=True)
    refresh_installed_systemd_units(tmp_path, panel=False, node=True, proxy=False)
    assert called.read_text().strip() == "panel=0 node=1 proxy=0"


def test_refresh_skips_missing_proxy_unit(tmp_path: Path, monkeypatch):
    called = _units(tmp_path, monkeypatch, panel=True)
    refresh_installed_systemd_units(tmp_path, panel=True, node=True)
    assert called.read_text().strip() == "panel=1 node=0 proxy=0"


def test_startup_migrates_proxy_unit_holding_api_key(tmp_path: Path, monkeypatch):
    called = _units(
        tmp_path,
        monkeypatch,
        node="ExecStart=/opt/x/scripts/systemd-exec-node.sh\n",
        proxy="ExecStart=/opt/x/proxy\nEnvironment=PROXY_AGENT_API_KEY=secret\n",
    )
    result = migrate_stale_systemd_units_on_startup(tmp_path, panel=False, node=True, proxy=True)
    assert result["success"] is True and result["skipped"] is False
    assert called.read_text().strip() == "panel=0 node=0 proxy=1"


def test_agents_migrate_units_on_startup(monkeypatch):
    import asyncio
    import importlib

    calls: list[dict] = []
    monkeypatch.setattr(
        "app.services.systemd_refresh.migrate_stale_systemd_units_on_startup",
        lambda repo_root, **kwargs: calls.append(kwargs),
    )
    monkeypatch.setenv("NODE_AGENT_API_KEY", "a" * 40)
    monkeypatch.setenv("PROXY_AGENT_API_KEY", "b" * 40)
    for module in ("node_agent.main", "proxy_agent.main"):
        agent = importlib.import_module(module)

        async def run(app=agent.app):
            async with app.router.lifespan_context(app):
                pass

        asyncio.run(run())
    assert calls == [
        {"panel": False, "node": True, "proxy": True},
        {"panel": False, "node": False, "proxy": True},
    ]
