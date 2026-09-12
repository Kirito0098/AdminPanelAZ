from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.routers import system as system_router
from app.services.feature_guards import check_path_access, module_disabled_message
from app.services.feature_toggles import FeatureToggleService


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


def _svc(env_file: Path, **flags: bool) -> FeatureToggleService:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return FeatureToggleService(env_file)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(system_router.router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="admin")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c


def test_rebuild_path_guard_blocks_panel_ops(env_file: Path):
    service = _svc(env_file, FEATURE_PANEL_OPS_ENABLED=False)

    blocked = check_path_access("/api/system/rebuild", service=service)
    assert blocked is not None
    assert blocked[0] == "panel_ops"
    assert blocked[1] == module_disabled_message("panel_ops")
    assert check_path_access("/api/system/restart", service=service) is None


def test_rebuild_endpoint_returns_403_when_panel_ops_disabled(client, env_file: Path, monkeypatch):
    service = _svc(env_file, FEATURE_PANEL_OPS_ENABLED=False)
    monkeypatch.setattr(system_router, "get_feature_service", lambda: service)

    with patch.object(system_router.background_task_service, "find_active_task") as find_active, patch.object(
        system_router.background_task_service, "enqueue_background_task"
    ) as enqueue, patch.object(system_router, "log_action") as log_action:
        resp = client.post("/api/system/rebuild")

    assert resp.status_code == 403
    assert resp.json()["detail"] == module_disabled_message("panel_ops")
    find_active.assert_not_called()
    enqueue.assert_not_called()
    log_action.assert_not_called()


def test_restart_endpoint_still_schedules_when_panel_ops_disabled(client, env_file: Path, monkeypatch):
    service = _svc(env_file, FEATURE_PANEL_OPS_ENABLED=False)
    monkeypatch.setattr(system_router, "get_feature_service", lambda: service)

    with patch.object(system_router, "schedule_controller_restart") as schedule_restart, patch.object(
        system_router, "log_action"
    ) as log_action:
        resp = client.post("/api/system/restart")

    assert resp.status_code == 200
    assert resp.json()["message"] == "Перезапуск панели запланирован через несколько секунд"
    schedule_restart.assert_called_once()
    log_action.assert_called_once()
