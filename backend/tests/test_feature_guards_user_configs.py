"""Admin config routes must not depend on the subscriber provisioning module."""

import pytest

from app.services.feature_guards import _modules_for_path, check_path_access
from app.services.feature_toggles import FeatureToggleService

CONFIG_ROUTES = (
    "/api/users/1/configs/4/download",
    "/api/users/1/configs/4/files",
    "/api/users/1/configs/4/access",
    "/api/users/1/configs/4",
)

PROVISIONING_ROUTES = (
    "/api/users/provisioned",
    "/api/users/1/provisioning",
    "/api/users/1/provisioning/configs",
    "/api/users/1/suspend",
    "/api/users/1/resume",
    "/api/users/1/extend",
    "/api/users/1/grace-cleanup",
    "/api/users/1/traffic-counter/reset",
    "/api/users/bulk/nodes",
    "/api/users/bulk/nodes/preview",
)


def _service(tmp_path, *, provisioning: bool, user_management: bool = True) -> FeatureToggleService:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                f"FEATURE_USER_PROVISIONING_ENABLED={str(provisioning).lower()}",
                f"FEATURE_USER_MANAGEMENT_ENABLED={str(user_management).lower()}",
            )
        ),
        encoding="utf-8",
    )
    return FeatureToggleService(env_file)


@pytest.mark.parametrize("path", CONFIG_ROUTES)
def test_admin_config_routes_work_without_user_provisioning(tmp_path, path):
    service = _service(tmp_path, provisioning=False)

    modules = _modules_for_path(path)
    assert not modules or "user_provisioning" not in modules
    assert check_path_access(path, service=service) is None


@pytest.mark.parametrize("path", CONFIG_ROUTES)
def test_admin_config_routes_still_respect_user_management(tmp_path, path):
    service = _service(tmp_path, provisioning=False, user_management=False)

    assert check_path_access(path, service=service)[0] == "user_management"


@pytest.mark.parametrize("path", PROVISIONING_ROUTES)
def test_provisioning_routes_still_require_user_provisioning(tmp_path, path):
    service = _service(tmp_path, provisioning=False)

    assert check_path_access(path, service=service)[0] == "user_provisioning"
