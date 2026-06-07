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
) -> None:
    db.add(
        UserActionLog(
            user_id=user_id,
            username=username,
            action=action,
            details=details,
            remote_addr=remote_addr,
        )
    )
    db.commit()
