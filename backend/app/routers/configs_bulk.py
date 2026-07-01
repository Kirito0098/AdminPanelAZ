from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import BulkConfigOpQueuedResponse, BulkConfigOpRequest
from app.services.bulk_config_ops import enqueue_bulk_config_op
from app.services.node_sync.groups import require_ha_primary_for_client_ops

router = APIRouter(prefix="/configs/bulk", tags=["configs"])


@router.post("", response_model=BulkConfigOpQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
def bulk_config_operation(
    payload: BulkConfigOpRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not payload.config_ids and not payload.tag_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите config_ids или tag_ids",
        )
    require_ha_primary_for_client_ops(db)
    try:
        task_id = enqueue_bulk_config_op(
            db,
            operation=payload.operation,
            config_ids=payload.config_ids,
            tag_ids=payload.tag_ids,
            block_days=payload.block_days or 7,
            renew_cert_days=payload.renew_cert_days or 3650,
            owner_id=payload.owner_id,
            actor=admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return BulkConfigOpQueuedResponse(
        task_id=task_id,
        status_url=f"/api/tasks/{task_id}",
    )
