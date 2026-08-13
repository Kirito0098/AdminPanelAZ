"""AZ-AWG2 wave 1a/1b: feature toggle registration, path guards, require_vpn_type."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.feature_guards import check_path_access, require_vpn_type
from app.services.feature_toggles import FEATURE_TOGGLE_BY_KEY, FeatureToggleService


def _svc(env_file: Path, **flags: bool) -> FeatureToggleService:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return FeatureToggleService(env_file)


def test_awg2_toggle_registered_default_off(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    defn = FEATURE_TOGGLE_BY_KEY["awg2"]
    assert defn.default is False
    assert defn.env_key == "FEATURE_AWG2_ENABLED"
    assert defn.api_prefixes == ("/api/awg2", "/api/client-access/amneziawg2")
    assert "/awg2" in defn.frontend_paths
    assert defn.label == "AZ-AWG2"
    service = FeatureToggleService(env_file)
    assert service.is_enabled("awg2") is False


def test_awg2_path_blocked_when_disabled(tmp_path: Path):
    env_file = tmp_path / ".env"
    service = _svc(env_file, FEATURE_AWG2_ENABLED=False)
    blocked = check_path_access("/api/awg2/health", service=service)
    assert blocked is not None and blocked[0] == "awg2"
    blocked = check_path_access("/api/client-access/amneziawg2/status", service=service)
    assert blocked is not None and blocked[0] == "awg2"


def test_awg2_path_allowed_when_enabled(tmp_path: Path):
    env_file = tmp_path / ".env"
    service = _svc(env_file, FEATURE_AWG2_ENABLED=True)
    assert check_path_access("/api/awg2/health", service=service) is None
    assert check_path_access("/api/awg2/status", service=service) is None
    assert check_path_access("/api/client-access/amneziawg2/status", service=service) is None


def test_require_vpn_type_amneziawg2(tmp_path: Path):
    env_file = tmp_path / ".env"
    service = _svc(env_file, FEATURE_AWG2_ENABLED=False)
    with pytest.raises(HTTPException) as exc:
        require_vpn_type("amneziawg2", service=service)
    assert exc.value.status_code == 403

    service = _svc(env_file, FEATURE_AWG2_ENABLED=True)
    require_vpn_type("amneziawg2", service=service)  # no raise
