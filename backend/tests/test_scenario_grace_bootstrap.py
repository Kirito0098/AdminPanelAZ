"""Install/update bootstrap: scenario grace AppSetting must exist before the first UI load."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting
from app.services.feature_toggles import FeatureToggleService
from app.services.user_grace import get_grace_months, set_grace_months


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _service(tmp_path: Path) -> FeatureToggleService:
    return FeatureToggleService(tmp_path / ".env")


def test_commercial_install_resolves_after_grace_sync(tmp_path, db):
    service = _service(tmp_path)
    # install.sh applies the preset to .env only: без AppSetting сценарий выглядит «Кастомным».
    service.apply_scenario_preset("commercial")
    assert service.resolve_scenario_state(db)["is_custom"] is True

    assert service.ensure_scenario_grace_setting(db) is True

    state = service.resolve_scenario_state(db)
    assert state["key"] == "commercial"
    assert state["is_custom"] is False
    assert get_grace_months(db) == 3


def test_existing_grace_setting_is_not_overwritten(tmp_path, db):
    service = _service(tmp_path)
    service.apply_scenario_preset("commercial")
    set_grace_months(db, 0)
    db.commit()

    assert service.ensure_scenario_grace_setting(db) is False
    assert get_grace_months(db) == 0


def test_no_scenario_env_leaves_settings_untouched(tmp_path, db):
    env = tmp_path / ".env"
    env.write_text("FEATURE_TRAFFIC_SYNC_ENABLED=true\n", encoding="utf-8")
    service = FeatureToggleService(env)

    assert service.ensure_scenario_grace_setting(db) is False
    assert db.query(AppSetting).count() == 0
