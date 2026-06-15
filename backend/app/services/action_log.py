from sqlalchemy.orm import Session

from app.models import UserActionLog


def log_action(
    db: Session,
    *,
    action: str,
    user_id: int | None = None,
    username: str | None = None,
    details: str | None = None,
    remote_addr: str | None = None,
) -> UserActionLog | None:
    row = UserActionLog(
        user_id=user_id,
        username=username,
        action=action,
        details=details,
        remote_addr=remote_addr,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        from app.services.audit_stream import audit_stream_service
        from app.services.event_webhooks import event_webhook_service

        event_webhook_service.dispatch_after_log(row, db=db)
        audit_stream_service.dispatch_after_log(row, db=db)
    except Exception:
        pass
    return row
