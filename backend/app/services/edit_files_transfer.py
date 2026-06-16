"""Transfer AntiZapret config files from one node to others."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Node
from app.services.cidr.pipeline.orchestrator import resolve_deploy_targets
from app.services.file_editor import EDITABLE_FILES
from app.services.node_manager import get_active_node, get_adapter_for_node

logger = logging.getLogger(__name__)


def _validate_file_keys(file_keys: list[str]) -> list[str]:
    if not file_keys:
        raise ValueError("Укажите хотя бы один файл")
    unique = list(dict.fromkeys(file_keys))
    for key in unique:
        if key not in EDITABLE_FILES:
            raise ValueError(f"Неизвестный файл: {key}")
    return unique


def _resolve_source_node(db: Session, source_node_id: int | None) -> Node:
    if source_node_id is None:
        return get_active_node(db)
    node = db.query(Node).filter(Node.id == source_node_id).first()
    if not node:
        raise ValueError(f"Исходный узел {source_node_id} не найден")
    return node


def _load_file_contents(
    source_adapter,
    file_keys: list[str],
    content_overrides: dict[str, str] | None,
) -> dict[str, str]:
    contents: dict[str, str] = {}
    for key in file_keys:
        if content_overrides and key in content_overrides:
            contents[key] = content_overrides[key]
            continue
        fname = EDITABLE_FILES[key]
        contents[key] = source_adapter.read_config_file(fname)
    return contents


def run_edit_files_transfer(
    db: Session,
    *,
    file_keys: list[str],
    target_node_ids: list[int] | None = None,
    all_online: bool = False,
    source_node_id: int | None = None,
    run_doall: bool = False,
    content_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Copy config file(s) from source node to one or more target nodes."""
    validated_keys = _validate_file_keys(file_keys)
    source = _resolve_source_node(db, source_node_id)

    try:
        source_adapter = get_adapter_for_node(source)
    except Exception as exc:
        raise ValueError(f"Не удалось подключиться к исходному узлу «{source.name}»: {exc}") from exc

    contents = _load_file_contents(source_adapter, validated_keys, content_overrides)

    if all_online:
        nodes, skipped = resolve_deploy_targets(db, all_online=True)
    elif target_node_ids:
        nodes, skipped = resolve_deploy_targets(db, target_node_ids=target_node_ids)
    else:
        raise ValueError("Укажите целевые узлы или включите «все online»")

    per_node: list[dict[str, Any]] = list(skipped)
    nodes_success = 0
    nodes_failed = 0
    nodes_skipped = len(skipped)
    total_transferred = 0

    for node in nodes:
        if node.id == source.id:
            per_node.append(
                {
                    "node_id": node.id,
                    "node_name": node.name,
                    "status": "skipped",
                    "transferred_files": [],
                    "failed": [],
                    "error": "Совпадает с исходным узлом",
                }
            )
            nodes_skipped += 1
            continue

        try:
            adapter = get_adapter_for_node(node)
        except Exception as exc:
            per_node.append(
                {
                    "node_id": node.id,
                    "node_name": node.name,
                    "status": "failed",
                    "transferred_files": [],
                    "failed": [{"file": "*", "error": str(exc)}],
                    "error": str(exc),
                }
            )
            nodes_failed += 1
            continue

        transferred: list[str] = []
        failed: list[dict[str, str]] = []
        for key in validated_keys:
            fname = EDITABLE_FILES[key]
            try:
                adapter.write_config_file(fname, contents[key])
                transferred.append(fname)
            except Exception as exc:
                failed.append({"file": fname, "error": str(exc)})

        if failed:
            per_node.append(
                {
                    "node_id": node.id,
                    "node_name": node.name,
                    "status": "failed",
                    "transferred_files": transferred,
                    "failed": failed,
                    "error": failed[0]["error"],
                }
            )
            nodes_failed += 1
            continue

        doall_output = None
        if run_doall:
            try:
                doall_output = adapter.apply_config_changes()
            except Exception as exc:
                per_node.append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "status": "failed",
                        "transferred_files": transferred,
                        "failed": [{"file": "*", "error": str(exc)}],
                        "error": f"Файлы записаны, но doall.sh ошибка: {exc}",
                    }
                )
                nodes_failed += 1
                continue

        per_node.append(
            {
                "node_id": node.id,
                "node_name": node.name,
                "status": "success",
                "transferred_files": transferred,
                "failed": [],
                "doall_output": doall_output,
            }
        )
        nodes_success += 1
        total_transferred += len(transferred)

    filenames = [EDITABLE_FILES[key] for key in validated_keys]
    if nodes_success and not nodes_failed:
        message = f"Перенесено {len(filenames)} файл(ов) на {nodes_success} узел(ов)"
    elif nodes_success:
        message = f"Частичный успех: {nodes_success} узел(ов), ошибок: {nodes_failed}"
    elif nodes_skipped and not nodes_failed:
        message = "Нет подходящих целевых узлов (все пропущены или offline)"
    else:
        message = "Перенос не выполнен"

    return {
        "success": nodes_success > 0 and nodes_failed == 0,
        "message": message,
        "source_node_id": source.id,
        "source_node_name": source.name,
        "files": filenames,
        "file_keys": validated_keys,
        "run_doall": run_doall,
        "nodes_success": nodes_success,
        "nodes_failed": nodes_failed,
        "nodes_skipped": nodes_skipped,
        "total_transferred": total_transferred,
        "per_node": per_node,
    }
