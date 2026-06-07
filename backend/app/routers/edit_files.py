from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole
from app.schemas import MessageResponse
from app.services.file_editor import FileEditorService
from app.services.node_manager import get_active_adapter

router = APIRouter(prefix="/edit-files", tags=["edit-files"])
settings = get_settings()


class FileContentUpdate(BaseModel):
    content: str = ""


class BatchUpdate(BaseModel):
    files: dict[str, str] = {}
    run_doall: bool = True


@router.get("")
def list_edit_files(current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.viewer:
        raise HTTPException(status_code=403, detail="Просмотр файлов недоступен для роли viewer")
    return FileEditorService().list_files()


@router.get("/{file_key}")
def read_edit_file(file_key: str, current_user: User = Depends(get_current_user)):
    if current_user.role not in (UserRole.admin, UserRole.user):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    try:
        return {"key": file_key, "content": FileEditorService().read_file(file_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{file_key}")
def save_edit_file(
    file_key: str,
    payload: FileContentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    editor = FileEditorService()
    try:
        editor.write_file(file_key, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        output = get_active_adapter(db).apply_config_changes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Файл сохранён, но doall.sh ошибка: {exc}") from exc
    return MessageResponse(message="Файл сохранён и применён", detail=output)


@router.post("/batch", response_model=MessageResponse)
def save_batch(
    payload: BatchUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    editor = FileEditorService()
    for key, content in payload.files.items():
        editor.write_file(key, content)
    output = None
    if payload.run_doall:
        output = get_active_adapter(db).apply_config_changes()
    return MessageResponse(message="Файлы сохранены", detail=output)
