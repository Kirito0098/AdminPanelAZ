from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.feature_guards import get_feature_service
from app.services.feature_toggles import (
    FRONTEND_PATH_TO_MODULE,
    SETTINGS_TAB_TO_MODULE,
    FeatureToggleService,
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
    try:
        result = _service().update_toggles(payload.toggles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@feature_modules_router.get("")
def get_feature_modules():
    service = _service()
    return {
        "features": service.get_feature_states(),
        "frontend_paths": FRONTEND_PATH_TO_MODULE,
        "settings_tabs": SETTINGS_TAB_TO_MODULE,
    }
