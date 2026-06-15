from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    AntizapretSettingFieldSchema,
    AntizapretSettingsResponse,
    AntizapretSettingsUpdateResponse,
    MessageResponse,
    RoutingOverview,
)
from app.services.antizapret_settings import build_schema, filter_known_keys
from app.services.background_tasks import background_task_service
from app.services.node_manager import get_active_adapter, get_active_node

router = APIRouter(prefix="/routing", tags=["routing"])


class ContentUpdate(BaseModel):
    content: str = ""


class ProviderEnabledUpdate(BaseModel):
    enabled: bool


@router.get("/overview", response_model=RoutingOverview)
def routing_overview(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
def get_provider(filename: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_active_adapter(db).get_provider_content(filename)


@router.put("/providers/{filename}")
def save_provider(
    filename: str,
    payload: ContentUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_active_adapter(db).save_provider_content(filename, payload.content)


@router.post("/providers/{filename}/enabled")
def toggle_provider(
    filename: str,
    payload: ProviderEnabledUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_active_adapter(db).set_provider_enabled(filename, payload.enabled)


@router.post("/sync")
def sync_providers(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_active_adapter(db).sync_cidr_providers()


@router.get("/files/{file_key}")
def read_route_file(file_key: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_active_adapter(db).read_route_file(file_key)


@router.put("/files/{file_key}")
def write_route_file(
    file_key: str,
    payload: ContentUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_active_adapter(db).write_route_file(file_key, payload.content)


@router.get("/results")
def result_files(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_active_adapter(db).get_route_result_files()


@router.get("/results/{key}")
def result_content(key: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается JSON-объект")
    try:
        result = get_active_adapter(db).update_antizapret_settings(filter_known_keys(payload))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на запись") from exc
    return AntizapretSettingsUpdateResponse(**result)


@router.post("/apply", status_code=status.HTTP_202_ACCEPTED)
def apply_routing(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    active = background_task_service.find_active_task("routing_apply")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Применение маршрутизации уже выполняется",
                "active_task_id": active.id,
            },
        )

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
        created_by_username=admin.username,
        queued_message="Применение маршрутизации поставлено в очередь",
    )
    return background_task_service.build_accepted_payload(
        task,
        "Маршрутизация запущена в фоне (sync + doall.sh)",
    )
