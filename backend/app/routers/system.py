import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import MessageResponse
from app.services.action_log import log_action

router = APIRouter(prefix="/system", tags=["system"])
APP_ROOT = Path(__file__).resolve().parents[2]


class ViewerAccessUpdate(BaseModel):
    user_id: int
    config_groups: list[str] = []


@router.get("/updates")
def check_updates(_: User = Depends(require_admin)):
    try:
        subprocess.run(["git", "fetch", "origin"], cwd=APP_ROOT, capture_output=True, timeout=30, check=False)
        local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=APP_ROOT, capture_output=True, text=True, check=False)
        remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=APP_ROOT, capture_output=True, text=True, check=False)
        local_hash = local.stdout.strip()
        remote_hash = remote.stdout.strip()
        behind = 0
        if local_hash and remote_hash and local_hash != remote_hash:
            count = subprocess.run(
                ["git", "rev-list", "--count", f"{local_hash}..{remote_hash}"],
                cwd=APP_ROOT, capture_output=True, text=True, check=False,
            )
            behind = int(count.stdout.strip() or "0")
        return {
            "local_hash": local_hash[:8] if local_hash else None,
            "remote_hash": remote_hash[:8] if remote_hash else None,
            "updates_available": behind > 0,
            "commits_behind": behind,
        }
    except Exception as exc:
        return {"error": str(exc), "updates_available": False}


@router.post("/update", response_model=MessageResponse)
def apply_update(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=APP_ROOT, capture_output=True, text=True, timeout=120, check=False,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr or result.stdout)
        log_action(db, action="system_update", user_id=user.id, username=user.username, details=result.stdout[:500])
        return MessageResponse(message="Обновление применено", detail=result.stdout.strip())
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Таймаут обновления") from exc


@router.get("/viewer-access/{user_id}")
def get_viewer_access(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.models import ViewerConfigAccess
    rows = db.query(ViewerConfigAccess).filter_by(user_id=user_id).all()
    return {"user_id": user_id, "config_groups": [r.config_group for r in rows]}


@router.put("/viewer-access", response_model=MessageResponse)
def set_viewer_access(payload: ViewerAccessUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.models import ViewerConfigAccess
    db.query(ViewerConfigAccess).filter_by(user_id=payload.user_id).delete()
    for group in payload.config_groups:
        db.add(ViewerConfigAccess(user_id=payload.user_id, config_group=group.strip()))
    db.commit()
    return MessageResponse(message="Доступ viewer обновлён")
