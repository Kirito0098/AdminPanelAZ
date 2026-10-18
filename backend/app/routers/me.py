"""Самосервис плана конфигов текущего пользователя: ``/api/me/plan-configs``.

Административный ``/api/users/{user_id}/provisioning/configs`` игнорирует квоту;
самообслуживание — нет (D3 квота по именам плана + лимит создания).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, UserNodeAssignment, UserRole
from app.schemas import UserProvisionedResponse
from app.services.self_service import enforce_user_can_create_config
from app.services.user_provisioning import (
    enqueue_user_provision,
    plan_add_index,
    plan_remove_index,
)

router = APIRouter(prefix="/me", tags=["me"])


def _user_summary(user: User, node_ids: list[int]) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "client_base_name": user.client_base_name,
        "plan_config_indexes": [int(item) for item in json.loads(user.plan_config_indexes or "[]")],
        "desired_protocols": [str(item) for item in json.loads(user.desired_protocols or "[]")],
        "panel_login_enabled": user.panel_login_enabled,
        "provision_state": user.provision_state,
        "access_until": user.access_until,
        "node_ids": list(node_ids),
        "config_quota": user.config_quota,
    }


@router.post("/plan-configs")
def add_me_plan_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Добавить в свой план самое свободное имя (индекс 1..20) и поставить задачу применения."""
    user = db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if not user.client_base_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="У пользователя нет плана конфигов"
        )
    # Админ добавляет без квоты; самосервис — с квотой D3 и лимитом создания.
    if current_user.role != UserRole.admin:
        enforce_user_can_create_config(db, current_user)

    free = plan_add_index(db, user)
    task = enqueue_user_provision(
        db,
        user_id=user.id,
        actor_username=current_user.username,
        confirm_deletions=False,
    )
    db.refresh(user)
    assignments = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    return {
        "index": free,
        "task_id": task.id,
        "user": _user_summary(user, [row.node_id for row in assignments]),
    }


@router.delete("/plan-configs/{index}")
def remove_me_plan_config(
    index: int,
    confirm_deletions: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалить имя плана по индексу. Требуется ``can_manage_configs``.

    Последнее имя → 409 ``last_config_name``; удаления без ``confirm_deletions`` → 409 ``confirm_deletions``.
    """
    user = db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if not user.client_base_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="У пользователя нет плана конфигов"
        )
    if not (
        current_user.role == UserRole.admin or bool(current_user.can_manage_configs)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для управления конфигами"
        )

    plan_remove_index(db, user, index, confirm_deletions=confirm_deletions)
    task = enqueue_user_provision(
        db,
        user_id=user.id,
        actor_username=current_user.username,
        confirm_deletions=confirm_deletions,
    )
    db.refresh(user)
    assignments = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    return UserProvisionedResponse(
        user=_user_summary(user, [row.node_id for row in assignments]), task_id=task.id
    )
