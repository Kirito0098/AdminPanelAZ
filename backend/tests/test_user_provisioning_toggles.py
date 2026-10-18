"""Stage 1 Task 6: §8.1 toggles `clients_page` / `user_provisioning` + path gating.

Toggles: `clients_page` (default on, no api_prefixes), `user_provisioning` (default off,
no broad /api/users prefix — explicit path checks only).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.feature_guards import blocked_json_response, check_path_access
from app.services.feature_toggles import (
    FEATURE_TOGGLE_BY_KEY,
    FeatureToggleService,
)

CLIENTS_PAGE = "clients_page"
USER_PROVISIONING = "user_provisioning"
USER_MANAGEMENT = "user_management"


def _svc(tmp_path: Path, **flags: bool) -> FeatureToggleService:
    env_file = tmp_path / ".env"
    defaults = {
        USER_MANAGEMENT: True,
        CLIENTS_PAGE: True,
        USER_PROVISIONING: False,
    }
    defaults.update(flags)
    env_file.write_text(
        "\n".join(
            f"FEATURE_{key.upper().replace(' ', '_')}_ENABLED={'true' if enabled else 'false'}"
            for key, enabled in defaults.items()
        ),
        encoding="utf-8",
    )
    return FeatureToggleService(env_file)


def test_toggle_definitions_registered():
    assert FEATURE_TOGGLE_BY_KEY[CLIENTS_PAGE].default is True
    assert FEATURE_TOGGLE_BY_KEY[CLIENTS_PAGE].api_prefixes == ()
    assert FEATURE_TOGGLE_BY_KEY[USER_PROVISIONING].default is False
    assert FEATURE_TOGGLE_BY_KEY[USER_PROVISIONING].api_prefixes == ()
    assert FEATURE_TOGGLE_BY_KEY[USER_PROVISIONING].env_key == "FEATURE_USER_PROVISIONING_ENABLED"


def test_cannot_disable_both_clients_and_provisioning(tmp_path):
    service = _svc(tmp_path)
    with pytest.raises(ValueError, match="одновремен"):
        service.update_toggles({CLIENTS_PAGE: False, USER_PROVISIONING: False})


def test_disabling_user_management_disables_provisioning(tmp_path):
    service = _svc(tmp_path, **{USER_PROVISIONING: True})
    assert service.is_enabled(USER_PROVISIONING) is True
    service.update_toggles({USER_MANAGEMENT: False})
    assert service.is_enabled(USER_MANAGEMENT) is False
    assert service.is_enabled(USER_PROVISIONING) is False


def test_enabling_provisioning_requires_user_management(tmp_path):
    service = _svc(tmp_path, **{USER_MANAGEMENT: False})
    assert service.is_enabled(USER_MANAGEMENT) is False
    with pytest.raises(ValueError, match="user_management|Пользователи и доступ"):
        service.update_toggles({USER_PROVISIONING: True})
    assert service.is_enabled(USER_PROVISIONING) is False


def test_both_off_rejected_even_via_management_cascade(tmp_path):
    service = _svc(tmp_path, **{CLIENTS_PAGE: False})
    assert service.is_enabled(CLIENTS_PAGE) is False
    with pytest.raises(ValueError, match="одновремен"):
        service.update_toggles({USER_MANAGEMENT: False})


def _guard_app(service: FeatureToggleService) -> TestClient:
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    def _stub(path: str):
        return {"ok": True}

    @app.middleware("http")
    async def _guard(request, call_next):
        blocked = check_path_access(request.url.path, service=service)
        if blocked is not None:
            return blocked_json_response(blocked[0])
        return await call_next(request)

    return TestClient(app)


def test_provisioning_paths_blocked_when_toggle_off(tmp_path):
    service = _svc(tmp_path)  # user_provisioning off by default
    client = _guard_app(service)

    for path, method in (
        ("/api/users/provisioned", "POST"),
        ("/api/users/1/provisioning", "GET"),
        ("/api/users/1/provisioning/apply", "POST"),
        ("/api/users/7/configs/3", "DELETE"),
    ):
        kwargs = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
        response = getattr(client, method.lower())(path, **kwargs)
        assert response.status_code == 403, path
        body = response.json()
        assert body["feature_disabled"] == USER_PROVISIONING, (path, body)
        assert "Пользователи (абоненты)" in body["detail"], (path, body)


def test_provisioning_paths_allowed_when_toggle_on(tmp_path):
    service = _svc(tmp_path, **{USER_PROVISIONING: True})
    client = _guard_app(service)

    for path in ("/api/users/provisioned", "/api/users/1/provisioning", "/api/users/1/configs/3"):
        response = client.post(path, json={})
        assert response.status_code == 200, (path, response.text)


def test_regular_user_paths_not_gated_by_provisioning(tmp_path):
    # telegram is enabled here so /api/tg-mini/* is not blocked by the telegram module;
    # the point is user_provisioning must not block these paths.
    service = _svc(tmp_path, telegram=True)
    client = _guard_app(service)

    for path, method in (
        ("/api/users", "GET"),
        ("/api/users/1", "PATCH"),
        ("/api/users/5", "GET"),
        ("/api/tg-mini/me/configs", "GET"),
        ("/api/tg-mini/me/configs/9/files", "GET"),
    ):
        fn = getattr(client, method.lower())
        kwargs = {} if method == "GET" else {"json": {"is_active": True}}
        response = fn(path, **kwargs)
        assert response.status_code == 200, (path, response.text)
        assert response.json() == {"ok": True}


def test_check_path_access_matcher_in_isolation(tmp_path):
    # telegram enabled so /api/tg-mini/* is not blocked by the unrelated telegram module.
    service = _svc(tmp_path, telegram=True)
    message = f"Раздел «{FEATURE_TOGGLE_BY_KEY[USER_PROVISIONING].label}» отключён администратором."
    assert check_path_access("/api/users/provisioned", service=service) == (USER_PROVISIONING, message)
    assert check_path_access("/api/users/1/provisioning/apply", service=service) == (USER_PROVISIONING, message)
    assert check_path_access("/api/users/7/configs/3", service=service) == (USER_PROVISIONING, message)
    # Not gated by user_provisioning: user_management keeps owning them.
    assert check_path_access("/api/users", service=service) is None
    assert check_path_access("/api/users/1", service=service) is None
    assert check_path_access("/api/tg-mini/me/configs", service=service) is None
