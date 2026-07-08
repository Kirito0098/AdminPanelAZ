import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.cidr_database import resolve_cidr_db_path
from app.database import get_db, resolve_main_db_path
from app.models import AppSetting, User
from app.services.action_log import log_action
from app.services.ip_restriction import ip_restriction_service
from app.schemas import (
    BackupCreateRequest,
    BackupEntry,
    BackupRestoreRequest,
    BackupSettingsResponse,
    BackupSettingsUpdate,
    BackupTestTelegramRequest,
    MessageResponse,
)
from app.services.admin_notify import admin_notify_service
from app.services.background_tasks import background_task_service
from app.services.backup_manager import BackupManager
from app.services.node_manager import get_active_adapter
from app.services.notify_time import get_client_timezone_from_request
from app.services.telegram import send_tg_document, send_tg_message
from app.services.telegram_recipients import get_setting_chat_ids

router = APIRouter(prefix="/backups", tags=["backups"])
settings = get_settings()
logger = logging.getLogger(__name__)
MAX_BACKUP_UPLOAD_BYTES = 200 * 1024 * 1024


def _get_backup_manager() -> BackupManager:
    app_root = Path(__file__).resolve().parents[2]
    db_path = resolve_main_db_path()
    cidr_db_path = resolve_cidr_db_path()
    return BackupManager(
        app_root=app_root,
        backup_root=Path(settings.backup_root),
        db_path=db_path,
        cidr_db_path=cidr_db_path,
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
        backup_az_enabled=_get_setting(db, "backup_az_enabled", "true") == "true",
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
    if payload.backup_az_enabled is not None:
        _set_setting(db, "backup_az_enabled", "true" if payload.backup_az_enabled else "false")
    if payload.retention_count is not None:
        _set_setting(db, "backup_retention", str(payload.retention_count))
    db.commit()
    return BackupSettingsResponse(
        auto_backup_enabled=_get_setting(db, "backup_auto_enabled", "false") == "true",
        auto_backup_days=int(_get_setting(db, "backup_auto_days", "7") or "7"),
        telegram_on_backup=_get_setting(db, "backup_telegram_enabled", "false") == "true",
        backup_az_enabled=_get_setting(db, "backup_az_enabled", "true") == "true",
        retention_count=int(_get_setting(db, "backup_retention", "5") or "5"),
    )


def _telegram_credentials(db: Session) -> tuple[str, list[str]] | None:
    bot_token = _get_setting(db, "telegram_bot_token")
    chat_ids = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
    if bot_token and chat_ids:
        return bot_token, chat_ids
    return None


def _create_backup_with_optional_telegram(
    db: Session,
    *,
    include_configs: bool,
    include_antizapret_backup: bool,
    send_to_telegram: bool,
    panel_caption_prefix: str,
    az_caption_prefix: str,
) -> dict:
    manager = _get_backup_manager()
    config_contents: dict[str, str] | None = None
    if include_configs:
        adapter = get_active_adapter(db)
        config_contents = {
            fname: adapter.read_config_file(fname)
            for fname in BackupManager.CONFIG_FILES
        }

    result = manager.create_backup(
        include_configs=include_configs,
        config_contents=config_contents,
    )

    send_tg = send_to_telegram or _get_setting(db, "backup_telegram_enabled", "false") == "true"

    tg: tuple[str, str] | None = None
    if send_tg:
        tg = _telegram_credentials(db)
        if send_to_telegram and not tg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите токен бота и chat_id в настройках Telegram",
            )

    if tg:
        bot_token, chat_ids = tg
        archive_path = manager.get_backup_path(result["file_name"])
        for chat_id in chat_ids:
            send_tg_document(
                bot_token,
                chat_id,
                str(archive_path),
                caption=f"{panel_caption_prefix}: {result['file_name']}",
            )

    if include_antizapret_backup:
        try:
            adapter = get_active_adapter(db)
            az_result = adapter.create_antizapret_backup()
            if tg and az_result.get("archive_path"):
                archive_name = az_result.get("archive_name") or Path(az_result["archive_path"]).name
                for chat_id in tg[1]:
                    send_tg_document(
                        tg[0],
                        chat_id,
                        az_result["archive_path"],
                        caption=f"{az_caption_prefix}: {archive_name}",
                    )
        except Exception as exc:
            if send_to_telegram:
                raise
            logger.warning("AntiZapret backup (client.sh 8) failed: %s", exc)

    return result


@router.post("/create", response_model=BackupEntry)
def create_backup(
    payload: BackupCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = _create_backup_with_optional_telegram(
        db,
        include_configs=payload.include_configs,
        include_antizapret_backup=payload.include_antizapret_backup,
        send_to_telegram=payload.send_to_telegram,
        panel_caption_prefix="Бэкап AdminPanelAZ",
        az_caption_prefix="Бэкап AntiZapret",
    )

    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_backup_create",
        subject_name=result["file_name"],
        client_timezone=get_client_timezone_from_request(request),
    )
    return BackupEntry(**result)


@router.post("/upload", response_model=BackupEntry)
async def upload_backup(
    request: Request,
    file: UploadFile = File(...),
    restore: bool = Form(False),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    original_name = os.path.basename(file.filename or "")
    if not original_name.lower().endswith((".tar.gz", ".tgz")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ожидается архив .tar.gz",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл пуст")
    if len(content) > MAX_BACKUP_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Размер архива превышает {MAX_BACKUP_UPLOAD_BYTES // (1024 * 1024)} МБ",
        )

    manager = _get_backup_manager()
    suffix = ".tar.gz" if original_name.lower().endswith(".tar.gz") else ".tgz"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = manager.import_uploaded_backup(tmp_path, original_name=original_name)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        tmp_path.unlink(missing_ok=True)

    if restore:
        manager.restore_backup(result["file_name"])
        if settings.audit_log_enabled:
            log_action(
                db,
                action="backup_restore",
                user_id=admin.id,
                username=admin.username,
                remote_addr=ip_restriction_service.get_client_ip(request),
                details=f"upload:{result['file_name']}",
            )
        admin_notify_service.send_settings_change(
            db,
            actor_username=admin.username,
            settings_key="settings_backup_restore",
            subject_name=result["file_name"],
            client_timezone=get_client_timezone_from_request(request),
        )
    else:
        admin_notify_service.send_settings_change(
            db,
            actor_username=admin.username,
            settings_key="settings_backup_upload",
            subject_name=result["file_name"],
            client_timezone=get_client_timezone_from_request(request),
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
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_backup_restore",
        subject_name=payload.file_name,
        client_timezone=get_client_timezone_from_request(request),
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


@router.post("/test-telegram", status_code=status.HTTP_202_ACCEPTED)
def test_backup_telegram(
    payload: BackupTestTelegramRequest = BackupTestTelegramRequest(),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    bot_token = _get_setting(db, "telegram_bot_token")
    chat_ids = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
    if not bot_token or not chat_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите токен бота и получателей бэкапов в настройках Telegram",
        )

    active = background_task_service.find_active_task("app_backup_test_tg")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Тестовая отправка бэкапа уже выполняется", "active_task_id": active.id},
        )

    include_az = bool(payload.include_antizapret_backup)
    include_configs = bool(payload.include_configs)

    def _task(progress_updater=None):
        from app.database import SessionLocal

        task_db = SessionLocal()
        try:
            if progress_updater:
                progress_updater(10, "Создание архива панели…")
            result = _create_backup_with_optional_telegram(
                task_db,
                include_configs=include_configs,
                include_antizapret_backup=include_az,
                send_to_telegram=True,
                panel_caption_prefix="Тест бэкапа AdminPanelAZ",
                az_caption_prefix="Тест бэкапа AntiZapret",
            )
            if progress_updater:
                progress_updater(100, "Готово")
            az_summary = ""
            if include_az:
                az_summary = "; AZ: включён"
            return {
                "message": f"Бэкап отправлен в Telegram: {result['file_name']}{az_summary}",
                "file_name": result["file_name"],
            }
        finally:
            task_db.close()

    task = background_task_service.enqueue_background_task(
        "app_backup_test_tg",
        _task,
        created_by_username=admin.username,
        queued_message="Создание бэкапа и отправка в Telegram поставлены в очередь",
    )
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_backup_test_telegram",
        subject_name="test_telegram",
    )
    return background_task_service.build_accepted_payload(
        task,
        "Создание бэкапа и отправка в Telegram запущены в фоне.",
    )
