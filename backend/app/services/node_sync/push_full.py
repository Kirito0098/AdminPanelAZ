"""Full push: backup primary → restore all replicas."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Node, NodeSyncGroup, SyncStatus
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import parse_replica_node_ids, validate_sync_group_payload
from app.services.node_sync.verify import verify_sync_group


def _read_backup_bytes(primary_adapter, backup_info: dict[str, str]) -> bytes:
    archive_path = backup_info.get("archive_path") or ""
    archive_name = backup_info.get("archive_name") or os.path.basename(archive_path)
    return primary_adapter.download_antizapret_backup(archive_name)


def run_push_full(
    db: Session,
    group: NodeSyncGroup,
    *,
    progress_callback: Callable[[int, str, str | None], None] | None = None,
    auto_verify: bool = True,
) -> dict[str, Any]:
    def progress(percent: int, stage: str, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(percent, stage, message)

    errors = validate_sync_group_payload(
        db,
        primary_node_id=group.primary_node_id,
        replica_node_ids=parse_replica_node_ids(group.replica_node_ids),
        exclude_group_id=group.id,
    )
    if errors:
        raise RuntimeError("; ".join(errors))

    group.sync_status = SyncStatus.pending
    group.last_sync_error = None
    db.commit()

    progress(10, "Создание бэкапа на primary…")
    primary_node = db.get(Node, group.primary_node_id)
    primary_adapter = get_adapter_for_node(primary_node)
    backup_info = primary_adapter.create_antizapret_backup()

    progress(30, "Чтение архива…")
    archive_bytes = _read_backup_bytes(primary_adapter, backup_info)
    archive_name = backup_info.get("archive_name") or "backup.tar.gz"

    replica_ids = parse_replica_node_ids(group.replica_node_ids)
    restored: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for index, replica_id in enumerate(replica_ids):
        percent = 40 + int((index / max(len(replica_ids), 1)) * 45)
        replica_node = db.get(Node, replica_id)
        replica_name = replica_node.name if replica_node else str(replica_id)
        progress(percent, f"Restore на {replica_name}…")

        replica_adapter = get_adapter_for_node(replica_node)
        try:
            if isinstance(replica_adapter, LocalNodeAdapter):
                with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                    tmp.write(archive_bytes)
                    tmp_path = tmp.name
                try:
                    result = replica_adapter.restore_antizapret_backup(tmp_path)
                finally:
                    os.unlink(tmp_path)
            else:
                result = replica_adapter.restore_antizapret_backup(archive_bytes, archive_name)
            restored.append({"node_id": replica_id, "node_name": replica_name, "result": result})
        except Exception as exc:
            failed.append({"node_id": replica_id, "node_name": replica_name, "error": str(exc)})
            group.sync_status = SyncStatus.failed
            group.last_sync_error = str(exc)
            group.last_sync_at = datetime.utcnow()
            db.commit()
            progress(100, "Push full завершился с ошибкой")
            return {
                "success": False,
                "message": f"Restore failed on {replica_name}: {exc}",
                "backup": backup_info,
                "restored": restored,
                "failed": failed,
            }

    group.sync_status = SyncStatus.synced
    group.last_sync_at = datetime.utcnow()
    group.last_sync_error = None
    db.commit()

    verify_result = None
    if auto_verify:
        progress(90, "Verify после sync…")
        verify_result = verify_sync_group(db, group)

    progress(100, "Push full завершён")
    return {
        "success": True,
        "message": "Полная синхронизация завершена",
        "backup": backup_info,
        "restored": restored,
        "failed": failed,
        "verify": verify_result,
    }
