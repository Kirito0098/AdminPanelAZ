"""File-based CIDR update pipeline (download providers)."""
import os
import shutil
from datetime import datetime, timezone

from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.constants import RUNTIME_BACKUP_RETENTION_SECONDS
from app.services.cidr.pipeline.facade_compat import get_attr as _cfg

def _snapshot_baseline_if_missing():
    os.makedirs(_cfg("BASELINE_DIR"), exist_ok=True)
    for file_name in IP_FILES.keys():
        source_path = os.path.join(_cfg("LIST_DIR"), file_name)
        target_path = os.path.join(_cfg("BASELINE_DIR"), file_name)
        if os.path.exists(target_path):
            continue
        if os.path.exists(source_path):
            shutil.copyfile(source_path, target_path)

def _make_runtime_backup(files):
    _prune_runtime_backups()

    backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = os.path.join(_cfg("RUNTIME_BACKUP_ROOT"), backup_stamp)
    os.makedirs(backup_dir, exist_ok=True)

    copied = []
    for file_name in files:
        source_path = os.path.join(_cfg("LIST_DIR"), file_name)
        if not os.path.exists(source_path):
            continue
        shutil.copyfile(source_path, os.path.join(backup_dir, file_name))
        copied.append(file_name)

    return backup_dir, copied

def _prune_runtime_backups(now_ts=None, retention_seconds=RUNTIME_BACKUP_RETENTION_SECONDS):
    if retention_seconds <= 0:
        return []

    os.makedirs(_cfg("RUNTIME_BACKUP_ROOT"), exist_ok=True)

    current_ts = float(now_ts) if now_ts is not None else datetime.now(timezone.utc).timestamp()
    cutoff_ts = current_ts - float(retention_seconds)
    removed_dirs = []

    for entry_name in os.listdir(_cfg("RUNTIME_BACKUP_ROOT")):
        entry_path = os.path.join(_cfg("RUNTIME_BACKUP_ROOT"), entry_name)
        if not os.path.isdir(entry_path):
            continue

        try:
            if os.path.getmtime(entry_path) > cutoff_ts:
                continue
            shutil.rmtree(entry_path)
            removed_dirs.append(entry_name)
        except OSError:
            continue

    return removed_dirs

def _emit_progress(progress_callback, percent, stage):
    if progress_callback is None:
        return
    try:
        safe_percent = max(0, min(100, int(percent)))
    except (TypeError, ValueError):
        safe_percent = 0

    text = str(stage or "").strip() or "Выполняется операция"
    progress_callback(safe_percent, text)

def list_runtime_backups() -> list[dict]:
    """List available runtime backup stamps (newest first)."""
    root = _cfg("RUNTIME_BACKUP_ROOT")
    if not os.path.isdir(root):
        return []

    backups: list[dict] = []
    for entry_name in os.listdir(root):
        entry_path = os.path.join(root, entry_name)
        if not os.path.isdir(entry_path):
            continue
        files = sorted(
            name
            for name in os.listdir(entry_path)
            if name in IP_FILES and os.path.isfile(os.path.join(entry_path, name))
        )
        if not files:
            continue
        try:
            mtime = os.path.getmtime(entry_path)
        except OSError:
            mtime = 0.0
        backups.append(
            {
                "stamp": entry_name,
                "files": files,
                "file_count": len(files),
                "mtime": mtime,
            }
        )

    backups.sort(key=lambda item: item["mtime"], reverse=True)
    return backups

def rollback_from_runtime_backup(
    backup_stamp: str,
    selected_files=None,
    progress_callback=None,
):
    """Restore controller LIST_DIR files from a runtime_backups stamp."""
    _emit_progress(progress_callback, 3, "Подготовка к откату из runtime_backups")

    if not backup_stamp or not str(backup_stamp).strip():
        _emit_progress(progress_callback, 100, "Откат завершен")
        return {
            "success": False,
            "message": "Не указан stamp резервной копии",
            "restored": [],
            "missing": [],
            "backup_stamp": backup_stamp,
        }

    safe_stamp = os.path.basename(str(backup_stamp).strip())
    backup_dir = os.path.join(_cfg("RUNTIME_BACKUP_ROOT"), safe_stamp)
    if not os.path.isdir(backup_dir):
        _emit_progress(progress_callback, 100, "Откат завершен")
        return {
            "success": False,
            "message": f"Резервная копия {safe_stamp} не найдена",
            "restored": [],
            "missing": [],
            "backup_stamp": safe_stamp,
        }

    available = sorted(
        name
        for name in os.listdir(backup_dir)
        if name in IP_FILES and os.path.isfile(os.path.join(backup_dir, name))
    )
    if not available:
        _emit_progress(progress_callback, 100, "Откат завершен")
        return {
            "success": False,
            "message": f"В резервной копии {safe_stamp} нет CIDR-файлов",
            "restored": [],
            "missing": [],
            "backup_stamp": safe_stamp,
        }

    requested = selected_files or available
    normalized = [name for name in requested if name in IP_FILES and name in available]
    if not normalized:
        normalized = available

    restored = []
    missing = []
    total_files = len(normalized)
    for index, file_name in enumerate(normalized, start=1):
        progress_start = 8 + int(((index - 1) / max(total_files, 1)) * 90)
        _emit_progress(progress_callback, progress_start, f"Восстановление {file_name}")

        source_path = os.path.join(backup_dir, file_name)
        target_path = os.path.join(_cfg("LIST_DIR"), file_name)
        if not os.path.isfile(source_path):
            missing.append(file_name)
            continue
        shutil.copyfile(source_path, target_path)
        restored.append(file_name)

    success = bool(restored)
    if restored and missing:
        message = "Откат из runtime_backups выполнен частично"
    elif restored:
        message = f"Восстановлено {len(restored)} файл(ов) из {safe_stamp}"
    else:
        message = "Не удалось восстановить файлы из runtime_backups"

    _emit_progress(progress_callback, 100, "Откат CIDR-файлов завершен")
    return {
        "success": success,
        "message": message,
        "restored": restored,
        "missing": missing,
        "backup_stamp": safe_stamp,
        "backup_dir": backup_dir,
        "backup_files": available,
    }

