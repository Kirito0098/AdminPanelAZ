from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Node, NodeStatus, User
from app.schemas import (
    ServerRebootPendingItem,
    ServerRebootPendingResponse,
    ServerRebootRequest,
    ServerRebootScheduleResponse,
)
from app.services.admin_notify import admin_notify_service
from app.services.action_log import log_action
from app.services.node_manager import _is_vpn_node, get_adapter_for_node
from app.services.notify_time import get_client_timezone_from_request
from app.services.server_reboot import (
    CONFIRM_PHRASE,
    DELAY_SECONDS,
    PendingReboot,
    RebootError,
    cancel_reboot,
    list_pending,
    schedule_reboot,
)

router = APIRouter(tags=["maintenance"])


def _reboot_node_warning(node: Node) -> str | None:
    if node.status in (NodeStatus.offline, NodeStatus.unknown):
        return "Узел offline или недоступен — перезагрузка может не выполниться"
    return None


def _pending_reboot_item(pending: PendingReboot, *, warning: str | None = None) -> ServerRebootPendingItem:
    delay_seconds = max(0, int((pending.execute_at - pending.created_at).total_seconds()))
    return ServerRebootPendingItem(
        reboot_id=pending.reboot_id,
        node_id=pending.node_id,
        node_name=pending.node_name,
        scheduled_by=pending.scheduled_by,
        created_at=pending.created_at,
        execute_at=pending.execute_at,
        delay_seconds=delay_seconds or DELAY_SECONDS,
        warning=warning,
    )


@router.post("/settings/reboot", response_model=ServerRebootScheduleResponse)
def schedule_server_reboot(
    payload: ServerRebootRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.confirm != CONFIRM_PHRASE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите REBOOT для подтверждения")

    node = db.query(Node).filter(Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Узел не найден")

    if not _is_vpn_node(node):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Перезагрузка доступна только для VPN-узлов",
        )

    warning = _reboot_node_warning(node)
    client_timezone = get_client_timezone_from_request(request)

    def _execute(pending: PendingReboot) -> None:
        from app.database import SessionLocal
        from app.services.ip_restriction import ip_restriction_service

        worker_db = SessionLocal()
        output: str | None = None
        failure: str | None = None
        try:
            worker_node = worker_db.query(Node).filter(Node.id == pending.node_id).first()
            if not worker_node:
                raise RuntimeError("node missing")
            adapter = get_adapter_for_node(worker_node)
            output = adapter.reboot()
        except Exception as exc:
            failure = str(exc) or exc.__class__.__name__
            raise
        finally:
            try:
                if failure is not None:
                    details = (
                        f"node_id={pending.node_id} node={pending.node_name} "
                        f"status=failed error={failure}"
                    )
                    subject_name = f"{pending.node_name} (ошибка)"
                else:
                    details = (
                        f"node_id={pending.node_id} node={pending.node_name} "
                        f"status=success output={output}"
                    )
                    subject_name = pending.node_name
                log_action(
                    worker_db,
                    action="settings_reboot_execute",
                    user_id=admin.id,
                    username=admin.username,
                    details=details,
                )
                admin_notify_service.send_settings_change(
                    worker_db,
                    actor_username=admin.username,
                    settings_key="settings_reboot_execute",
                    subject_name=subject_name,
                    details=details,
                    node_id=pending.node_id,
                    node_name=pending.node_name,
                )
            finally:
                worker_db.close()

    try:
        pending = schedule_reboot(
            node_id=node.id,
            node_name=node.name,
            scheduled_by=admin.username,
            execute_fn=_execute,
        )
    except RebootError as exc:
        code = status.HTTP_409_CONFLICT if exc.code == "duplicate_pending" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=exc.message) from exc

    from app.services.ip_restriction import ip_restriction_service

    log_action(
        db,
        action="settings_reboot_schedule",
        user_id=admin.id,
        username=admin.username,
        remote_addr=ip_restriction_service.get_client_ip(request),
        details=f"node_id={node.id} node={node.name} reboot_id={pending.reboot_id}",
    )
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_reboot_schedule",
        subject_name=node.name,
        node_id=node.id,
        node_name=node.name,
        client_timezone=client_timezone,
    )
    item = _pending_reboot_item(pending, warning=warning)
    return ServerRebootScheduleResponse(**item.model_dump())


@router.get("/settings/reboot/pending", response_model=ServerRebootPendingResponse)
def list_server_reboots_pending(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    items = []
    for pending in list_pending():
        node = db.query(Node).filter(Node.id == pending.node_id).first()
        warning = _reboot_node_warning(node) if node else None
        items.append(_pending_reboot_item(pending, warning=warning))
    return ServerRebootPendingResponse(items=items)


@router.post("/settings/reboot/{reboot_id}/cancel", response_model=ServerRebootPendingItem)
def cancel_server_reboot(
    reboot_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        pending = cancel_reboot(reboot_id)
    except RebootError as exc:
        if exc.code == "not_found":
            code = status.HTTP_404_NOT_FOUND
        elif exc.code == "not_cancellable":
            code = status.HTTP_409_CONFLICT
        else:
            code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=exc.message) from exc

    from app.services.ip_restriction import ip_restriction_service

    log_action(
        db,
        action="settings_reboot_cancel",
        user_id=admin.id,
        username=admin.username,
        remote_addr=ip_restriction_service.get_client_ip(request),
        details=f"node_id={pending.node_id} node={pending.node_name} reboot_id={pending.reboot_id}",
    )
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_reboot_cancel",
        subject_name=pending.node_name,
        node_id=pending.node_id,
        node_name=pending.node_name,
        client_timezone=get_client_timezone_from_request(request),
    )
    return _pending_reboot_item(pending)
