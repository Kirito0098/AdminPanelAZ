"""Deploy CIDR artifacts from controller LIST_DIR to nodes."""

import hashlib
import os
from typing import Any

from app.services.cidr.pipeline.constants import LIST_DIR
from app.services.node_adapter import NodeAdapter


def _normalize_filenames(filenames: list[str] | list[dict] | None) -> list[str]:
    if not filenames:
        return []
    normalized: list[str] = []
    for item in filenames:
        if isinstance(item, dict):
            name = item.get("file")
            if name:
                normalized.append(str(name))
        else:
            normalized.append(str(item))
    return normalized


def _list_artifact_filenames() -> list[str]:
    if not os.path.isdir(LIST_DIR):
        return []
    return sorted(
        name
        for name in os.listdir(LIST_DIR)
        if name.endswith(".txt") and os.path.isfile(os.path.join(LIST_DIR, name))
    )


def push_cidr_artifacts(
    adapter: NodeAdapter,
    filenames: list[str] | list[dict] | None = None,
) -> dict[str, Any]:
    """Read compiled CIDR files from LIST_DIR and push them via the node adapter."""
    targets = _normalize_filenames(filenames) or _list_artifact_filenames()

    pushed: list[str] = []
    failed: list[dict[str, str]] = []
    skipped: list[str] = []

    for filename in targets:
        file_path = os.path.join(LIST_DIR, filename)
        if not os.path.isfile(file_path):
            skipped.append(filename)
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            adapter.save_provider_content(filename, content)
            pushed.append(filename)
        except OSError as exc:
            failed.append({"file": filename, "error": str(exc)})
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
