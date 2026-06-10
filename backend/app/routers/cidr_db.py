"""CIDR database pipeline API (download, antifilter, generate)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import CidrPresetCreateRequest, CidrPresetUpdateRequest
from app.services.action_log import log_action
from app.services.cidr.cidr_tasks import (
    create_cidr_task,
    find_active_cidr_task,
    find_any_active_pipeline_task,
    find_last_completed_cidr_task,
    get_cidr_task,
    serialize_cidr_task,
    start_cidr_task,
)
from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.db_pipeline import estimate_cidr_matches_from_db
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.models import Node
from app.services.cidr.pipeline.orchestrator import (
    run_apply,
    run_compile,
    run_deploy,
    run_ingest,
    run_multi_deploy,
)
from app.services.cidr.pipeline.deploy import list_compile_artifacts
from app.services.node_manager import get_active_adapter, get_adapter_for_node

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
    deploy_after: bool = True
    target_node_id: int | None = None


class CidrDbDeployRequest(BaseModel):
    target_node_id: int | None = None
    target_node_ids: list[int] | None = None
    all_online: bool = False
    sync_after: bool = True
    apply_after: bool = False
    selected_files: list[str] | None = None


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


def _summarize_last_compile() -> dict | None:
    task = find_last_completed_cidr_task("cidr_generate_from_db")
    if not task:
        return None
    result = task.get("result") or {}
    updated = result.get("updated") or []
    return {
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
        "files_updated": len(updated),
        "artifact_stamp": result.get("artifact_stamp"),
        "message": task.get("message"),
    }


def _summarize_last_deploy() -> dict | None:
    task = find_last_completed_cidr_task("cidr_deploy")
    if not task:
        return None
    result = task.get("result") or {}
    deploy = result.get("deploy") or {}
    per_node = result.get("per_node") or []
    return {
        "finished_at": task.get("finished_at"),
        "status": task.get("status"),
        "pushed_count": len(deploy.get("pushed") or []),
        "failed_count": len(deploy.get("failed") or []),
        "target_node_id": result.get("target_node_id"),
        "artifact_stamp": result.get("artifact_stamp"),
        "nodes_deployed": result.get("nodes_deployed", len([n for n in per_node if n.get("status") == "success"])),
        "nodes_failed": result.get("nodes_failed", len([n for n in per_node if n.get("status") == "failed"])),
        "nodes_skipped": result.get("nodes_skipped", len([n for n in per_node if n.get("status") == "skipped"])),
        "per_node": per_node,
        "message": task.get("message"),
    }


def _deploy_target_label(payload: CidrDbDeployRequest) -> str:
    if payload.all_online:
        return "all_online"
    if payload.target_node_ids:
        return ",".join(str(node_id) for node_id in payload.target_node_ids)
    if payload.target_node_id is not None:
        return str(payload.target_node_id)
    return "active"


def _enrich_preset_providers_meta(presets: list[dict]) -> list[dict]:
    for preset in presets:
        meta = {}
        for prov_key in preset.get("providers", []):
            ip_meta = IP_FILES.get(prov_key, {})
            meta[prov_key] = {
                "name": ip_meta.get("name", prov_key),
                "category": ip_meta.get("category", ""),
                "tags": ip_meta.get("tags", []),
            }
        preset["providers_meta"] = meta
    return presets


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
        "last_compile_at": _summarize_last_compile(),
        "last_deploy": _summarize_last_deploy(),
        "compile_artifacts": list_compile_artifacts(),
        "active_task": find_any_active_pipeline_task(),
    }


@router.get("/deploy/status")
def cidr_deploy_status(_: User = Depends(get_current_user)):
    """Last completed CIDR deploy with per-node results."""
    summary = _summarize_last_deploy()
    if not summary:
        return {"success": True, "last_deploy": None}
    return {"success": True, "last_deploy": summary}


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

    active = find_active_cidr_task(task_type)
    if active:
        return {
            "success": True,
            "queued": True,
            "task_id": active["task_id"],
            "message": "Обновление CIDR БД уже выполняется",
        }

    task_id = create_cidr_task(task_type, message)

    def _runner(progress_callback):
        from app.database import SessionLocal

        inner_db = SessionLocal()
        try:
            return run_ingest(
                inner_db,
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

        result = run_compile(progress_callback=progress_callback, **common_kwargs)
        if not (result.get("success") or result.get("updated")):
            return result

        inner_db = SessionLocal()
        try:
            if payload.target_node_id is not None:
                node = inner_db.query(Node).filter(Node.id == payload.target_node_id).first()
                if not node:
                    result["deploy"] = {
                        "pushed": [],
                        "failed": [{"file": "*", "error": f"Узел {payload.target_node_id} не найден"}],
                    }
                    return result
                adapter = get_adapter_for_node(node)
            else:
                adapter = get_active_adapter(inner_db)

            if payload.deploy_after:
                deploy_result = run_deploy(adapter, files=result.get("updated"))
                result["deploy"] = {
                    "pushed": deploy_result.get("pushed", []),
                    "failed": deploy_result.get("failed", []),
                }
                if deploy_result.get("sync") is not None:
                    result["sync"] = deploy_result["sync"]

            if payload.sync_after:
                apply_result = run_apply(
                    adapter,
                    sync_after=not payload.deploy_after,
                    apply_after=payload.apply_after,
                )
                result.update(apply_result)
        finally:
            inner_db.close()
        return result

    start_cidr_task(task_id, _generate_runner)
    return {"success": True, "queued": True, "task_id": task_id, "message": "Генерация CIDR-файлов из БД запущена"}


@router.post("/deploy", status_code=status.HTTP_202_ACCEPTED)
def cidr_db_deploy(
    payload: CidrDbDeployRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    active = find_active_cidr_task("cidr_deploy")
    if active:
        return {
            "success": True,
            "queued": True,
            "task_id": active["task_id"],
            "message": "Развёртывание CIDR уже выполняется",
        }

    triggered_by = f"manual:{user.username}"
    task_id = create_cidr_task("cidr_deploy", "Развёртывание CIDR-файлов на ноду запущено")

    def _deploy_runner(progress_callback):
        from app.database import SessionLocal

        inner_db = SessionLocal()
        try:
            result = run_multi_deploy(
                inner_db,
                target_node_ids=payload.target_node_ids,
                all_online=payload.all_online,
                target_node_id=payload.target_node_id,
                files=payload.selected_files,
                sync_after=payload.sync_after,
                apply_after=payload.apply_after,
                triggered_by=triggered_by,
            )
            if payload.target_node_id is not None and not payload.target_node_ids and not payload.all_online:
                result["target_node_id"] = payload.target_node_id
            return result
        finally:
            inner_db.close()

    start_cidr_task(task_id, _deploy_runner)
    log_action(
        db,
        action="settings_cidr_deploy",
        user_id=user.id,
        username=user.username,
        details=_deploy_target_label(payload),
    )
    return {
        "success": True,
        "queued": True,
        "task_id": task_id,
        "message": "Развёртывание CIDR-файлов на ноду запущено",
    }


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
    active = find_active_cidr_task("antifilter_refresh")
    if active:
        return {
            "success": True,
            "queued": True,
            "task_id": active["task_id"],
            "message": "Обновление антифильтра уже выполняется (~3–5 минут)",
        }

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
        "message": "Обновление антифильтра запущено в фоне (~1–3 минуты)",
    }


@router.post("/seed-presets")
def seed_presets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    _svc(db).seed_builtin_presets()
    return {"success": True, "message": "Встроенные пресеты обновлены"}


@router.get("/presets")
def list_presets(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    presets = _enrich_preset_providers_meta(_svc(db).get_presets())
    return {"success": True, "presets": presets}


@router.post("/presets", status_code=status.HTTP_201_CREATED)
def create_preset(
    payload: CidrPresetCreateRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Необходимо указать имя пресета")
    if not payload.providers:
        raise HTTPException(status_code=400, detail="Необходимо указать список провайдеров")

    settings = payload.settings.model_dump() if payload.settings else None
    preset = _svc(db).create_preset(
        name=name,
        description=payload.description,
        providers=payload.providers,
        settings=settings,
    )
    log_action(
        db,
        action="settings_cidr_preset_create",
        user_id=user.id,
        username=user.username,
        details=name,
    )
    return {"success": True, "preset": preset}


@router.put("/presets/{preset_id}")
def update_preset(
    preset_id: int,
    payload: CidrPresetUpdateRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings = payload.settings.model_dump() if payload.settings is not None else None
    preset = _svc(db).update_preset(
        preset_id,
        name=payload.name.strip() if payload.name is not None else None,
        description=payload.description if payload.description is not None else None,
        providers=payload.providers,
        settings=settings,
    )
    if not preset:
        raise HTTPException(status_code=404, detail="Пресет не найден")
    log_action(
        db,
        action="settings_cidr_preset_update",
        user_id=user.id,
        username=user.username,
        details=str(preset_id),
    )
    return {"success": True, "preset": preset}


@router.delete("/presets/{preset_id}")
def delete_preset(
    preset_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ok, msg = _svc(db).delete_preset(preset_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    log_action(
        db,
        action="settings_cidr_preset_delete",
        user_id=user.id,
        username=user.username,
        details=str(preset_id),
    )
    return {"success": True, "message": msg}


@router.post("/presets/{preset_id}/reset")
def reset_preset(
    preset_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    preset = _svc(db).reset_builtin_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Встроенный пресет не найден")
    log_action(
        db,
        action="settings_cidr_preset_reset",
        user_id=user.id,
        username=user.username,
        details=str(preset_id),
    )
    return {"success": True, "preset": preset}
