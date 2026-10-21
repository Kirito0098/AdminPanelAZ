from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, tg_mini_token_allowed
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.feature_guards import get_feature_service
from app.services.feature_toggles import (
    FRONTEND_PATH_TO_MODULE,
    SETTINGS_TAB_TO_MODULE,
    FeatureToggleService,
    VALID_SCENARIO_PRESETS,
)

router = APIRouter(prefix="/feature-toggles", tags=["feature-toggles"])
feature_modules_router = APIRouter(prefix="/feature-modules", tags=["feature-modules"])


def _service() -> FeatureToggleService:
    return get_feature_service()


class FeatureToggleUpdate(BaseModel):
    toggles: dict[str, bool]


@router.get("")
def list_feature_toggles(_: User = Depends(require_admin)):
    return _service().list_toggles()


@router.put("")
def update_feature_toggles(payload: FeatureToggleUpdate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = _service()
    turning_off_telegram = (
        "telegram" in payload.toggles
        and payload.toggles["telegram"] is False
        and service.is_enabled("telegram")
    )
    try:
        result = service.update_toggles(payload.toggles, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if turning_off_telegram:
        from app.services.telegram_module import shutdown_telegram_integration

        shutdown_telegram_integration(db)
    db.commit()
    get_settings.cache_clear()
    return result


@router.get("/presets")
def list_scenario_presets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _service().list_scenario_presets(db)


@router.post("/preview-preset")
def preview_scenario_preset(
    preset: str, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    try:
        return _service().preview_scenario_preset(preset, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/apply-preset")
def apply_scenario_preset(preset: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = _service()
    telegram_was_enabled = service.is_enabled("telegram")
    try:
        result = service.apply_scenario_preset(preset, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    if telegram_was_enabled and not service.is_enabled("telegram"):
        from app.services.telegram_module import shutdown_telegram_integration

        shutdown_telegram_integration(db)
        db.commit()
    get_settings.cache_clear()
    return result


@router.post("/clear-locks")
def clear_scenario_locks(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Снять обязательные ограничения сценария, не меняя модули."""
    result = _service().clear_scenario_locks(db)
    db.commit()
    get_settings.cache_clear()
    return result


@router.get("/current-preset")
def get_current_scenario_preset(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = _service()
    resolved = service.resolve_scenario_state(db)
    return {
        "preset": resolved["key"],
        "last_applied": resolved["last_applied"],
        "resolved": resolved,
        "requires_restart": True,
        "valid_presets": sorted(VALID_SCENARIO_PRESETS),
    }


@feature_modules_router.get("")
@tg_mini_token_allowed
def get_feature_modules(_: User = Depends(get_current_user)):
    service = _service()
    return {
        "features": service.get_feature_states(),
        "frontend_paths": FRONTEND_PATH_TO_MODULE,
        "settings_tabs": SETTINGS_TAB_TO_MODULE,
    }
