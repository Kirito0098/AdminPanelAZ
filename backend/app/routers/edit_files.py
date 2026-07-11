from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User, UserRole
from app.schemas import MessageResponse
from app.services.action_log import log_action
from app.services.edit_files_transfer import run_edit_files_transfer
from app.services.file_editor import EDITABLE_FILES, FileEditorService
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.config_sync import maybe_replicate_config_files
from app.services.node_sync.groups import require_ha_primary_for_config_ops

router = APIRouter(prefix="/edit-files", tags=["edit-files"])


class FileContentUpdate(BaseModel):
    content: str = ""


class BatchUpdate(BaseModel):
    files: dict[str, str] = {}
    run_doall: bool = True


class TransferRequest(BaseModel):
    file_keys: list[str] = Field(min_length=1)
    target_node_ids: list[int] | None = None
    all_online: bool = False
    source_node_id: int | None = None
    run_doall: bool = False
    content_overrides: dict[str, str] | None = None


def _filename_for_key(file_key: str) -> str:
    fname = EDITABLE_FILES.get(file_key)
    if not fname:
        raise ValueError("Неизвестный файл")
    return fname


@router.get("")
def list_edit_files(current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.viewer:
        raise HTTPException(status_code=403, detail="Просмотр файлов недоступен для роли viewer")
    return FileEditorService().list_files()


@router.get("/{file_key}")
def read_edit_file(file_key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in (UserRole.admin, UserRole.user):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    try:
        adapter = get_active_adapter(db)
        content = adapter.read_config_file(_filename_for_key(file_key))
        return {"key": file_key, "content": content}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{file_key}")
def save_edit_file(
    file_key: str,
    payload: FileContentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        adapter = get_active_adapter(db)
        adapter.write_config_file(_filename_for_key(file_key), payload.content)
        output = adapter.apply_config_changes()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Файл сохранён, но doall.sh ошибка: {exc}") from exc
    maybe_replicate_config_files(
        db,
        node_id=get_active_node(db).id,
        file_keys=[file_key],
        run_doall=True,
        content_overrides={file_key: payload.content},
    )
    return MessageResponse(message="Файл сохранён и применён", detail=output)


@router.post("/batch", response_model=MessageResponse)
def save_batch(
    payload: BatchUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    adapter = get_active_adapter(db)
    for key, content in payload.files.items():
        adapter.write_config_file(_filename_for_key(key), content)
    output = None
    if payload.run_doall:
        output = adapter.apply_config_changes()
    maybe_replicate_config_files(
        db,
        node_id=get_active_node(db).id,
        file_keys=list(payload.files.keys()),
        run_doall=payload.run_doall,
        content_overrides=dict(payload.files),
    )
    return MessageResponse(message="Файлы сохранены", detail=output)


@router.post("/transfer")
def transfer_edit_files(
    payload: TransferRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        result = run_edit_files_transfer(
            db,
            file_keys=payload.file_keys,
            target_node_ids=payload.target_node_ids,
            all_online=payload.all_online,
            source_node_id=payload.source_node_id,
            run_doall=payload.run_doall,
            content_overrides=payload.content_overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_action(
        db,
        action="edit_files_transfer",
        user_id=user.id,
        username=user.username,
        details=(
            f"from={result['source_node_name']};files={','.join(result['files'])};"
            f"success={result['nodes_success']};failed={result['nodes_failed']};"
            f"doall={payload.run_doall}"
        ),
    )
    return result
