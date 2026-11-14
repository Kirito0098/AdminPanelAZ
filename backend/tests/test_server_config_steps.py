"""Server-config step selection: DDNS availability, validation and FU_ONLY passed to full-update.sh."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import server_config


def _step_by_key(steps: list[dict]) -> dict[str, dict]:
    return {item["key"]: item for item in steps}


def test_ddns_hidden_without_config(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))

    steps = _step_by_key(server_config.available_steps())

    assert list(steps) == ["apt", "systemd", "nginx", "firewall", "ddns"]
    assert steps["ddns"]["available"] is False
    assert steps["ddns"]["reason"] == "DDNS не настроен"
    assert all(steps[key]["available"] for key in ("apt", "systemd", "nginx", "firewall"))


def test_ddns_available_with_config(monkeypatch, tmp_path):
    config = tmp_path / "ddns.env"
    config.write_text("DDNS_PROVIDER=duckdns\n", encoding="utf-8")
    monkeypatch.setenv("DDNS_CONFIG", str(config))

    steps = _step_by_key(server_config.available_steps())

    assert steps["ddns"]["available"] is True
    assert "reason" not in steps["ddns"]


def test_validate_steps_keeps_order_and_drops_duplicates(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))

    assert server_config.validate_steps(["nginx", "apt", "nginx"]) == ["nginx", "apt"]


def test_validate_steps_rejects_unknown(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))

    with pytest.raises(ValueError, match="bogus"):
        server_config.validate_steps(["apt", "bogus"])


def test_validate_steps_rejects_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))

    with pytest.raises(ValueError):
        server_config.validate_steps([])


def test_apply_passes_fu_only_to_script(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))
    calls: dict = {}

    def fake_run(*args, timeout, env=None, ok_codes=(0,)):
        calls["args"] = args
        calls["env"] = dict(env or {})
        report = Path(args[args.index("--report") + 1])
        report.write_text("nginx\tok\t\n", encoding="utf-8")
        return ""

    monkeypatch.setattr(server_config, "_run_script", fake_run)

    result = server_config.apply(["nginx"])

    assert result["success"] is True
    assert "--server-only" in calls["args"]
    assert calls["env"]["FU_ONLY"] == "nginx"


def test_apply_without_selection_omits_fu_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))
    calls: dict = {}

    def fake_run(*args, timeout, env=None, ok_codes=(0,)):
        calls["env"] = dict(env or {})
        Path(args[args.index("--report") + 1]).write_text("apt\tok\t\n", encoding="utf-8")
        return ""

    monkeypatch.setattr(server_config, "_run_script", fake_run)

    server_config.apply(None)

    assert "FU_ONLY" not in calls["env"]


def test_apply_rejects_unknown_and_unavailable_steps(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))

    def fail_run(*args, **kwargs):
        raise AssertionError("script must not run for an invalid selection")

    monkeypatch.setattr(server_config, "_run_script", fail_run)

    with pytest.raises(ValueError, match="bogus"):
        server_config.apply(["bogus"])
    with pytest.raises(ValueError, match="ddns"):
        server_config.apply(["ddns"])


def test_preview_includes_steps_and_nginx_impact(monkeypatch, tmp_path):
    monkeypatch.setenv("DDNS_CONFIG", str(tmp_path / "ddns.env"))
    monkeypatch.setenv("NGINX_SITES_ENABLED_DIR", str(tmp_path / "no-nginx" / "enabled"))
    monkeypatch.setenv("NGINX_SITES_AVAILABLE_DIR", str(tmp_path / "no-nginx" / "available"))
    monkeypatch.setenv("NGINX_CONF_D_DIR", str(tmp_path / "no-nginx" / "conf.d"))
    monkeypatch.setattr(server_config, "_run_script", lambda *args, **kwargs: "add\tПакет\n")
    monkeypatch.setattr(server_config, "_panel_domain", lambda: "panel.arbitrary.test")

    result = server_config.preview()

    assert result["pending"] == 1
    assert _step_by_key(result["steps"])["ddns"]["available"] is False
    assert result["nginx_impact"]["nginx_seen"] is False
    assert result["nginx_impact"]["panel_domain"] == "panel.arbitrary.test"
