import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings as load_app_config
from app.database import get_db
from app.models import AppSetting, User
from app.schemas import AppSettingsResponse, AppSettingsUpdate, MessageResponse, MonitorSettingsResponse, MonitorSettingsUpdate, RetentionSettingsResponse, RetentionSettingsUpdate
from app.services.admin_notify import admin_notify_service
from app.services.env_file import EnvFileService
from app.services.file_editor import EDITABLE_FILES
from app.services.node_manager import get_active_adapter, get_active_node, get_node_antizapret_path
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import require_ha_primary_for_config_ops
from app.services.notify_time import _normalize_timezone_name, get_client_timezone_from_request

router = APIRouter(prefix="/settings", tags=["settings"])
settings = load_app_config()
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


_CONFIG_FILE_NAMES = (
    "include-hosts.txt",
    "exclude-hosts.txt",
    "include-ips.txt",
    "exclude-ips.txt",
    "allow-ips.txt",
)

_SETTINGS_FIELD_TO_FILE_KEY: dict[str, str] = {
    "include_hosts": "include_hosts",
    "exclude_hosts": "exclude_hosts",
    "include_ips": "include_ips",
    "exclude_ips": "exclude_ips",
    "allow_ips": "allow_ips",
}


def _read_config_files_parallel(adapter, filenames: tuple[str, ...]) -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=len(filenames)) as pool:
        contents = list(pool.map(adapter.read_config_file, filenames))
    return dict(zip(filenames, contents, strict=True))


@router.get("", response_model=AppSettingsResponse)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    file_contents = _read_config_files_parallel(adapter, _CONFIG_FILE_NAMES)
    include_hosts = file_contents["include-hosts.txt"]
    exclude_hosts = file_contents["exclude-hosts.txt"]
    include_ips = file_contents["include-ips.txt"]
    exclude_ips = file_contents["exclude-ips.txt"]
    allow_ips = file_contents["allow-ips.txt"]

    if current_user.role.value != "admin":
        include_hosts = ""
        exclude_hosts = ""
        include_ips = ""
        exclude_ips = ""
        allow_ips = ""

    return AppSettingsResponse(
        theme=current_user.theme,
        timezone=current_user.timezone or "",
        app_name=_get_setting(db, "app_name", settings.app_name),
        antizapret_path=str(get_node_antizapret_path(db)),
        include_hosts=include_hosts,
        exclude_hosts=exclude_hosts,
        include_ips=include_ips,
        exclude_ips=exclude_ips,
        allow_ips=allow_ips,
        node_id=node.id,
        node_name=node.name,
    )


@router.patch("", response_model=AppSettingsResponse)
def update_settings(
    payload: AppSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config_changed = False

    if payload.theme is not None:
        current_user.theme = payload.theme
        db.add(current_user)

    if payload.timezone is not None:
        tz_raw = payload.timezone.strip()
        if tz_raw == "":
            current_user.timezone = ""
        else:
            normalized = _normalize_timezone_name(tz_raw)
            if normalized is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Неизвестный часовой пояс: {tz_raw}",
                )
            current_user.timezone = normalized
        db.add(current_user)

    if current_user.role.value == "admin":
        require_ha_primary_for_config_ops(db)
        adapter = get_active_adapter(db)
        changed_file_keys: list[str] = []
        content_overrides: dict[str, str] = {}
        payload_fields = payload.model_dump(exclude_unset=True)
        for field_name, file_key in _SETTINGS_FIELD_TO_FILE_KEY.items():
            if field_name not in payload_fields:
                continue
            content = payload_fields[field_name]
            adapter.write_config_file(EDITABLE_FILES[file_key], content)
            changed_file_keys.append(file_key)
            content_overrides[file_key] = content
            config_changed = True

        if config_changed:
            try:
                adapter.apply_config_changes()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Ошибка применения настроек: {exc}",
                ) from exc
            node = get_active_node(db)
            maybe_replicate_config_files(
                db,
                node_id=node.id,
                file_keys=changed_file_keys,
                run_doall=True,
                content_overrides=content_overrides,
            )
            admin_notify_service.send_settings_change(
                db,
                actor_username=current_user.username,
                settings_key="settings_run_doall",
                node_id=node.id,
                node_name=node.name,
                client_timezone=get_client_timezone_from_request(request),
            )
    elif any(
        v is not None
        for v in [payload.include_hosts, payload.exclude_hosts, payload.include_ips, payload.exclude_ips, payload.allow_ips]
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять списки AntiZapret")

    db.commit()
    db.refresh(current_user)
    return get_settings(current_user=current_user, db=db)


@router.post("/recreate-profiles", response_model=MessageResponse)
def recreate_profiles(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    output = get_active_adapter(db).recreate_profiles()
    node = get_active_node(db)
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_run_doall",
        details="recreate_profiles",
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )
    return MessageResponse(message="Профили пересозданы", detail=output)


@router.get("/monitor", response_model=MonitorSettingsResponse)
def get_monitor_settings(_: User = Depends(require_admin)):
    cfg = load_app_config()
    return MonitorSettingsResponse(
        cpu_threshold=cfg.monitor_cpu_threshold,
        ram_threshold=cfg.monitor_ram_threshold,
        interval_seconds=cfg.monitor_check_interval_seconds,
        cooldown_minutes=cfg.monitor_cooldown_minutes,
        sustained_seconds=cfg.monitor_sustained_seconds,
    )


@router.patch("/monitor", response_model=MonitorSettingsResponse)
def update_monitor_settings(
    payload: MonitorSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    env_service = EnvFileService(ENV_FILE)
    cfg = load_app_config()
    cpu = payload.cpu_threshold if payload.cpu_threshold is not None else cfg.monitor_cpu_threshold
    ram = payload.ram_threshold if payload.ram_threshold is not None else cfg.monitor_ram_threshold
    interval = payload.interval_seconds if payload.interval_seconds is not None else cfg.monitor_check_interval_seconds
    cooldown = payload.cooldown_minutes if payload.cooldown_minutes is not None else cfg.monitor_cooldown_minutes
    sustained = (
        payload.sustained_seconds
        if payload.sustained_seconds is not None
        else cfg.monitor_sustained_seconds
    )

    env_service.set_env_value("MONITOR_CPU_THRESHOLD", str(cpu))
    env_service.set_env_value("MONITOR_RAM_THRESHOLD", str(ram))
    env_service.set_env_value("MONITOR_CHECK_INTERVAL_SECONDS", str(interval))
    env_service.set_env_value("MONITOR_COOLDOWN_MINUTES", str(cooldown))
    env_service.set_env_value("MONITOR_SUSTAINED_SECONDS", str(sustained))
    os.environ["MONITOR_CPU_THRESHOLD"] = str(cpu)
    os.environ["MONITOR_RAM_THRESHOLD"] = str(ram)
    os.environ["MONITOR_CHECK_INTERVAL_SECONDS"] = str(interval)
    os.environ["MONITOR_COOLDOWN_MINUTES"] = str(cooldown)
    os.environ["MONITOR_SUSTAINED_SECONDS"] = str(sustained)
    load_app_config.cache_clear()

    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_monitor_update",
        details=f"cpu={cpu}% ram={ram}% interval={interval}s cooldown={cooldown}min sustained={sustained}s",
        client_timezone=get_client_timezone_from_request(request),
    )
    updated = load_app_config()
    return MonitorSettingsResponse(
        cpu_threshold=updated.monitor_cpu_threshold,
        ram_threshold=updated.monitor_ram_threshold,
        interval_seconds=updated.monitor_check_interval_seconds,
        cooldown_minutes=updated.monitor_cooldown_minutes,
        sustained_seconds=updated.monitor_sustained_seconds,
    )


@router.get("/retention", response_model=RetentionSettingsResponse)
def get_retention_settings(_: User = Depends(require_admin)):
    cfg = load_app_config()
    return RetentionSettingsResponse(
        enabled=cfg.retention_enabled,
        interval_hours=cfg.retention_interval_hours,
        traffic_sample_retention_days=cfg.traffic_sample_retention_days,
        action_log_retention_days=cfg.action_log_retention_days,
        resource_metrics_retention_days=cfg.resource_metrics_retention_days,
        panel_resource_metrics_retention_days=cfg.panel_resource_metrics_retention_days,
    )


@router.patch("/retention", response_model=RetentionSettingsResponse)
def update_retention_settings(
    payload: RetentionSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    env_service = EnvFileService(ENV_FILE)
    cfg = load_app_config()

    if payload.enabled is not None:
        env_service.set_env_value("RETENTION_ENABLED", "true" if payload.enabled else "false")
        os.environ["RETENTION_ENABLED"] = "true" if payload.enabled else "false"
    if payload.interval_hours is not None:
        env_service.set_env_value("RETENTION_INTERVAL_HOURS", str(payload.interval_hours))
        os.environ["RETENTION_INTERVAL_HOURS"] = str(payload.interval_hours)
    if payload.traffic_sample_retention_days is not None:
        env_service.set_env_value("TRAFFIC_SAMPLE_RETENTION_DAYS", str(payload.traffic_sample_retention_days))
        os.environ["TRAFFIC_SAMPLE_RETENTION_DAYS"] = str(payload.traffic_sample_retention_days)
    if payload.action_log_retention_days is not None:
        env_service.set_env_value("ACTION_LOG_RETENTION_DAYS", str(payload.action_log_retention_days))
        os.environ["ACTION_LOG_RETENTION_DAYS"] = str(payload.action_log_retention_days)
    if payload.resource_metrics_retention_days is not None:
        env_service.set_env_value("RESOURCE_METRICS_RETENTION_DAYS", str(payload.resource_metrics_retention_days))
        os.environ["RESOURCE_METRICS_RETENTION_DAYS"] = str(payload.resource_metrics_retention_days)
    if payload.panel_resource_metrics_retention_days is not None:
        env_service.set_env_value(
            "PANEL_RESOURCE_METRICS_RETENTION_DAYS",
            str(payload.panel_resource_metrics_retention_days),
        )
        os.environ["PANEL_RESOURCE_METRICS_RETENTION_DAYS"] = str(payload.panel_resource_metrics_retention_days)

    load_app_config.cache_clear()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_retention_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    updated = load_app_config()
    return RetentionSettingsResponse(
        enabled=updated.retention_enabled,
        interval_hours=updated.retention_interval_hours,
        traffic_sample_retention_days=updated.traffic_sample_retention_days,
        action_log_retention_days=updated.action_log_retention_days,
        resource_metrics_retention_days=updated.resource_metrics_retention_days,
        panel_resource_metrics_retention_days=updated.panel_resource_metrics_retention_days,
    )
