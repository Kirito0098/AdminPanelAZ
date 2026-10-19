"""User access extension hook (Stage 3, Task 7).

``compute_extended_access_until`` implements the shared ``max(now, current) + days``
arithmetic (admin ``+N``, unlock redeem, provisioning presets).

``on_user_access_extended`` runs after any successful extension:
1) ``traffic_counter_reset_at = now`` and the ``user_traffic_limit`` block/lift is
   cleared;
2) if the user has a plan and ``provision_state != "ok"``, a creations-only
   ``user_provision`` task is enqueued (missing configs are recreated);
3) an owner Telegram note: redownload when configs are/will be re-created, else a
   plain extension message.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User
from app.services.app_setting_store import _get_setting
from app.services.feature_guards import get_feature_service
from app.services.shared_helpers import as_utc as _as_utc
from app.services.telegram import send_tg_message
from app.services.user_blocks import lift_user_block

logger = logging.getLogger(__name__)


def compute_extended_access_until(
    current: datetime | None, days: int, *, now: datetime | None = None
) -> datetime:
    """max(now, current) + days in UTC. ``current=None`` extends from now."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cur = _as_utc(current)
    base = max(now, cur) if cur is not None else now
    return base + timedelta(days=int(days))


def on_user_access_extended(
    db: Session,
    user: User,
    *,
    actor: str,
    previous_access_until: datetime | None,
    configs_were_kept: bool,
) -> dict:
    """Reset traffic, lift user_traffic_limit, auto-apply creations, notify owner."""
    logger.info(
        "access extended user_id=%s actor=%s previous_access_until=%s",
        user.id, actor, previous_access_until,
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user.traffic_counter_reset_at = now
    task = None
    if user.traffic_limit_blocked:
        user.traffic_limit_blocked = False
        db.add(user)
        db.flush()
        lift_user_block(db, user, "user_traffic_limit", actor=actor)
    db.commit()

    has_plan = bool(user.client_base_name) and get_feature_service().is_enabled("user_provisioning")
    if has_plan and user.provision_state != "ok":
        from app.services.user_provisioning import enqueue_user_provision

        task = enqueue_user_provision(
            db, user_id=user.id, actor_username=actor, confirm_deletions=False, creations_only=True
        )

    if user.telegram_id:
        bot_token = _get_setting(db, "telegram_bot_token")
        if bot_token:
            if not configs_were_kept or task is not None:
                text = (
                    "Доступ продлён. Конфиги выпущены заново — скачайте их и "
                    "замените старые на устройствах."
                )
            else:
                text = "Доступ продлён."
            send_tg_message(bot_token, str(user.telegram_id), text)

    return {"task_id": getattr(task, "id", None)}
