"""CIDR database pipeline API (download, antifilter, generate)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.cidr.cidr_tasks import (
    create_cidr_task,
    find_active_cidr_task,
    get_cidr_task,
    serialize_cidr_task,
    start_cidr_task,
)
from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.db_pipeline import (
    estimate_cidr_matches_from_db,
    update_cidr_files_from_db,
)
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/routing/cidr-db", tags=["cidr-db"])


class CidrDbRefreshRequest(BaseModel):
    selected_files: list[str] | None = None
    dry_run: bool = False
    retry_failed_mode: str | None = None


class CidrDbGenerateRequest(BaseModel):
    action: str = "generate"
    dry_run: bool = False
    regions: list[str] | None = None
    region_scopes: list[str] | None = None
    include_non_geo_fallback: bool = False
    exclude_ru_cidrs: bool = False
    include_game_hosts: bool = False
    strict_geo_filter: bool = False
    filter_by_antifilter: bool = False
    apply_after: bool = False
    sync_after: bool = True


class CidrDbClearRequest(BaseModel):
    selected_files: list[str] | None = None


def _svc(db: Session) -> CidrDbUpdaterService:
    return CidrDbUpdaterService(db=db)


def _enrich_providers(status: dict) -> dict:
    providers = {}
    for key, info in (status.get("providers") or {}).items():
        meta = IP_FILES.get(key, {})
        providers[key] = {
            **info,
            "name": meta.get("name", key),
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
        }
    status["providers"] = providers
    return status


@router.get("/status")
def cidr_db_status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = _svc(db)
    status_data = _enrich_providers(svc.get_db_status())
    history = svc.get_refresh_history(limit=5)
    return {
        "success": True,
        "last_refresh_started": status_data.get("last_refresh_started"),
        "last_refresh_finished": status_data.get("last_refresh_finished"),
        "last_refresh_status": status_data.get("last_refresh_status"),
        "last_refresh_triggered_by": status_data.get("last_refresh_triggered_by"),
        "total_cidrs": status_data.get("total_cidrs"),
        "providers": status_data.get("providers"),
        "alerts": status_data.get("alerts", []),
        "history": history,
    }


@router.get("/tasks/{task_id}")
def cidr_task_status(task_id: str, _: User = Depends(get_current_user)):
    task = get_cidr_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {"success": True, "task": serialize_cidr_task(task)}


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
def cidr_db_refresh(
    payload: CidrDbRefreshRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    svc = _svc(db)
    selected_files = payload.selected_files
    if payload.retry_failed_mode in {"last", "selected"}:
        failed = svc.get_last_failed_providers()
        if payload.retry_failed_mode == "last":
            selected_files = failed or []
        else:
            selected_set = set(selected_files or [])
            selected_files = [name for name in failed if name in selected_set]
        if not selected_files:
            raise HTTPException(status_code=400, detail="Нет failed-провайдеров для повтора")

    triggered_by = f"manual:{user.username}"
    task_type = "cidr_db_refresh_dry_run" if payload.dry_run else "cidr_db_refresh"
    message = "Dry-run CIDR БД запущен в фоне" if payload.dry_run else "Обновление CIDR БД запущено в фоне"
    task_id = create_cidr_task(task_type, message)

    def _runner(progress_callback):
        from app.database import SessionLocal

        inner_db = SessionLocal()
        try:
            svc_inner = CidrDbUpdaterService(db=inner_db)
            return svc_inner.refresh_all_providers(
                triggered_by=triggered_by,
                selected_files=selected_files,
                progress_callback=progress_callback,
                dry_run=payload.dry_run,
            )
        finally:
            inner_db.close()

    start_cidr_task(task_id, _runner)
    return {
        "success": True,
        "queued": True,
        "task_id": task_id,
        "message": message,
    }


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
def cidr_db_generate(
    payload: CidrDbGenerateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    selected_files = payload.regions
    region_scopes = payload.region_scopes or ["all"]
    action = payload.action.strip().lower()
    dry_run = payload.dry_run

    common_kwargs = dict(
        selected_files=selected_files,
        region_scopes=region_scopes,
        include_non_geo_fallback=payload.include_non_geo_fallback,
        exclude_ru_cidrs=payload.exclude_ru_cidrs,
        include_game_hosts=payload.include_game_hosts,
        strict_geo_filter=payload.strict_geo_filter,
        filter_by_antifilter=payload.filter_by_antifilter,
        total_cidr_limit=None,
    )

    if action in {"estimate", "estimate_dry_run"} or dry_run:
        active = find_active_cidr_task("cidr_estimate_from_db")
        if active:
            return {
                "success": True,
                "queued": True,
                "task_id": active["task_id"],
                "message": "Оценка CIDR из БД уже выполняется",
            }
        task_id = create_cidr_task("cidr_estimate_from_db", "Dry-run генерации из БД запущен")

        def _estimate_runner(progress_callback):
            return estimate_cidr_matches_from_db(progress_callback=progress_callback, **common_kwargs)

        start_cidr_task(task_id, _estimate_runner)
        return {"success": True, "queued": True, "task_id": task_id, "message": "Dry-run генерации из БД запущен"}

    task_id = create_cidr_task("cidr_generate_from_db", "Генерация CIDR-файлов из БД запущена")

    def _generate_runner(progress_callback):
        from app.database import SessionLocal

        result = update_cidr_files_from_db(progress_callback=progress_callback, **common_kwargs)
        if (result.get("success") or result.get("updated")) and payload.sync_after:
            inner_db = SessionLocal()
            try:
                adapter = get_active_adapter(inner_db)
                sync_result = adapter.sync_cidr_providers()
                result["sync"] = sync_result
                if payload.apply_after:
                    result["doall_output"] = adapter.apply_config_changes()
            finally:
                inner_db.close()
        return result

    start_cidr_task(task_id, _generate_runner)
    return {"success": True, "queued": True, "task_id": task_id, "message": "Генерация CIDR-файлов из БД запущена"}


@router.post("/clear")
def cidr_db_clear(
    payload: CidrDbClearRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = _svc(db).clear_provider_data(
        selected_files=payload.selected_files,
        triggered_by=f"manual:{user.username}",
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Ошибка очистки"))
    return result


@router.get("/antifilter/status")
def antifilter_status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"success": True, **_svc(db).get_antifilter_status()}


@router.post("/antifilter/refresh", status_code=status.HTTP_202_ACCEPTED)
def antifilter_refresh(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    task_id = create_cidr_task("antifilter_refresh", "Обновление антифильтра запущено в фоне")
    triggered_by = f"manual:{user.username}"

    def _runner(progress_callback):
        from app.database import SessionLocal

        inner_db = SessionLocal()
        try:
            return CidrDbUpdaterService(db=inner_db).refresh_antifilter(
                triggered_by=triggered_by,
                progress_callback=progress_callback,
            )
        finally:
            inner_db.close()

    start_cidr_task(task_id, _runner)
    return {
        "success": True,
        "queued": True,
        "task_id": task_id,
        "message": "Обновление антифильтра запущено в фоне (~1–2 минуты)",
    }


@router.post("/seed-presets")
def seed_presets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    _svc(db).seed_builtin_presets()
    return {"success": True, "message": "Встроенные пресеты обновлены"}
