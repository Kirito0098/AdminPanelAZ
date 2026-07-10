"""Background Node Sync reconcile worker — periodic parity checks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.config import get_settings
from app.database import SessionLocal
from app.models import NodeSyncGroup, SyncStatus
from app.services.node_sync.antizapret_sync import heal_antizapret_drift
from app.services.node_sync.config_sync import heal_config_drift
from app.services.node_sync.groups import is_auto_sync_enabled
from app.services.node_sync.policy_sync import heal_policy_drift
from app.services.node_sync.vpn_state_sync import heal_crypto_drift
from app.services.node_sync.verify import verify_sync_group

logger = logging.getLogger(__name__)
settings = get_settings()

_PKI_FP_PREFIX = "easyrsa3/"
_CLIENT_DRIFT_KINDS = frozenset({"openvpn_clients", "wireguard_clients"})


def classify_heal_actions(verify_result: dict[str, Any]) -> tuple[set[str], bool]:
    """Return heal action names and whether drift is entirely unhealable incrementally."""
    actions: set[str] = set()
    has_unhealable = False
    has_healable = False

    for replica in verify_result.get("replicas") or []:
        for mismatch in replica.get("mismatches") or []:
            kind = mismatch.get("kind")
            if kind == "node_status":
                has_unhealable = True
                continue
            if kind in _CLIENT_DRIFT_KINDS:
                actions.add("crypto_sync")
                actions.add("policy")
                has_healable = True
                continue
            if kind == "fingerprint":
                path = str(mismatch.get("path") or "")
                if path == "antizapret/config":
                    actions.add("config")
                    actions.add("antizapret")
                    has_healable = True
                elif path == "wireguard/conf_files" or path.startswith(_PKI_FP_PREFIX):
                    actions.add("crypto_sync")
                    has_healable = True
                else:
                    actions.add("config")
                    has_healable = True

    if has_unhealable and not has_healable:
        return set(), True
    return actions, False


def _read_heal_failure_count(verify_result: dict[str, Any] | None) -> int:
    if not verify_result:
        return 0
    raw = verify_result.get("auto_heal_failures")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _merge_heal_failure_count(verify_result: dict[str, Any], count: int) -> dict[str, Any]:
    merged = dict(verify_result)
    merged["auto_heal_failures"] = max(0, int(count))
    return merged


def _persist_verify_result(group: NodeSyncGroup, verify_result: dict[str, Any]) -> None:
    group.last_verify_result = json.dumps(verify_result, ensure_ascii=False)


def _attempt_incremental_heal(
    db,
    group: NodeSyncGroup,
    verify_result: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Run incremental heal paths for detected drift. Never invokes Push full."""
    actions, unhealable_only = classify_heal_actions(verify_result)
    if unhealable_only:
        return False, ["incremental heal cannot fix offline nodes"]
    if not actions:
        return False, ["no incremental heal actions for detected drift"]

    errors: list[str] = []
    if "crypto_sync" in actions:
        result = heal_crypto_drift(db, group)
        if not result.get("success"):
            for entry in result.get("errors") or []:
                errors.append(str(entry.get("error") or entry))
    if "config" in actions:
        result = heal_config_drift(db, group)
        if not result.get("success"):
            for entry in result.get("errors") or []:
                errors.append(str(entry.get("error") or entry))
    if "antizapret" in actions:
        result = heal_antizapret_drift(db, group)
        if not result.get("success"):
            for entry in result.get("errors") or []:
                errors.append(str(entry.get("error") or entry))
    if "policy" in actions:
        result = heal_policy_drift(db, group)
        if not result.get("success"):
            for entry in result.get("errors") or []:
                errors.append(str(entry.get("error") or entry))

    return not errors, errors


def reconcile_sync_groups_once() -> dict:
    db = SessionLocal()
    checked = 0
    drift_groups: list[dict] = []
    try:
        groups = db.query(NodeSyncGroup).order_by(NodeSyncGroup.id).all()
        for group in groups:
            result = verify_sync_group(db, group)
            checked += 1
            prior_failures = _read_heal_failure_count(result)

            if result.get("ready"):
                if prior_failures:
                    _persist_verify_result(group, _merge_heal_failure_count(result, 0))
                    db.commit()
                continue

            heal_attempted = False
            heal_errors: list[str] = []
            if settings.node_sync_auto_heal and is_auto_sync_enabled(group):
                heal_attempted = True
                heal_ok, heal_errors = _attempt_incremental_heal(db, group, result)
                if heal_ok:
                    result = verify_sync_group(db, group)
                    if result.get("ready"):
                        _persist_verify_result(group, _merge_heal_failure_count(result, 0))
                        db.commit()
                        logger.info(
                            "Node sync auto-heal succeeded: group=%s domain=%s",
                            group.name,
                            group.shared_domain,
                        )
                        continue

            heal_failures = prior_failures + 1 if heal_attempted else prior_failures
            result = _merge_heal_failure_count(result, heal_failures)
            _persist_verify_result(group, result)

            notify = (
                not settings.node_sync_auto_heal
                or not is_auto_sync_enabled(group)
                or not heal_attempted
                or heal_failures >= settings.node_sync_auto_heal_max_failures
            )
            group.sync_status = SyncStatus.failed
            summary = str(result.get("summary") or "parity mismatch")
            if heal_attempted:
                detail = "; ".join(heal_errors) if heal_errors else summary
                group.last_sync_error = (
                    f"auto-heal attempt {heal_failures}/{settings.node_sync_auto_heal_max_failures}: {detail}"
                )
            else:
                group.last_sync_error = summary
            db.commit()

            drift_item = {
                "group_id": group.id,
                "name": group.name,
                "shared_domain": group.shared_domain,
                "summary": result.get("summary"),
                "auto_heal_failures": heal_failures,
                "notify": notify,
            }
            if heal_attempted and notify:
                drift_item["hint"] = (
                    "Incremental auto-heal exhausted; run Push full manually or fix drift on primary"
                )
            drift_groups.append(drift_item)
            logger.warning(
                "Node sync drift: group=%s domain=%s summary=%s heal_failures=%s notify=%s",
                group.name,
                group.shared_domain,
                result.get("summary"),
                heal_failures,
                notify,
            )
        return {"node_sync_reconcile": "ok", "checked": checked, "drift": drift_groups}
    except Exception as exc:
        logger.warning("Node sync reconcile failed: %s", exc)
        return {"node_sync_reconcile": "error", "error": str(exc)}
    finally:
        db.close()


def reconcile_sync_groups_safe() -> dict:
    started = time.perf_counter()
    result = reconcile_sync_groups_once()
    if result.get("node_sync_reconcile") == "ok":
        drift = result.get("drift") or []
        logger.info(
            "Node sync reconcile: checked=%d drift=%d duration_ms=%d",
            result.get("checked", 0),
            len(drift),
            int((time.perf_counter() - started) * 1000),
        )
        to_notify = [item for item in drift if item.get("notify", True)]
        if to_notify:
            _notify_drift(to_notify)
    return result


def _notify_drift(drift_groups: list[dict]) -> None:
    try:
        from app.services.admin_notify import admin_notify_service

        db = SessionLocal()
        try:
            for item in drift_groups:
                admin_notify_service.send_settings_change(
                    db,
                    actor_username="system",
                    settings_key="node_sync_drift",
                    detail=json.dumps(item, ensure_ascii=False),
                )
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Node sync drift notify skipped: %s", exc)


async def run_node_sync_reconcile_loop() -> None:
    if not settings.node_sync_reconcile_enabled:
        return

    while True:
        try:
            await asyncio.to_thread(reconcile_sync_groups_safe)
        except Exception as exc:
            logger.warning("Node sync reconcile loop error: %s", exc)
        await asyncio.sleep(settings.node_sync_reconcile_interval_seconds)
