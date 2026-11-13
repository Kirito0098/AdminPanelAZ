"""Deploy preview: diff controller artifacts vs node provider files (no apply)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node
from app.services.cidr.ip_manager import masked_include_name
from app.services.cidr.pipeline.deploy import (
    _artifact_path,
    _count_cidr_lines,
    _list_artifact_filenames,
    _normalize_filenames,
)
from app.services.cidr.pipeline.orchestrator import resolve_deploy_targets
from app.services.node_manager import get_adapter_for_node, node_metadata_dict

ANTIZAPRET_PATH = str(get_settings().antizapret_path)

logger = logging.getLogger(__name__)

INCLUDE_IN_SYNC = "in_sync"
INCLUDE_STALE = "stale"
INCLUDE_NOT_ENABLED = "not_enabled"
INCLUDE_UNKNOWN = "unknown"


def _route_lines(content: str) -> set[str]:
    lines: set[str] = set()
    for raw in content.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.add(stripped)
    return lines


def _diff_stats(controller_content: str, node_content: str) -> dict[str, int | bool]:
    controller_lines = _route_lines(controller_content)
    node_lines = _route_lines(node_content)
    added = len(controller_lines - node_lines)
    removed = len(node_lines - controller_lines)
    unchanged = len(controller_lines & node_lines)
    return {
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "changed": added > 0 or removed > 0,
    }


def _read_controller_content(filename: str) -> tuple[str, int]:
    path = _artifact_path(filename)
    if path is None or not os.path.isfile(path):
        return "", 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    return content, _count_cidr_lines(path)


def _local_config_dir(node: Node) -> Path:
    """Local adapter base path: node metadata wins over panel settings."""
    raw = node_metadata_dict(node).get("antizapret_path")
    return Path(str(raw) if raw else ANTIZAPRET_PATH) / "config"


def _local_include_entry(
    filename: str, controller_content: str, config_dir: Path
) -> dict[str, Any]:
    """Compare the controller list with the local node's AP include file."""
    include_name = masked_include_name(filename)
    entry: dict[str, Any] = {"include_file": include_name, "include_cidr_count": 0}
    path = config_dir / include_name
    if not os.path.isfile(path):
        entry["include_status"] = INCLUDE_NOT_ENABLED
        return entry
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        entry["include_status"] = INCLUDE_UNKNOWN
        return entry
    include_lines = _route_lines(content)
    entry["include_cidr_count"] = len(include_lines)
    entry["include_status"] = (
        INCLUDE_IN_SYNC if include_lines == _route_lines(controller_content) else INCLUDE_STALE
    )
    return entry


def _remote_include_context(adapter: Any) -> tuple[dict[str, dict], dict[str, int]]:
    """Provider states and include line counts from the node agent overview."""
    try:
        overview = adapter.get_routing_overview() or {}
    except Exception as exc:
        logger.warning("routing overview unavailable for preview: %s", exc)
        return {}, {}
    providers = {
        str(item.get("filename")): item
        for item in overview.get("providers") or []
        if item.get("filename")
    }
    include_counts = (overview.get("route_stats") or {}).get("config_include_per_file") or {}
    return providers, include_counts


def _remote_include_entry(
    filename: str,
    controller_count: int,
    providers: dict[str, dict],
    include_counts: dict[str, int],
) -> dict[str, Any]:
    include_name = masked_include_name(filename)
    entry: dict[str, Any] = {"include_file": include_name, "include_cidr_count": 0}
    provider = providers.get(filename) or {}
    if not provider.get("enabled"):
        entry["include_status"] = INCLUDE_NOT_ENABLED
        return entry
    # The agent reports counts only; equal counts mean the include file is current.
    used = include_counts.get(include_name)
    if used is None:
        used = provider.get("cidr_count")
    if used is None:
        entry["include_status"] = INCLUDE_UNKNOWN
        return entry
    used = int(used or 0)
    entry["include_cidr_count"] = used
    entry["include_status"] = INCLUDE_IN_SYNC if used == controller_count else INCLUDE_STALE
    return entry


def _preview_node(
    node: Node,
    filenames: list[str],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "node_id": node.id,
        "node_name": node.name,
        "status": "ok",
        "files": [],
        "total_controller_routes": 0,
        "total_node_routes": 0,
        "total_added": 0,
        "total_removed": 0,
        "files_changed": 0,
        "files_stale": 0,
        "stale_files": [],
    }
    try:
        adapter = get_adapter_for_node(node)
    except Exception as exc:
        entry["status"] = "error"
        entry["error"] = str(exc)
        return entry

    is_local = bool(getattr(node, "is_local", False))
    providers, include_counts = ({}, {}) if is_local else _remote_include_context(adapter)
    local_config_dir = _local_config_dir(node) if is_local else None

    for filename in filenames:
        controller_content, controller_count = _read_controller_content(filename)
        try:
            node_payload = adapter.get_provider_content(filename)
            node_content = str(node_payload.get("content") or "")
            node_count = int(node_payload.get("cidr_count") or len(_route_lines(node_content)))
        except Exception as exc:
            entry["files"].append(
                {
                    "file": filename,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        if controller_count <= 0 and not controller_content.strip():
            include_entry = {
                "include_file": masked_include_name(filename),
                "include_status": INCLUDE_UNKNOWN,
                "include_cidr_count": 0,
            }
        elif is_local:
            include_entry = _local_include_entry(filename, controller_content, local_config_dir)
        else:
            include_entry = _remote_include_entry(
                filename, controller_count, providers, include_counts
            )

        diff = _diff_stats(controller_content, node_content)
        controller_path = _artifact_path(filename)
        file_entry = {
            "file": filename,
            "status": "ok",
            "controller_cidr_count": controller_count,
            "node_cidr_count": node_count,
            "diff": diff,
            "exists_on_controller": bool(controller_content.strip())
            or (controller_path is not None and os.path.isfile(controller_path)),
            "exists_on_node": bool(node_content.strip()),
            **include_entry,
        }
        entry["files"].append(file_entry)
        entry["total_controller_routes"] += controller_count
        entry["total_node_routes"] += node_count
        entry["total_added"] += int(diff["added"])
        entry["total_removed"] += int(diff["removed"])
        if diff["changed"]:
            entry["files_changed"] += 1
        if include_entry["include_status"] == INCLUDE_STALE:
            entry["files_stale"] += 1
            entry["stale_files"].append(include_entry["include_file"])

    return entry


def compute_deploy_preview(
    db: Session,
    *,
    target_node_ids: list[int] | None = None,
    all_online: bool = False,
    target_node_id: int | None = None,
    selected_files: list[str] | list[dict] | None = None,
) -> dict[str, Any]:
    """Compare compiled controller artifacts with current node files (dry-run, no push)."""
    filenames = _normalize_filenames(selected_files)
    if not filenames and not selected_files:
        filenames = _list_artifact_filenames()
    if not filenames:
        return {
            "success": False,
            "message": "Нет файлов для preview: сначала выполните сборку (compile)",
            "files": [],
            "per_node": [],
            "stale_files": [],
            "has_stale_includes": False,
            "summary": "Нет артефактов для сравнения",
        }

    nodes, skipped = resolve_deploy_targets(
        db,
        target_node_ids=target_node_ids,
        all_online=all_online,
        target_node_id=target_node_id,
    )

    per_node = [_preview_node(node, filenames) for node in nodes]
    for skip in skipped:
        per_node.append(
            {
                "node_id": skip.get("node_id"),
                "node_name": skip.get("node_name"),
                "status": "skipped",
                "error": skip.get("error"),
                "files": [],
                "files_stale": 0,
                "stale_files": [],
            }
        )

    controller_summary: dict[str, dict[str, int | bool]] = {}
    for filename in filenames:
        controller_path = _artifact_path(filename)
        _, count = _read_controller_content(filename)
        controller_summary[filename] = {
            "cidr_count": count,
            "exists": controller_path is not None and os.path.isfile(controller_path),
        }

    preview_nodes = [entry for entry in per_node if entry.get("status") == "ok"]
    any_changes = any(int(entry.get("files_changed") or 0) > 0 for entry in preview_nodes)
    errors = [entry for entry in per_node if entry.get("status") == "error"]
    stale_files = sorted(
        {name for entry in preview_nodes for name in entry.get("stale_files") or []}
    )
    has_stale = bool(stale_files)

    if errors:
        message = f"Preview готов с ошибками на {len(errors)} узел(ов)"
    elif not preview_nodes:
        message = "Нет online-узлов для preview"
    elif any_changes and has_stale:
        message = "Обнаружены отличия и устаревшие include-файлы — deploy изменит маршруты на узлах"
    elif has_stale:
        message = "List-файлы совпадают с контроллером, но include-файлы на узлах устарели"
    elif any_changes:
        message = "Обнаружены отличия — deploy изменит файлы на узлах"
    else:
        message = "Файлы на узлах совпадают с контроллером — deploy не изменит маршруты"

    changed_files = sum(int(entry.get("files_changed") or 0) for entry in preview_nodes)
    summary = (
        f"Узлов: {len(preview_nodes)}, изменённых файлов: {changed_files}, "
        f"устаревших include-файлов: {len(stale_files)}, ошибок: {len(errors)}"
    )

    return {
        "success": len(errors) == 0,
        "message": message,
        "summary": summary,
        "dry_run": True,
        "artifact_files": filenames,
        "controller_artifacts": controller_summary,
        "per_node": per_node,
        "nodes_previewed": len(preview_nodes),
        "nodes_skipped": len(skipped),
        "nodes_errored": len(errors),
        "has_changes": any_changes or has_stale,
        "has_stale_includes": has_stale,
        "stale_files": stale_files,
    }
