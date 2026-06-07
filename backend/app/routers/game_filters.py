import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User
from app.schemas import MessageResponse
from app.services.cidr.game_filters import get_game_filters_state, sync_game_filters
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/routing/game-filters", tags=["game-filters"])
settings = get_settings()


class GameFiltersUpdate(BaseModel):
    modes: dict[str, str] = {}
    include_domains: bool = True
    run_doall: bool = True


def _get_modes(db: Session) -> dict[str, str]:
    row = db.query(AppSetting).filter(AppSetting.key == "game_filter_modes").first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return {}


def _set_modes(db: Session, modes: dict[str, str]) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == "game_filter_modes").first()
    val = json.dumps(modes)
    if row:
        row.value = val
    else:
        db.add(AppSetting(key="game_filter_modes", value=val))


@router.get("")
def get_filters(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    modes = _get_modes(db)
    return get_game_filters_state(list(modes.keys()), modes)


@router.post("/sync", response_model=MessageResponse)
def sync_filters(payload: GameFiltersUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    _set_modes(db, payload.modes)
    db.commit()
    include_keys = [k for k, m in payload.modes.items() if m == "include"]
    exclude_keys = [k for k, m in payload.modes.items() if m == "exclude"]
    adapter = get_active_adapter(db)
    config_dir = settings.antizapret_path / "config"
    result = sync_game_filters(
        config_dir,
        include_keys=include_keys,
        exclude_keys=exclude_keys,
        include_domains=payload.include_domains,
    )
    output = None
    if payload.run_doall and (result["hosts_changed"] or result["ips_changed"]):
        output = adapter.apply_config_changes()
    return MessageResponse(message="Игровые фильтры синхронизированы", detail={**result, "doall": output})
