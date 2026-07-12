"""Parity verification between primary and replica nodes in a sync group."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.node_adapter import NodeAdapter
from app.services.node_manager import check_node_health, get_adapter_for_node, update_node_from_health
from app.services.node_sync.fingerprints import CONFIG_FP_PREFIX
from app.services.node_sync.groups import parse_replica_node_ids
from app.services.openvpn_pki import profile_issues_payload, validate_all_openvpn_profiles


def _refresh_node_online(db: Session, node: Node | None) -> bool:
    """Live health check before parity verify — avoids stale offline status in DB."""
    if not node:
        return False
    health = check_node_health(node)
    update_node_from_health(node, health, db)
    db.refresh(node)
    return node.status == NodeStatus.online


def _client_set_diff(primary: set[str], replica: set[str]) -> dict[str, list[str]]:
    only_primary = sorted(primary - replica)
    only_replica = sorted(replica - primary)
    if not only_primary and not only_replica:
        return {}
    return {"only_primary": only_primary, "only_replica": only_replica}


def _config_file_maps(fingerprints: dict[str, str]) -> dict[str, str]:
    prefix = f"{CONFIG_FP_PREFIX}/"
    return {
        key[len(prefix) :]: value
        for key, value in fingerprints.items()
        if key.startswith(prefix) and key != CONFIG_FP_PREFIX
    }


def _has_config_file_detail(fingerprints: dict[str, str]) -> bool:
    return bool(_config_file_maps(fingerprints))


def _enrich_config_fingerprints(fingerprints: dict[str, str], adapter: NodeAdapter) -> dict[str, str]:
    if _has_config_file_detail(fingerprints):
        return fingerprints
    try:
        file_hashes = adapter.get_config_file_fingerprints()
    except Exception:
        return fingerprints
    if not file_hashes:
        return fingerprints
    enriched = dict(fingerprints)
    for filename, digest in file_hashes.items():
        enriched[f"{CONFIG_FP_PREFIX}/{filename}"] = digest
    return enriched


def _config_files_diff(primary_fp: dict[str, str], replica_fp: dict[str, str]) -> dict[str, Any] | None:
    primary_agg = primary_fp.get(CONFIG_FP_PREFIX)
    replica_agg = replica_fp.get(CONFIG_FP_PREFIX)
    primary_files = _config_file_maps(primary_fp)
    replica_files = _config_file_maps(replica_fp)
    has_primary_detail = bool(primary_files)
    has_replica_detail = bool(replica_files)

    changed_files: list[str] = []
    only_primary: list[str] = []
    only_replica: list[str] = []
    detail: str | None = None

    if has_primary_detail and has_replica_detail:
        for name in sorted(set(primary_files) | set(replica_files)):
            primary_hash = primary_files.get(name)
            replica_hash = replica_files.get(name)
            if primary_hash is None:
                only_replica.append(name)
            elif replica_hash is None:
                only_primary.append(name)
            elif primary_hash != replica_hash:
                changed_files.append(name)
    elif has_primary_detail != has_replica_detail:
        if has_primary_detail:
            detail = (
                "Детализация по файлам недоступна на реплике — обновите node agent и повторите проверку."
            )
        else:
            detail = (
                "Детализация по файлам недоступна на основном узле — "
                "обновите node agent и повторите проверку."
            )

    if (
        primary_agg == replica_agg
        and not changed_files
        and not only_primary
        and not only_replica
        and not detail
    ):
        return None

    result: dict[str, Any] = {
        "changed_files": changed_files,
        "only_primary": only_primary,
        "only_replica": only_replica,
    }
    if detail:
        result["detail"] = detail
    return result


def _fingerprint_mismatches(primary_fp: dict[str, str], replica_fp: dict[str, str]) -> list[dict[str, Any]]:
    config_prefix = f"{CONFIG_FP_PREFIX}/"
    skip_keys = {CONFIG_FP_PREFIX} | {
        key for key in (set(primary_fp) | set(replica_fp)) if key.startswith(config_prefix)
    }
    mismatches: list[dict[str, Any]] = []

    for key in sorted((set(primary_fp) | set(replica_fp)) - skip_keys):
        primary_hash = primary_fp.get(key)
        replica_hash = replica_fp.get(key)
        if primary_hash != replica_hash:
            mismatches.append(
                {
                    "kind": "fingerprint",
                    "path": key,
                    "primary": primary_hash,
                    "replica": replica_hash,
                }
            )

    config_diff = _config_files_diff(primary_fp, replica_fp)
    if config_diff:
        mismatches.append(
            {
                "kind": "fingerprint",
                "path": CONFIG_FP_PREFIX,
                "primary": primary_fp.get(CONFIG_FP_PREFIX),
                "replica": replica_fp.get(CONFIG_FP_PREFIX),
                **config_diff,
            }
        )

    return mismatches


def verify_sync_group(
    db: Session,
    group: NodeSyncGroup,
    *,
    progress_callback: Callable[[int, str, str | None], None] | None = None,
) -> dict[str, Any]:
    def progress(percent: int, stage: str, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(percent, stage, message)

    progress(5, "Проверка паритета…", "Primary")
    primary_node = db.get(Node, group.primary_node_id)
    primary_online = _refresh_node_online(db, primary_node)
    if not primary_node or not primary_online:
        result = {
            "ready": False,
            "shared_domain": group.shared_domain,
            "primary_node_id": group.primary_node_id,
            "replicas": [],
            "summary": "Основной узел offline или не найден",
        }
        group.last_verify_at = datetime.utcnow()
        group.last_verify_result = json.dumps(result, ensure_ascii=False)
        db.commit()
        return result

    primary_adapter = get_adapter_for_node(primary_node)
    primary_ovpn = set(primary_adapter.list_openvpn_clients())
    primary_wg = set(primary_adapter.list_wireguard_clients())
    primary_fp = _enrich_config_fingerprints(
        primary_adapter.get_antizapret_fingerprints(),
        primary_adapter,
    )
    primary_profile_validation = validate_all_openvpn_profiles(primary_adapter)
    profile_cert_ready = primary_profile_validation.ready

    replica_results: list[dict[str, Any]] = []
    replica_ids = parse_replica_node_ids(group.replica_node_ids)
    ready = True
    if not profile_cert_ready:
        ready = False

    replica_profile_issues: dict[int, list[dict[str, str | None]]] = {}

    for index, replica_id in enumerate(replica_ids):
        percent = 10 + int((index / max(len(replica_ids), 1)) * 80)
        node = db.get(Node, replica_id)
        node_name = node.name if node else str(replica_id)
        progress(percent, f"Verify: {node_name}")

        mismatches: list[dict[str, Any]] = []
        online = _refresh_node_online(db, node)
        if not online:
            ready = False
            mismatches.append({"kind": "node_status", "detail": "узел offline или не найден"})
            replica_results.append(
                {
                    "node_id": replica_id,
                    "node_name": node_name,
                    "online": False,
                    "mismatches": mismatches,
                }
            )
            continue

        adapter = get_adapter_for_node(node)
        ovpn_diff = _client_set_diff(primary_ovpn, set(adapter.list_openvpn_clients()))
        if ovpn_diff:
            ready = False
            mismatches.append({"kind": "openvpn_clients", **ovpn_diff})

        wg_diff = _client_set_diff(primary_wg, set(adapter.list_wireguard_clients()))
        if wg_diff:
            ready = False
            mismatches.append({"kind": "wireguard_clients", **wg_diff})

        replica_fp = _enrich_config_fingerprints(
            adapter.get_antizapret_fingerprints(),
            adapter,
        )
        fp_mismatches = _fingerprint_mismatches(primary_fp, replica_fp)
        if fp_mismatches:
            ready = False
            mismatches.extend(fp_mismatches)

        replica_profile_validation = validate_all_openvpn_profiles(adapter)
        if not replica_profile_validation.ready:
            ready = False
            profile_cert_ready = False
            replica_profile_issues[replica_id] = profile_issues_payload(replica_profile_validation)
            mismatches.append(
                {
                    "kind": "openvpn_profile_certs",
                    "issues": profile_issues_payload(replica_profile_validation),
                }
            )

        replica_results.append(
            {
                "node_id": replica_id,
                "node_name": node_name,
                "online": True,
                "mismatches": mismatches,
            }
        )

    summary = "Готово к DNS-переключению" if ready else "Расхождения между основным узлом и репликой"
    result = {
        "ready": ready,
        "shared_domain": group.shared_domain,
        "primary_node_id": group.primary_node_id,
        "replicas": replica_results,
        "summary": summary,
        "openvpn_profile_certs": {
            "ready": profile_cert_ready,
            "primary_issues": profile_issues_payload(primary_profile_validation),
            "replica_issues": {
                str(node_id): issues for node_id, issues in replica_profile_issues.items()
            },
        },
    }

    if group.last_verify_result:
        try:
            prior = json.loads(group.last_verify_result)
            if isinstance(prior, dict) and "auto_heal_failures" in prior:
                result["auto_heal_failures"] = prior["auto_heal_failures"]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    group.last_verify_at = datetime.utcnow()
    group.last_verify_result = json.dumps(result, ensure_ascii=False)
    db.commit()

    progress(100, "Verify завершён")
    return result


def verify_sync_group_by_id(db: Session, group_id: int) -> dict[str, Any]:
    group = db.get(NodeSyncGroup, group_id)
    if not group:
        raise ValueError(f"Sync group {group_id} not found")
    return verify_sync_group(db, group)
