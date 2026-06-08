from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
import json

from app.models import DEFAULT_TG_NOTIFY_EVENTS, AppSetting, User
from app.schemas import (
    AdminNotifyEventItem,
    AdminNotifySettingsResponse,
    AdminNotifySettingsUpdate,
    MessageResponse,
    ServiceRestartRequest,
    TelegramSettingsResponse,
    TelegramSettingsUpdate,
)
from app.services.admin_notify import TG_NOTIFY_EVENT_LABELS, admin_notify_service
from app.services.background_tasks import background_task_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.notify_time import get_client_timezone_from_request
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


@router.post("/settings/run-doall", status_code=status.HTTP_202_ACCEPTED)
def run_doall(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    active = background_task_service.find_active_task("run_doall")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "doall.sh уже выполняется",
                "active_task_id": active.id,
            },
        )

    client_timezone = get_client_timezone_from_request(request)

    def _callable(progress_updater=None):
        from app.database import SessionLocal

        worker_db = SessionLocal()
        try:
            adapter = get_active_adapter(worker_db)
            result = background_task_service.task_run_doall(adapter, progress_updater)
            node = get_active_node(worker_db)
            admin_notify_service.send_settings_change(
                worker_db,
                actor_username=admin.username,
                settings_key="settings_run_doall",
                node_id=node.id,
                node_name=node.name,
                client_timezone=client_timezone,
            )
            return result
        finally:
            worker_db.close()

    task = background_task_service.enqueue_background_task(
        "run_doall",
        _callable,
        created_by_username=admin.username,
        queued_message="Запуск doall поставлен в очередь",
    )
    return background_task_service.build_accepted_payload(task, "Скрипт doall запущен в фоне.")


@router.post("/settings/restart-service", response_model=MessageResponse)
def restart_service(
    payload: ServiceRestartRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    output = get_active_adapter(db).restart_service(payload.service_name)
    node = get_active_node(db)
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_restart_service",
        subject_name=payload.service_name,
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )
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


def _admin_notify_settings_response(db: Session, user: User) -> AdminNotifySettingsResponse:
    merged = user.merged_tg_notify_events()
    return AdminNotifySettingsResponse(
        telegram_id=user.telegram_id or "",
        notify_enabled=_get_setting(db, "telegram_notify_enabled", "false") == "true",
        bot_token_set=bool(_get_setting(db, "telegram_bot_token")),
        events=[
            AdminNotifyEventItem(key=key, label=label, enabled=merged.get(key, False))
            for key, label in TG_NOTIFY_EVENT_LABELS
        ],
    )


@router.get("/settings/admin-notify", response_model=AdminNotifySettingsResponse)
def get_admin_notify_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return _admin_notify_settings_response(db, admin)


@router.patch("/settings/admin-notify", response_model=AdminNotifySettingsResponse)
def update_admin_notify_settings(
    payload: AdminNotifySettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.telegram_id is not None:
        tg_id = payload.telegram_id.strip()
        if tg_id:
            existing = db.query(User).filter(User.telegram_id == tg_id, User.id != admin.id).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Этот Telegram ID уже привязан к другому пользователю",
                )
            admin.telegram_id = tg_id
        else:
            admin.telegram_id = None
    if payload.events is not None:
        merged = admin.merged_tg_notify_events()
        for key in DEFAULT_TG_NOTIFY_EVENTS:
            if key in payload.events:
                merged[key] = bool(payload.events[key])
        admin.tg_notify_events = json.dumps(merged)
    db.commit()
    db.refresh(admin)
    return _admin_notify_settings_response(db, admin)


@router.post("/settings/admin-notify/test", response_model=MessageResponse)
def test_admin_notify(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if not admin.telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите Telegram ID в настройках уведомлений")
    bot_token = _get_setting(db, "telegram_bot_token")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    merged = admin.merged_tg_notify_events()
    enabled = [label for key, label in TG_NOTIFY_EVENT_LABELS if merged.get(key)]
    events_text = "\n".join(f"  ✓ {item}" for item in enabled) if enabled else "  (нет включённых событий)"
    text = (
        "🔔 <b>Тест уведомлений AdminPanelAZ</b>\n\n"
        f"Аккаунт: <code>{admin.username}</code>\n\n"
        f"Включённые события:\n{events_text}"
    )
    ok = send_tg_message(bot_token, admin.telegram_id, text, run_async=False)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
    return MessageResponse(message="Тестовое сообщение отправлено")


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
