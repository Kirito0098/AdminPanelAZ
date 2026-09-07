"""FeatureToggleService env-map cache + get_feature_service singleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import feature_guards
from app.services.feature_toggles import FeatureToggleService


@pytest.fixture(autouse=True)
def _reset_singleton():
    feature_guards.reset_feature_service_cache()
    yield
    feature_guards.reset_feature_service_cache()


def test_env_map_caches_until_mtime_or_write(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=false\n", encoding="utf-8")
    svc = FeatureToggleService(env_file)

    reads: list[str] = []
    real_read = Path.read_text

    def counting_read(self, *args, **kwargs):
        if self == env_file:
            reads.append("read")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read)

    assert svc.is_enabled("telegram") is False
    assert svc.is_enabled("telegram") is False
    assert svc.get_feature_states()["telegram"] is False
    assert len(reads) == 1

    svc.update_toggles({"telegram": True})
    assert svc.is_enabled("telegram") is True
    assert len(reads) >= 2


def test_external_env_write_picked_up_via_mtime(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_AWG2_ENABLED=false\n", encoding="utf-8")
    svc = FeatureToggleService(env_file)
    assert svc.is_enabled("awg2") is False

    env_file.write_text("FEATURE_AWG2_ENABLED=true\n", encoding="utf-8")
    assert svc.is_enabled("awg2") is True


def test_get_feature_service_reuses_instance(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setattr(feature_guards, "_panel_env_path", lambda: env_file)

    first = feature_guards.get_feature_service()
    second = feature_guards.get_feature_service()
    assert first is second
    assert first.is_enabled("telegram") is True
