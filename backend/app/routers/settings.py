import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User
from app.schemas import AppSettingsResponse, AppSettingsUpdate, MessageResponse, MonitorSettingsResponse, MonitorSettingsUpdate
from app.services.admin_notify import admin_notify_service
from app.services.env_file import EnvFileService
from app.services.node_manager import get_active_adapter, get_active_node, get_node_antizapret_path
from app.services.notify_time import get_client_timezone_from_request

router = APIRouter(prefix="/settings", tags=["settings"])
settings = get_settings()
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


@router.get("", response_model=AppSettingsResponse)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    include_hosts = adapter.read_config_file("include-hosts.txt")
    exclude_hosts = adapter.read_config_file("exclude-hosts.txt")
    include_ips = adapter.read_config_file("include-ips.txt")
    exclude_ips = adapter.read_config_file("exclude-ips.txt")
    allow_ips = adapter.read_config_file("allow-ips.txt")

    if current_user.role.value != "admin":
        include_hosts = ""
        exclude_hosts = ""
        include_ips = ""
        exclude_ips = ""
        allow_ips = ""

    return AppSettingsResponse(
        theme=current_user.theme,
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

    if current_user.role.value == "admin":
        adapter = get_active_adapter(db)
        if payload.include_hosts is not None:
            adapter.write_config_file("include-hosts.txt", payload.include_hosts)
            config_changed = True
        if payload.exclude_hosts is not None:
            adapter.write_config_file("exclude-hosts.txt", payload.exclude_hosts)
            config_changed = True
        if payload.include_ips is not None:
            adapter.write_config_file("include-ips.txt", payload.include_ips)
            config_changed = True
        if payload.exclude_ips is not None:
            adapter.write_config_file("exclude-ips.txt", payload.exclude_ips)
            config_changed = True
        if payload.allow_ips is not None:
            adapter.write_config_file("allow-ips.txt", payload.allow_ips)
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
    cfg = get_settings()
    return MonitorSettingsResponse(
        cpu_threshold=cfg.monitor_cpu_threshold,
        ram_threshold=cfg.monitor_ram_threshold,
        interval_seconds=cfg.monitor_check_interval_seconds,
        cooldown_minutes=cfg.monitor_cooldown_minutes,
    )


@router.patch("/monitor", response_model=MonitorSettingsResponse)
def update_monitor_settings(
    payload: MonitorSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    env_service = EnvFileService(ENV_FILE)
    cfg = get_settings()
    cpu = payload.cpu_threshold if payload.cpu_threshold is not None else cfg.monitor_cpu_threshold
    ram = payload.ram_threshold if payload.ram_threshold is not None else cfg.monitor_ram_threshold
    interval = payload.interval_seconds if payload.interval_seconds is not None else cfg.monitor_check_interval_seconds
    cooldown = payload.cooldown_minutes if payload.cooldown_minutes is not None else cfg.monitor_cooldown_minutes

    env_service.set_env_value("MONITOR_CPU_THRESHOLD", str(cpu))
    env_service.set_env_value("MONITOR_RAM_THRESHOLD", str(ram))
    env_service.set_env_value("MONITOR_CHECK_INTERVAL_SECONDS", str(interval))
    env_service.set_env_value("MONITOR_COOLDOWN_MINUTES", str(cooldown))
    os.environ["MONITOR_CPU_THRESHOLD"] = str(cpu)
    os.environ["MONITOR_RAM_THRESHOLD"] = str(ram)
    os.environ["MONITOR_CHECK_INTERVAL_SECONDS"] = str(interval)
    os.environ["MONITOR_COOLDOWN_MINUTES"] = str(cooldown)
    get_settings.cache_clear()

    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_monitor_update",
        details=f"cpu={cpu}% ram={ram}% interval={interval}s cooldown={cooldown}min",
        client_timezone=get_client_timezone_from_request(request),
    )
    updated = get_settings()
    return MonitorSettingsResponse(
        cpu_threshold=updated.monitor_cpu_threshold,
        ram_threshold=updated.monitor_ram_threshold,
        interval_seconds=updated.monitor_check_interval_seconds,
        cooldown_minutes=updated.monitor_cooldown_minutes,
    )
