#!/usr/bin/env python3
"""Create the scenario grace AppSetting after install/update (idempotent).

install.sh / full-update.sh apply the scenario to .env only; this writes the missing
AppSetting so the panel shows the chosen preset right after the first start.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
ENV_FILE = BACKEND_DIR / ".env"
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))
(BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)

from app.services.feature_toggles import FeatureToggleService


def main() -> int:
    if not ENV_FILE.is_file():
        return 0
    service = FeatureToggleService(ENV_FILE)
    if not service.env.env_key_defined_in_file("SCENARIO_PRESET"):
        return 0

    import app.models  # noqa: F401 — регистрирует таблицы (app_settings) в Base.metadata
    from app.database import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if service.ensure_scenario_grace_setting(db):
            print(f"[sync-scenario-db] grace setting written for scenario {service.get_scenario_preset()}")
        else:
            print("[sync-scenario-db] grace setting already set — unchanged")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
