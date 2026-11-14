from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import MessageResponse
from app.services.action_log import log_action
from app.services.config_apply_queue import enqueue_doall_and_replicate
from app.services.edit_files_transfer import run_edit_files_transfer
from app.services.file_editor import EDITABLE_FILES, FileEditorService, is_kresd_custom_key
from app.services.node_manager import get_active_adapter, get_active_node
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
def list_edit_files(_: User = Depends(require_admin)):
    return FileEditorService().list_files()


@router.get("/{file_key}")
def read_edit_file(file_key: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
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
    node = get_active_node(db)
    if is_kresd_custom_key(file_key):
        adapter = get_active_adapter(db)
        adapter.write_config_file(EDITABLE_FILES[file_key], payload.content)
        task = enqueue_doall_and_replicate(
            node_id=node.id,
            file_keys=[file_key],
            content_overrides={file_key: payload.content},
            created_by_username=current_user.username,
            run_doall=False,
            run_replicate=True,
            queued_message="DNS-файл сохранён — HA-репликация в фоне…",
        )
        return MessageResponse(
            message="Файл сохранён, DNS-резолвер перезапущен; HA в фоне",
            task_id=task.id,
        )
    try:
        adapter = get_active_adapter(db)
        adapter.write_config_file(_filename_for_key(file_key), payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить файл: {exc}") from exc

    task = enqueue_doall_and_replicate(
        node_id=node.id,
        file_keys=[file_key],
        content_overrides={file_key: payload.content},
        created_by_username=current_user.username,
        run_doall=True,
        run_replicate=True,
        queued_message="Файл сохранён — doall в фоне…",
    )
    return MessageResponse(
        message="Файл сохранён, применение (doall) запущено в фоне",
        task_id=task.id,
    )


@router.post("/batch", response_model=MessageResponse)
def save_batch(
    payload: BatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    require_ha_primary_for_config_ops(db)
    try:
        filenames = {key: _filename_for_key(key) for key in payload.files}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    adapter = get_active_adapter(db)
    for key, content in payload.files.items():
        adapter.write_config_file(filenames[key], content)
    run_doall = payload.run_doall and any(not is_kresd_custom_key(key) for key in payload.files)
    node = get_active_node(db)
    task = enqueue_doall_and_replicate(
        node_id=node.id,
        file_keys=list(payload.files.keys()),
        content_overrides=dict(payload.files),
        created_by_username=current_user.username,
        run_doall=run_doall,
        run_replicate=True,
        queued_message=(
            "Файлы сохранены — doall в фоне…"
            if run_doall
            else "Файлы сохранены — HA-репликация в фоне…"
        ),
    )
    return MessageResponse(
        message="Файлы сохранены" + (", применение в фоне" if run_doall else ""),
        task_id=task.id,
    )


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
