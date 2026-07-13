import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import LatestChangelogResponse, MessageResponse
from app.services.action_log import log_action
from app.services.background_tasks import background_task_service
from app.services.changelog_remote import build_changelog_response, fetch_remote_changelog_content
from app.services.system_update import schedule_controller_restart

router = APIRouter(prefix="/system", tags=["system"])
APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT.parent
_CHANGELOG_CACHE: dict = {"content": None, "source": None, "expires": 0.0}


def _repo_root() -> Path:
    from app.services.node_update import resolve_repo_root

    return resolve_repo_root(PROJECT_ROOT) or PROJECT_ROOT


def _git_update_status(repo_root: Path) -> dict:
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


@router.get("/updates")
def check_updates(_: User = Depends(require_admin)):
    return _git_update_status(_repo_root())


@router.get("/latest-changelog", response_model=LatestChangelogResponse)
def latest_changelog(_: User = Depends(require_admin)):
    now = time.monotonic()
    repo_root = _repo_root()
    status_payload = _git_update_status(repo_root)
    updates_available = bool(status_payload.get("updates_available"))

    content = _CHANGELOG_CACHE["content"]
    source = _CHANGELOG_CACHE["source"]
    if content is None or now >= _CHANGELOG_CACHE["expires"]:
        try:
            content, source = fetch_remote_changelog_content(repo_root)
            _CHANGELOG_CACHE["content"] = content
            _CHANGELOG_CACHE["source"] = source
            _CHANGELOG_CACHE["expires"] = now + 600
        except Exception as exc:
            return LatestChangelogResponse(success=False, message=f"Не удалось загрузить CHANGELOG: {exc}")

    payload = build_changelog_response(content, updates_available=updates_available, source=source or "")
    return LatestChangelogResponse(**payload)


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
    active_rebuild = background_task_service.find_active_task("rebuild_frontend")
    if active_rebuild:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Пересборка frontend уже выполняется",
                "active_task_id": active_rebuild.id,
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


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
def rebuild_panel(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    for task_type in ("update_system", "rebuild_frontend"):
        active = background_task_service.find_active_task(task_type)
        if active:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "Пересборка или обновление уже выполняется",
                    "active_task_id": active.id,
                },
            )

    def _callable(progress_updater=None):
        return background_task_service.task_rebuild_frontend(progress_updater)

    task = background_task_service.enqueue_background_task(
        "rebuild_frontend",
        _callable,
        created_by_username=user.username,
        queued_message="Пересборка frontend поставлена в очередь",
    )

    log_action(
        db,
        action="system_rebuild_queued",
        user_id=user.id,
        username=user.username,
        details=f"task_id={task.id}",
    )

    return background_task_service.build_accepted_payload(task, "Пересборка frontend запущена в фоне.")


@router.post("/restart", response_model=MessageResponse)
def restart_panel(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    schedule_controller_restart(_repo_root())
    log_action(
        db,
        action="system_restart",
        user_id=user.id,
        username=user.username,
        details="scheduled",
    )
    return MessageResponse(message="Перезапуск панели запланирован через несколько секунд")
