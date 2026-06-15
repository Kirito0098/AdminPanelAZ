import re
import subprocess
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import LatestChangelogResponse, MessageResponse
from app.services.action_log import log_action
from app.services.background_tasks import background_task_service

router = APIRouter(prefix="/system", tags=["system"])
APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT.parent
_CHANGELOG_CACHE: dict = {"data": None, "expires": 0.0}


def _repo_root() -> Path:
    from app.services.node_update import resolve_repo_root

    return resolve_repo_root(PROJECT_ROOT) or PROJECT_ROOT


class ViewerAccessUpdate(BaseModel):
    user_id: int
    config_groups: list[str] = []


@router.get("/updates")
def check_updates(_: User = Depends(require_admin)):
    repo_root = _repo_root()
    try:
        subprocess.run(["git", "fetch", "origin"], cwd=repo_root, capture_output=True, timeout=30, check=False)
        local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=False)
        remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=repo_root, capture_output=True, text=True, check=False)
        local_hash = local.stdout.strip()
        remote_hash = remote.stdout.strip()
        behind = 0
        if local_hash and remote_hash and local_hash != remote_hash:
            count = subprocess.run(
                ["git", "rev-list", "--count", f"{local_hash}..{remote_hash}"],
                cwd=repo_root, capture_output=True, text=True, check=False,
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


@router.get("/latest-changelog", response_model=LatestChangelogResponse)
def latest_changelog(_: User = Depends(require_admin)):
    now = time.monotonic()
    if _CHANGELOG_CACHE["data"] is not None and now < _CHANGELOG_CACHE["expires"]:
        return _CHANGELOG_CACHE["data"]

    changelog_path = PROJECT_ROOT / "CHANGELOG.md"
    content = ""
    if changelog_path.is_file():
        content = changelog_path.read_text(encoding="utf-8")
    else:
        url = "https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/main/CHANGELOG.md"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AdminPanelAZ/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
        except Exception as exc:
            return LatestChangelogResponse(success=False, message=f"Не удалось загрузить CHANGELOG: {exc}")

    version_pattern = re.compile(r"^## \[(.+?)\]\s*[–\-]\s*(.+)$", re.MULTILINE)
    matches = list(version_pattern.finditer(content))
    if not matches:
        return LatestChangelogResponse(success=False, message="CHANGELOG не содержит версий")

    first = matches[0]
    end = matches[1].start() if len(matches) > 1 else len(content)
    block = content[first.start():end].strip()
    version = first.group(1).strip()
    date = first.group(2).strip()

    sections = []
    section_pattern = re.compile(r"^#{3,4}\s+(.+)$", re.MULTILINE)
    sec_matches = list(section_pattern.finditer(block))
    for i, sm in enumerate(sec_matches):
        sec_end = sec_matches[i + 1].start() if i + 1 < len(sec_matches) else len(block)
        sec_text = block[sm.end():sec_end].strip()
        items = [
            line.lstrip("-* \t").strip()
            for line in sec_text.splitlines()
            if line.strip().startswith(("-", "*"))
        ]
        if items:
            sections.append({"title": sm.group(1).strip(), "items": items})

    result = LatestChangelogResponse(success=True, version=version, date=date, sections=sections)
    _CHANGELOG_CACHE["data"] = result
    _CHANGELOG_CACHE["expires"] = now + 600
    return result


@router.post("/update", status_code=status.HTTP_202_ACCEPTED)
def apply_update(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    active = background_task_service.find_active_task("update_system")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Обновление системы уже выполняется",
                "active_task_id": active.id,
            },
        )

    def _callable(progress_updater=None):
        return background_task_service.task_update_system(progress_updater)

    task = background_task_service.enqueue_background_task(
        "update_system",
        _callable,
        created_by_username=user.username,
        queued_message="Обновление системы поставлено в очередь",
    )

    log_action(
        db,
        action="system_update_queued",
        user_id=user.id,
        username=user.username,
        details=f"task_id={task.id}",
    )

    return background_task_service.build_accepted_payload(task, "Обновление системы запущено в фоне.")


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
