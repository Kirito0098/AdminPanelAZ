"""Deploy CIDR artifacts from controller LIST_DIR to nodes."""

import hashlib
import logging
import os
from typing import Any

from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline.constants import LIST_DIR
from app.services.node_adapter import NodeAdapter

logger = logging.getLogger(__name__)

ALLOWED_ARTIFACT_FILES = frozenset(IP_FILES)


def _requested_filenames(filenames: list[str] | list[dict] | None) -> list[str]:
    names: list[str] = []
    for item in filenames or []:
        name = item.get("file") if isinstance(item, dict) else item
        if name:
            names.append(str(name))
    return names


def _normalize_filenames(filenames: list[str] | list[dict] | None) -> list[str]:
    """Keep plain provider filenames; paths and unknown names are rejected."""
    normalized: list[str] = []
    for name in _requested_filenames(filenames):
        if name != os.path.basename(name) or name not in ALLOWED_ARTIFACT_FILES:
            logger.warning("ignored unknown deploy filename: %r", name)
            continue
        if name not in normalized:
            normalized.append(name)
    return normalized


def _artifact_path(filename: str) -> str | None:
    """Resolve a whitelisted artifact inside LIST_DIR, None if it escapes."""
    path = os.path.join(LIST_DIR, filename)
    root = os.path.realpath(LIST_DIR)
    if not os.path.realpath(path).startswith(root + os.sep):
        logger.warning("ignored deploy path outside LIST_DIR: %r", filename)
        return None
    return path


def _list_artifact_filenames() -> list[str]:
    if not os.path.isdir(LIST_DIR):
        return []
    names: list[str] = []
    for name in os.listdir(LIST_DIR):
        if name not in ALLOWED_ARTIFACT_FILES:
            continue
        path = _artifact_path(name)
        if path is not None and os.path.isfile(path):
            names.append(name)
    return sorted(names)


def _count_cidr_lines(path: str) -> int:
    count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def list_compile_artifacts() -> dict[str, dict[str, int | bool]]:
    """Return per-file artifact stats from controller LIST_DIR."""
    artifacts: dict[str, dict[str, int | bool]] = {}
    if not os.path.isdir(LIST_DIR):
        return artifacts
    for filename in _list_artifact_filenames():
        file_path = os.path.join(LIST_DIR, filename)
        try:
            cidr_count = _count_cidr_lines(file_path)
        except OSError:
            cidr_count = 0
        artifacts[filename] = {"cidr_count": cidr_count, "exists": True}
    return artifacts


def push_cidr_artifacts(
    adapter: NodeAdapter,
    filenames: list[str] | list[dict] | None = None,
) -> dict[str, Any]:
    """Read compiled CIDR files from LIST_DIR and push them via the node adapter."""
    requested = _requested_filenames(filenames)
    targets = _normalize_filenames(filenames)
    if not targets and not requested:
        targets = _list_artifact_filenames()
    # Explicitly selected unknown names are reported, never widened to all artifacts.
    skipped: list[str] = [name for name in requested if name not in targets]

    pushed: list[str] = []
    failed: list[dict[str, str]] = []

    for filename in targets:
        file_path = _artifact_path(filename)
        if file_path is None or not os.path.isfile(file_path):
            skipped.append(filename)
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            adapter.save_provider_content(filename, content)
            pushed.append(filename)
        except Exception as exc:
            failed.append({"file": filename, "error": str(exc)})

    return {"pushed": pushed, "failed": failed, "skipped": skipped}


def compute_artifact_stamp() -> str | None:
    """Fingerprint of compiled LIST_DIR artifacts (for deploy tracking)."""
    filenames = _list_artifact_filenames()
    if not filenames:
        return None
    hasher = hashlib.sha256()
    for filename in filenames:
        file_path = os.path.join(LIST_DIR, filename)
        hasher.update(filename.encode())
        with open(file_path, "rb") as handle:
            hasher.update(handle.read())
    return hasher.hexdigest()[:16]
