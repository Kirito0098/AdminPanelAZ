from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import BackgroundTaskResponse
from app.services.background_tasks import background_task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=BackgroundTaskResponse)
def get_task_status(task_id: str, _: User = Depends(require_admin)):
    task = background_task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    payload = background_task_service.serialize_background_task(task)
    payload["success"] = True
    return payload
