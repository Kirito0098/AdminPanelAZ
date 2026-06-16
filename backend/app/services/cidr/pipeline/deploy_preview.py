"""Deploy preview: diff controller artifacts vs node provider files (no apply)."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.models import Node
from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.deploy import _count_cidr_lines, _normalize_filenames
from app.services.cidr.pipeline.constants import LIST_DIR
from app.services.cidr.pipeline.orchestrator import resolve_deploy_targets
from app.services.node_manager import get_adapter_for_node


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
    path = os.path.join(LIST_DIR, filename)
    if not os.path.isfile(path):
        return "", 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    return content, _count_cidr_lines(path)


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
    }
    try:
        adapter = get_adapter_for_node(node)
    except Exception as exc:
        entry["status"] = "error"
        entry["error"] = str(exc)
        return entry

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

        diff = _diff_stats(controller_content, node_content)
        file_entry = {
            "file": filename,
            "status": "ok",
            "controller_cidr_count": controller_count,
            "node_cidr_count": node_count,
            "diff": diff,
            "exists_on_controller": bool(controller_content.strip()) or os.path.isfile(
                os.path.join(LIST_DIR, filename)
            ),
            "exists_on_node": bool(node_content.strip()),
        }
        entry["files"].append(file_entry)
        entry["total_controller_routes"] += controller_count
        entry["total_node_routes"] += node_count
        entry["total_added"] += int(diff["added"])
        entry["total_removed"] += int(diff["removed"])
        if diff["changed"]:
            entry["files_changed"] += 1

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
    filenames = _normalize_filenames(selected_files) or [
        name for name in sorted(IP_FILES.keys()) if os.path.isfile(os.path.join(LIST_DIR, name))
    ]
    if not filenames:
        return {
            "success": False,
            "message": "Нет файлов для preview: сначала выполните сборку (compile)",
            "files": [],
            "per_node": [],
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
            }
        )

    controller_summary: dict[str, dict[str, int | bool]] = {}
    for filename in filenames:
        _, count = _read_controller_content(filename)
        controller_summary[filename] = {
            "cidr_count": count,
            "exists": os.path.isfile(os.path.join(LIST_DIR, filename)),
        }

    preview_nodes = [entry for entry in per_node if entry.get("status") == "ok"]
    any_changes = any(int(entry.get("files_changed") or 0) > 0 for entry in preview_nodes)
    errors = [entry for entry in per_node if entry.get("status") == "error"]

    if errors:
        message = f"Preview готов с ошибками на {len(errors)} узел(ов)"
    elif not preview_nodes:
        message = "Нет online-узлов для preview"
    elif any_changes:
        message = "Обнаружены отличия — deploy изменит файлы на узлах"
    else:
        message = "Файлы на узлах совпадают с контроллером — deploy не изменит маршруты"

    return {
        "success": len(errors) == 0,
        "message": message,
        "dry_run": True,
        "artifact_files": filenames,
        "controller_artifacts": controller_summary,
        "per_node": per_node,
        "nodes_previewed": len(preview_nodes),
        "nodes_skipped": len(skipped),
        "nodes_errored": len(errors),
        "has_changes": any_changes,
    }
