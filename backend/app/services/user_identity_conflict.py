"""HTTP conflicts when a username or base name is held by a user still being deleted."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User
from app.services.user_provisioning import enqueue_user_delete_cleanup


def pending_deletion_conflict(
    db: Session, user: User, actor: User, *, what: str
) -> HTTPException:
    """User row still deleting: re-enqueue cleanup instead of «already exists»."""
    enqueue_user_delete_cleanup(db, user_id=user.id, actor_username=actor.username)
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "user_deletion_pending",
            "message": (
                f"{what} занято пользователем {user.username}, который ещё удаляется — "
                "очистка перезапущена, повторите через несколько секунд"
            ),
        },
    )
