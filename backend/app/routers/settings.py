from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User
from app.schemas import AppSettingsResponse, AppSettingsUpdate, MessageResponse
from app.services.antizapret import antizapret_service

router = APIRouter(prefix="/settings", tags=["settings"])
settings = get_settings()


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
    include_hosts = antizapret_service.read_config_file("include-hosts.txt")
    exclude_hosts = antizapret_service.read_config_file("exclude-hosts.txt")
    include_ips = antizapret_service.read_config_file("include-ips.txt")

    if current_user.role.value != "admin":
        include_hosts = ""
        exclude_hosts = ""
        include_ips = ""

    return AppSettingsResponse(
        theme=current_user.theme,
        app_name=_get_setting(db, "app_name", settings.app_name),
        antizapret_path=str(settings.antizapret_path),
        include_hosts=include_hosts,
        exclude_hosts=exclude_hosts,
        include_ips=include_ips,
    )


@router.patch("", response_model=AppSettingsResponse)
def update_settings(
    payload: AppSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config_changed = False

    if payload.theme is not None:
        current_user.theme = payload.theme
        db.add(current_user)

    if current_user.role.value == "admin":
        if payload.include_hosts is not None:
            antizapret_service.write_config_file("include-hosts.txt", payload.include_hosts)
            config_changed = True
        if payload.exclude_hosts is not None:
            antizapret_service.write_config_file("exclude-hosts.txt", payload.exclude_hosts)
            config_changed = True
        if payload.include_ips is not None:
            antizapret_service.write_config_file("include-ips.txt", payload.include_ips)
            config_changed = True

        if config_changed:
            try:
                antizapret_service.apply_config_changes()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Ошибка применения настроек: {exc}",
                ) from exc
    elif any(v is not None for v in [payload.include_hosts, payload.exclude_hosts, payload.include_ips]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять списки AntiZapret")

    db.commit()
    db.refresh(current_user)
    return get_settings(current_user=current_user, db=db)


@router.post("/recreate-profiles", response_model=MessageResponse)
def recreate_profiles(_: User = Depends(require_admin)):
    output = antizapret_service.recreate_profiles()
    return MessageResponse(message="Профили пересозданы", detail=output)
