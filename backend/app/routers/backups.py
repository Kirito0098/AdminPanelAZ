from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User
from app.services.action_log import log_action
from app.services.ip_restriction import ip_restriction_service
from app.schemas import (
    BackupCreateRequest,
    BackupEntry,
    BackupRestoreRequest,
    BackupSettingsResponse,
    BackupSettingsUpdate,
    MessageResponse,
)
from app.services.backup_manager import BackupManager
from app.services.node_manager import get_active_adapter
from app.services.telegram import send_tg_document, send_tg_message

router = APIRouter(prefix="/backups", tags=["backups"])
settings = get_settings()


def _get_backup_manager() -> BackupManager:
    app_root = Path(__file__).resolve().parents[2]
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        if not db_path.is_absolute():
            db_path = app_root / db_path
    else:
        db_path = app_root / "data" / "adminpanel.db"
    return BackupManager(
        app_root=app_root,
        backup_root=Path(settings.backup_root),
        db_path=db_path,
        env_path=app_root / ".env",
    )


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


@router.get("", response_model=list[BackupEntry])
def list_backups(_: User = Depends(require_admin)):
    return _get_backup_manager().list_backups()


@router.get("/settings", response_model=BackupSettingsResponse)
def get_backup_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return BackupSettingsResponse(
        auto_backup_enabled=_get_setting(db, "backup_auto_enabled", "false") == "true",
        auto_backup_days=int(_get_setting(db, "backup_auto_days", "7") or "7"),
        telegram_on_backup=_get_setting(db, "backup_telegram_enabled", "false") == "true",
        retention_count=int(_get_setting(db, "backup_retention", "5") or "5"),
    )


@router.patch("/settings", response_model=BackupSettingsResponse)
def update_backup_settings(
    payload: BackupSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if payload.auto_backup_enabled is not None:
        _set_setting(db, "backup_auto_enabled", "true" if payload.auto_backup_enabled else "false")
    if payload.auto_backup_days is not None:
        _set_setting(db, "backup_auto_days", str(payload.auto_backup_days))
    if payload.telegram_on_backup is not None:
        _set_setting(db, "backup_telegram_enabled", "true" if payload.telegram_on_backup else "false")
    if payload.retention_count is not None:
        _set_setting(db, "backup_retention", str(payload.retention_count))
    db.commit()
    return BackupSettingsResponse(
        auto_backup_enabled=_get_setting(db, "backup_auto_enabled", "false") == "true",
        auto_backup_days=int(_get_setting(db, "backup_auto_days", "7") or "7"),
        telegram_on_backup=_get_setting(db, "backup_telegram_enabled", "false") == "true",
        retention_count=int(_get_setting(db, "backup_retention", "5") or "5"),
    )


@router.post("/create", response_model=BackupEntry)
def create_backup(
    payload: BackupCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    manager = _get_backup_manager()
    config_contents: dict[str, str] | None = None
    if payload.include_configs:
        adapter = get_active_adapter(db)
        config_contents = {
            fname: adapter.read_config_file(fname)
            for fname in BackupManager.CONFIG_FILES
        }

    result = manager.create_backup(
        include_configs=payload.include_configs,
        config_contents=config_contents,
    )

    if _get_setting(db, "backup_telegram_enabled", "false") == "true":
        bot_token = _get_setting(db, "telegram_bot_token")
        chat_id = _get_setting(db, "telegram_chat_id")
        if bot_token and chat_id:
            archive_path = manager.get_backup_path(result["file_name"])
            send_tg_document(
                bot_token,
                chat_id,
                str(archive_path),
                caption=f"Бэкап AdminPanelAZ: {result['file_name']}",
            )

    return BackupEntry(**result)


@router.post("/restore", response_model=MessageResponse)
def restore_backup(
    payload: BackupRestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = _get_backup_manager().restore_backup(payload.file_name)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="backup_restore",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=payload.file_name,
        )
    return MessageResponse(
        message="Восстановление выполнено. Перезапустите панель для применения БД.",
        detail=result,
    )


@router.delete("/{file_name}", response_model=MessageResponse)
def delete_backup(file_name: str, _: User = Depends(require_admin)):
    _get_backup_manager().delete_backup(file_name)
    return MessageResponse(message=f"Архив {file_name} удалён")


@router.get("/{file_name}/download")
def download_backup(file_name: str, _: User = Depends(require_admin)):
    path = _get_backup_manager().get_backup_path(file_name)
    return FileResponse(path, filename=file_name, media_type="application/gzip")
