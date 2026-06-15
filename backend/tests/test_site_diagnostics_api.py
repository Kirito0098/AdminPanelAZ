"""API tests for site diagnostics runbook."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.site_diagnostics import (
    CheckResult,
    DiagnosticsContext,
    DiagnosticsReport,
    report_to_dict,
)


def test_report_to_dict_groups_steps():
    ctx = DiagnosticsContext(install_dir="/opt/panel", service_name="adminpanelaz")
    report = DiagnosticsReport()
    report.results = [
        CheckResult("ok", "Unit ok", category="systemd"),
        CheckResult("fail", "No db", detail="missing", category="files"),
        CheckResult("warn", "nginx off", category="nginx"),
        CheckResult("ok", "Done", detail="ok=1, warn=1, fail=1", category="summary"),
    ]
    report.recommended_commands = ["systemctl restart adminpanelaz"]

    payload = report_to_dict(report, ctx)

    assert payload["success"] is False
    assert payload["install_dir"] == "/opt/panel"
    assert payload["service_name"] == "adminpanelaz"
    assert len(payload["steps"]) == 8
    systemd = next(s for s in payload["steps"] if s["id"] == "systemd")
    assert systemd["status"] == "ok"
    assert len(systemd["checks"]) == 1
    files = next(s for s in payload["steps"] if s["id"] == "files")
    assert files["status"] == "fail"
    assert payload["recommended_commands"] == ["systemctl restart adminpanelaz"]


@patch("app.routers.site_diagnostics.run_site_diagnostics")
@patch("app.routers.site_diagnostics.resolve_diagnostics_context")
def test_run_returns_json(mock_ctx, mock_run, api_test_env):
    ctx = DiagnosticsContext(install_dir="/opt/panel", service_name="adminpanelaz")
    report = DiagnosticsReport()
    report.results = [CheckResult("ok", "All good", category="summary")]
    mock_ctx.return_value = ctx
    mock_run.return_value = report

    client = TestClient(api_test_env["app"])
    resp = client.post("/api/site-diagnostics/run", headers=api_test_env["admin_headers"])

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["service_name"] == "adminpanelaz"
    assert "steps" in data
    assert "results" in data


def test_run_rejects_unauthenticated(api_test_env):
    client = TestClient(api_test_env["app"])
    resp = client.post("/api/site-diagnostics/run")
    assert resp.status_code in (401, 403)
