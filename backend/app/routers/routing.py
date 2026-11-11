import logging
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
    RoutingOverview,
)
from app.services.antizapret_params import needs_antizapret_restart
from app.services.antizapret_settings import (
    VERIFIED_WRITE_TYPES,
    az_host_updates_conflict_with_panel_domain,
    build_schema,
    filter_known_keys,
    normalize_choice_settings,
    openvpn_backup_tcp_conflict_warnings,
    setting_write_mismatch_warnings,
)
from app.services.background_tasks import background_task_service
from app.services.env_file import EnvFileService
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.antizapret_sync import enqueue_ha_routing_apply_replicas, replicate_antizapret_settings
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import find_sync_group_for_primary, is_auto_sync_enabled, require_ha_primary_for_config_ops
from app.services.node_sync.provider_sync import deploy_compiled_providers_to_replicas, replicate_provider_content
from app.services.profile_delivery import load_node_remote_hosts

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

logger = logging.getLogger(__name__)
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
            node = get_active_node(worker_db)
            return background_task_service.task_routing_apply(
                adapter,
                progress_updater,
                hosts=load_node_remote_hosts(worker_db, node.id),
                ensure_openvpn_multihome=bool(node.openvpn_multihome),
            )
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
    settings = normalize_choice_settings(adapter.get_antizapret_settings())
    return AntizapretSettingsResponse(
        settings=settings,
        param_schema=[AntizapretSettingFieldSchema(**item) for item in build_schema()],
        node_id=node.id,
        node_name=node.name,
    )


def apply_antizapret_runtime_changes(
    adapter: Any,
    filtered: dict[str, Any],
    result: dict[str, Any],
    *,
    previous_subnets: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Применить файлы, которые setup.sh/update.sh не переписывают, и один раз перезапустить antizapret.

    Порядок важен: ``antizapret.service`` запускает ``/root/antizapret/proxy.py``. Сначала
    патчим ``proxy.py`` (``--fake-cidr``), потом перезапускаем службу — иначе новый fake-пул
    заработает только при следующем перезапуске, а up.sh уже поднимет правила под новые
    подсети. Один рестарт на всю пачку изменений.
    """
    subnets_requested = bool({"alternative_client_ip", "alternative_fake_ip"} & set(filtered))
    subnets_changed = False
    subnets_failed = False
    if subnets_requested:
        try:
            current = adapter.get_antizapret_settings()
            outcome = adapter.apply_client_subnets(
                alternative_client_ip=current.get("alternative_client_ip", "y") == "y",
                alternative_fake_ip=current.get("alternative_fake_ip", "y") == "y",
            )
            result["warnings"].extend(outcome.get("warnings") or [])
            result["restarted"] = [*(result.get("restarted") or []), *(outcome.get("restarted") or [])]
            subnets_changed = bool(outcome.get("changed"))
        except NotImplementedError:
            subnets_failed = True
            result["warnings"].append(
                "Подсети клиентов переключаются только на VPN-узле: обновите node agent на этом узле"
            )
        except Exception as exc:  # noqa: BLE001 — setup уже сохранён, файлы правим best-effort
            subnets_failed = True
            detail = getattr(exc, "detail", str(exc))
            logger.warning("client subnet change failed: %s", detail)
            result["warnings"].append(f"Подсети клиентов не применены к kresd.conf / proxy.py: {detail}")

    # up.sh читает firewall/WARP-ключи только при старте службы: без рестарта правила не меняются.
    rolled_back = False
    if subnets_failed and previous_subnets:
        try:
            adapter.update_antizapret_settings(previous_subnets)
            rolled_back = True
            if set(filtered) <= {"alternative_client_ip", "alternative_fake_ip"}:
                result["changes"] = 0
                result["needs_apply"] = False
            result["warnings"].append(
                "Настройки подсетей в setup возвращены как были — после обновления node agent "
                "переключите их снова"
            )
        except Exception as exc:  # noqa: BLE001 — best-effort откат
            logger.warning("client subnet rollback failed: %s", exc)
            result["warnings"].append(
                f"Не удалось вернуть прежние подсети в setup: {getattr(exc, 'detail', exc)}"
            )

    if subnets_failed and not rolled_back:
        result["warnings"].append(
            "Служба antizapret не перезапущена, чтобы правила не разошлись с proxy.py: "
            "обновите node agent на узле и сохраните настройки ещё раз"
        )
    elif needs_antizapret_restart(filtered) and (result.get("changes") or subnets_changed):
        try:
            adapter.restart_service("antizapret")
            result["antizapret_restarted"] = True
        except Exception as exc:  # noqa: BLE001 — настройки уже сохранены, отдаём предупреждение
            detail = getattr(exc, "detail", str(exc))
            logger.warning("antizapret restart failed after settings save: %s", detail)
            result["warnings"].append(
                f"Служба antizapret не перезапустилась, правила остались прежними: {detail}. "
                "На удалённом узле нужен node agent 1.15.0 или новее (Узлы → Обновить)."
            )
    return result


@router.put("/antizapret-settings", response_model=AntizapretSettingsUpdateResponse)
def put_antizapret_settings(
    payload: dict[str, Any],
    apply: bool = Query(False, description="После сохранения поставить apply в очередь (только HA auto)"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_ha_primary_for_config_ops(db)
    filtered = filter_known_keys(payload)
    env = EnvFileService(_ENV_FILE)
    host_conflict = az_host_updates_conflict_with_panel_domain(
        filtered,
        env.get_env_value("DOMAIN", ""),
    )
    if host_conflict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=host_conflict)
    adapter = get_active_adapter(db)
    previous_subnets: dict[str, str] = {}
    if {"alternative_client_ip", "alternative_fake_ip"} & set(filtered):
        try:
            current = adapter.get_antizapret_settings()
        except Exception as exc:  # noqa: BLE001 — откат подсетей best-effort
            logger.warning("cannot read current subnets before save: %s", exc)
            current = {}
        previous_subnets = {
            key: current[key]
            for key in ("alternative_client_ip", "alternative_fake_ip")
            if key in current
        }
    try:
        result = adapter.update_antizapret_settings(filtered)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на запись") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    https_public_port = env.get_env_value("HTTPS_PUBLIC_PORT", "443") or "443"
    warnings = list(result.get("warnings") or [])
    if any(
        (field["type"] in VERIFIED_WRITE_TYPES or field.get("verify_write")) and field["key"] in filtered
        for field in build_schema()
    ):
        try:
            warnings.extend(setting_write_mismatch_warnings(filtered, adapter.get_antizapret_settings()))
        except Exception as exc:  # noqa: BLE001 — best-effort verification
            logger.warning("antizapret settings write verification failed: %s", exc)
    for warning in openvpn_backup_tcp_conflict_warnings(filtered, https_public_port=https_public_port):
        if warning not in warnings:
            warnings.append(warning)
    result["warnings"] = warnings

    result = apply_antizapret_runtime_changes(adapter, filtered, result, previous_subnets=previous_subnets)

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
