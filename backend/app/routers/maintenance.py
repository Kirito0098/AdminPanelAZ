import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import GeoIpStatusResponse, MessageResponse, ServiceRestartRequest
from app.services.admin_notify import admin_notify_service
from app.services.background_tasks import assert_heavy_apply_idle, background_task_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.notify_time import get_client_timezone_from_request
from app.services.profile_delivery import load_node_remote_hosts

# Shared setting helpers (canonical location: app.services.app_setting_store)
from app.services.app_setting_store import _get_setting, _set_setting

# Re-exports for telegram bot handlers / tests that still import from this module
from app.routers.settings_reboot import cancel_server_reboot, schedule_server_reboot
from app.routers.settings_telegram import (
    _admin_notify_settings_response,
    _send_test_message_to_recipients,
    _telegram_settings_response,
    register_telegram_webhook,
    test_admin_notify,
    test_telegram,
    unregister_telegram_webhook,
    update_admin_notify_settings,
    update_telegram_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["maintenance"])


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
    assert_heavy_apply_idle(db)

    client_timezone = get_client_timezone_from_request(request)

    def _callable(progress_updater=None):
        from app.database import SessionLocal

        worker_db = SessionLocal()
        try:
            adapter = get_active_adapter(worker_db)
            node = get_active_node(worker_db)
            result = background_task_service.task_run_doall(
                adapter,
                progress_updater,
                hosts=load_node_remote_hosts(worker_db, node.id),
                ensure_openvpn_multihome=bool(node.openvpn_multihome),
            )
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


@router.post("/maintenance/chat-attachments/purge", response_model=MessageResponse)
def purge_chat_attachments(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Убрать ссылки на фото из переписок и очистить кэш превью.

    Сами картинки лежат в Telegram: на сервере хранится только file_id, байты
    скачиваются на просмотр и живут в памяти не дольше минуты.
    """
    from app.models import UserMessage
    from app.services.request_receipt_preview import clear_preview_cache

    cleared = (
        db.query(UserMessage)
        .filter(UserMessage.attachment_file_id.isnot(None))
        .update({UserMessage.attachment_file_id: None}, synchronize_session=False)
    )
    db.commit()
    cached = clear_preview_cache()
    logger.info(
        "chat attachments purged by %s: %s messages, %s cached previews",
        admin.username,
        cleared,
        cached,
    )
    return MessageResponse(message=f"Удалено фото из переписок: {cleared}")


@router.get("/maintenance/geoip-status", response_model=GeoIpStatusResponse)
def geoip_status(_: User = Depends(require_admin)):
    from app.services.ip_geo import get_geoip_status

    return get_geoip_status()


# Backward-compatible public names for bot handlers / older imports.
__all__ = [
    "router",
    "_get_setting",
    "_set_setting",
    "run_doall",
    "restart_service",
    "cancel_server_reboot",
    "schedule_server_reboot",
    "_admin_notify_settings_response",
    "_send_test_message_to_recipients",
    "_telegram_settings_response",
    "update_admin_notify_settings",
    "test_admin_notify",
    "update_telegram_settings",
    "test_telegram",
    "register_telegram_webhook",
    "unregister_telegram_webhook",
    "geoip_status",
]
