from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import BackgroundTask, User
from app.schemas import (
    AntizapretSettingFieldSchema,
    AntizapretSettingsResponse,
    AntizapretSettingsUpdateResponse,
    MessageResponse,
    RoutingOverview,
)
from app.services.antizapret_settings import (
    build_schema,
    filter_known_keys,
    openvpn_backup_tcp_conflict_warnings,
)
from app.services.background_tasks import background_task_service
from app.services.env_file import EnvFileService
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.antizapret_sync import enqueue_ha_routing_apply_replicas, replicate_antizapret_settings
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import find_sync_group_for_primary, is_auto_sync_enabled, require_ha_primary_for_config_ops
from app.services.node_sync.provider_sync import deploy_compiled_providers_to_replicas, replicate_provider_content

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

router = APIRouter(prefix="/routing", tags=["routing"])


def _enqueue_routing_apply_tasks(
    db: Session,
    *,
    created_by_username: str,
) -> BackgroundTask | None:
    """Enqueue routing apply on primary and HA replicas (independent background tasks)."""
    if background_task_service.find_active_task("routing_apply"):
        return None

    def _callable(progress_updater=None):
        from app.database import SessionLocal

        worker_db = SessionLocal()
        try:
            adapter = get_active_adapter(worker_db)
            return background_task_service.task_routing_apply(adapter, progress_updater)
        finally:
            worker_db.close()

    task = background_task_service.enqueue_background_task(
        "routing_apply",
        _callable,
        created_by_username=created_by_username,
        queued_message="Применение маршрутизации поставлено в очередь",
    )

    active_node = get_active_node(db)
    group = find_sync_group_for_primary(db, active_node.id)
    if group and is_auto_sync_enabled(group):
        enqueue_ha_routing_apply_replicas(db, group, created_by_username=created_by_username)

    return task


class ContentUpdate(BaseModel):
    content: str = ""


class ProviderEnabledUpdate(BaseModel):
    enabled: bool


@router.get("/overview", response_model=RoutingOverview)
def routing_overview(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_routing_overview()
    return RoutingOverview(
        **data,
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
    )


@router.get("/providers/{filename}")
def get_provider(filename: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_active_adapter(db).get_provider_content(filename)


@router.put("/providers/{filename}")
def save_provider(
    filename: str,
    payload: ContentUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_ha_primary_for_config_ops(db)
    result = get_active_adapter(db).save_provider_content(filename, payload.content)
    active_node = get_active_node(db)
    group = find_sync_group_for_primary(db, active_node.id)
    if group and is_auto_sync_enabled(group):
        replicate_provider_content(db, group, filename, payload.content)
    return result


@router.post("/providers/{filename}/enabled")
def toggle_provider(
    filename: str,
    payload: ProviderEnabledUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_ha_primary_for_config_ops(db)
    return get_active_adapter(db).set_provider_enabled(filename, payload.enabled)


@router.post("/sync")
def sync_providers(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    require_ha_primary_for_config_ops(db)
    adapter = get_active_adapter(db)
    result = adapter.sync_cidr_providers()
    active_node = get_active_node(db)
    group = find_sync_group_for_primary(db, active_node.id)
    if group and is_auto_sync_enabled(group):
        ha_deploy = deploy_compiled_providers_to_replicas(db, group, adapter, sync_result=result)
        result = {**result, "ha_deploy": ha_deploy}
    return result


@router.get("/files/{file_key}")
def read_route_file(file_key: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_active_adapter(db).read_route_file(file_key)


@router.put("/files/{file_key}")
def write_route_file(
    file_key: str,
    payload: ContentUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_ha_primary_for_config_ops(db)
    result = get_active_adapter(db).write_route_file(file_key, payload.content)
    maybe_replicate_config_files(
        db,
        node_id=get_active_node(db).id,
        file_keys=[file_key],
        run_doall=False,
        content_overrides={file_key: payload.content},
    )
    return result


@router.get("/results")
def result_files(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_active_adapter(db).get_route_result_files()


@router.get("/results/{key}")
def result_content(key: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_active_adapter(db).get_route_result_content(key)


@router.get("/antizapret-settings", response_model=AntizapretSettingsResponse)
def get_antizapret_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    settings = adapter.get_antizapret_settings()
    return AntizapretSettingsResponse(
        settings=settings,
        param_schema=[AntizapretSettingFieldSchema(**item) for item in build_schema()],
        node_id=node.id,
        node_name=node.name,
    )


@router.put("/antizapret-settings", response_model=AntizapretSettingsUpdateResponse)
def put_antizapret_settings(
    payload: dict[str, Any],
    apply: bool = Query(False, description="После сохранения поставить apply в очередь (только HA auto)"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_ha_primary_for_config_ops(db)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается JSON-объект")
    filtered = filter_known_keys(payload)
    try:
        result = get_active_adapter(db).update_antizapret_settings(filtered)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на запись") from exc

    https_public_port = EnvFileService(_ENV_FILE).get_env_value("HTTPS_PUBLIC_PORT", "443") or "443"
    warnings = list(result.get("warnings") or [])
    for warning in openvpn_backup_tcp_conflict_warnings(filtered, https_public_port=https_public_port):
        if warning not in warnings:
            warnings.append(warning)
    result["warnings"] = warnings

    active_node = get_active_node(db)
    group = find_sync_group_for_primary(db, active_node.id)
    if group and is_auto_sync_enabled(group):
        replicate_antizapret_settings(db, group, filtered)
        if apply:
            _enqueue_routing_apply_tasks(db, created_by_username=admin.username)

    return AntizapretSettingsUpdateResponse(**result)


@router.post("/apply", status_code=status.HTTP_202_ACCEPTED)
def apply_routing(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    require_ha_primary_for_config_ops(db)
    active = background_task_service.find_active_task("routing_apply")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Применение маршрутизации уже выполняется",
                "active_task_id": active.id,
            },
        )

    task = _enqueue_routing_apply_tasks(db, created_by_username=admin.username)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Применение маршрутизации уже выполняется",
        )

    return background_task_service.build_accepted_payload(
        task,
        "Маршрутизация запущена в фоне (sync + doall.sh)",
    )
