from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import AppSetting, User
from app.schemas import MessageResponse, ServiceRestartRequest, TelegramSettingsResponse, TelegramSettingsUpdate
from app.services.node_manager import get_active_adapter
from app.services.telegram import send_tg_message

router = APIRouter(tags=["maintenance"])


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


@router.post("/settings/run-doall", response_model=MessageResponse)
def run_doall(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    output = get_active_adapter(db).apply_config_changes()
    return MessageResponse(message="doall.sh выполнен", detail=output)


@router.post("/settings/restart-service", response_model=MessageResponse)
def restart_service(
    payload: ServiceRestartRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    output = get_active_adapter(db).restart_service(payload.service_name)
    return MessageResponse(message=f"Служба {payload.service_name} перезапущена", detail=output)


@router.get("/settings/telegram", response_model=TelegramSettingsResponse)
def get_telegram_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return TelegramSettingsResponse(
        bot_token_set=bool(_get_setting(db, "telegram_bot_token")),
        chat_id=_get_setting(db, "telegram_chat_id"),
        notify_on_backup=_get_setting(db, "backup_telegram_enabled", "false") == "true",
        notify_enabled=_get_setting(db, "telegram_notify_enabled", "false") == "true",
    )


@router.patch("/settings/telegram", response_model=TelegramSettingsResponse)
def update_telegram_settings(
    payload: TelegramSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if payload.bot_token is not None:
        _set_setting(db, "telegram_bot_token", payload.bot_token.strip())
    if payload.chat_id is not None:
        _set_setting(db, "telegram_chat_id", payload.chat_id.strip())
    if payload.notify_enabled is not None:
        _set_setting(db, "telegram_notify_enabled", "true" if payload.notify_enabled else "false")
    if payload.notify_on_backup is not None:
        _set_setting(db, "backup_telegram_enabled", "true" if payload.notify_on_backup else "false")
    db.commit()
    return TelegramSettingsResponse(
        bot_token_set=bool(_get_setting(db, "telegram_bot_token")),
        chat_id=_get_setting(db, "telegram_chat_id"),
        notify_on_backup=_get_setting(db, "backup_telegram_enabled", "false") == "true",
        notify_enabled=_get_setting(db, "telegram_notify_enabled", "false") == "true",
    )


@router.post("/settings/telegram/test", response_model=MessageResponse)
def test_telegram(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    bot_token = _get_setting(db, "telegram_bot_token")
    chat_id = _get_setting(db, "telegram_chat_id")
    if not bot_token or not chat_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите токен бота и chat_id")
    ok = send_tg_message(
        bot_token,
        chat_id,
        "✅ <b>AdminPanelAZ</b>: тестовое уведомление Telegram",
        run_async=False,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
    return MessageResponse(message="Тестовое сообщение отправлено")
