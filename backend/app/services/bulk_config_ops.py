"""Bulk config operations via background tasks."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import User, VpnConfig, VpnType
from app.services.access_policy import AccessPolicyService
from app.services.admin_notify import admin_notify_service
from app.services.background_tasks import background_task_service
from app.services.config_tags import resolve_config_ids_by_tags
from app.services.node_manager import get_active_adapter, get_active_node, get_node_antizapret_path
from app.services.node_sync.client_sync import maybe_replicate_delete
from app.services.node_sync.groups import find_sync_group_for_primary, require_ha_primary_for_client_ops

logger = logging.getLogger(__name__)


def _run_single_op(
    *,
    operation: str,
    config_id: int,
    node_id: int,
    block_days: int,
    renew_cert_days: int,
    actor_username: str,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        config = (
            db.query(VpnConfig)
            .filter(VpnConfig.id == config_id, VpnConfig.node_id == node_id)
            .first()
        )
        if not config:
            return {"config_id": config_id, "ok": False, "error": "not found"}

        adapter = get_active_adapter(db)
        svc = AccessPolicyService(
            db,
            antizapret_path=get_node_antizapret_path(db),
            node_id=node_id,
            adapter=adapter,
        )
        name = config.client_name

        if operation == "block_temp":
            if config.vpn_type == VpnType.openvpn:
                svc.openvpn_temp_block(name, block_days, actor=actor_username)
            else:
                svc.wg_temp_block(name, block_days, actor=actor_username)
        elif operation == "block_perm":
            if config.vpn_type == VpnType.openvpn:
                svc.openvpn_permanent_block(name, actor=actor_username)
            else:
                svc.wg_permanent_block(name, actor=actor_username)
        elif operation == "unblock":
            if config.vpn_type == VpnType.openvpn:
                svc.openvpn_unblock(name, actor=actor_username)
            else:
                svc.wg_unblock(name, actor=actor_username)
        elif operation == "renew_cert":
            if config.vpn_type != VpnType.openvpn:
                return {"config_id": config_id, "ok": False, "error": "not openvpn"}
            adapter.add_openvpn_client(name, renew_cert_days)
            config.cert_expire_days = renew_cert_days
            db.commit()
        elif operation == "delete":
            if config.vpn_type == VpnType.openvpn:
                adapter.delete_openvpn_client(name)
            else:
                adapter.delete_wireguard_client(name)
            node = get_active_node(db)
            sync_group = find_sync_group_for_primary(db, node.id)
            if sync_group:
                maybe_replicate_delete(db, node_id=node.id, primary_config=config)
            admin_notify_service.send_config_delete(
                db,
                actor_username=actor_username,
                target_name=name,
                target_type=config.vpn_type.value,
                node_id=node.id,
                node_name=node.name,
            )
            db.query(VpnConfig).filter(VpnConfig.id == config.id).delete(synchronize_session=False)
            db.commit()
        else:
            return {"config_id": config_id, "ok": False, "error": f"unknown op {operation}"}

        return {"config_id": config_id, "client_name": name, "ok": True}
    except Exception as exc:
        db.rollback()
        logger.exception("Bulk op failed for config %s: %s", config_id, exc)
        return {"config_id": config_id, "ok": False, "error": str(exc)}
    finally:
        db.close()


def run_bulk_config_op(
    *,
    operation: str,
    config_ids: list[int],
    tag_ids: list[int],
    block_days: int,
    renew_cert_days: int,
    actor_username: str,
    progress_updater: Callable[[int, str, str | None], None] | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        node = get_active_node(db)
        targets = resolve_config_ids_by_tags(db, node.id, tag_ids, base_config_ids=config_ids)
    finally:
        db.close()

    if not targets:
        return {
            "message": "Нет конфигураций для обработки",
            "output": json.dumps({"succeeded": [], "failed": [], "operation": operation}, ensure_ascii=False),
        }

    total = len(targets)
    max_workers = max(1, int(get_settings().bulk_config_op_max_workers))
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _run_single_op,
                operation=operation,
                config_id=cid,
                node_id=node.id,
                block_days=block_days,
                renew_cert_days=renew_cert_days,
                actor_username=actor_username,
            ): cid
            for cid in targets
        }
        for future in as_completed(futures):
            cid = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"config_id": cid, "ok": False, "error": str(exc)}
            done += 1
            if result.get("ok"):
                succeeded.append(result)
            else:
                failed.append(result)
            if progress_updater:
                label = result.get("client_name") or str(cid)
                pct = int(done * 100 / total)
                progress_updater(pct, f"{label} ({done}/{total})")

    summary = {
        "operation": operation,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
    }
    msg = f"Обработано {len(succeeded)}/{total}, ошибок: {len(failed)}"
    return {
        "message": msg,
        "output": json.dumps(summary, ensure_ascii=False),
    }


def enqueue_bulk_config_op(
    db: Session,
    *,
    operation: str,
    config_ids: list[int],
    tag_ids: list[int],
    block_days: int,
    renew_cert_days: int,
    actor: User,
) -> str:
    node = get_active_node(db)
    require_ha_primary_for_client_ops(db, node=node)
    targets = resolve_config_ids_by_tags(db, node.id, tag_ids, base_config_ids=config_ids)
    if not targets:
        raise ValueError("Нет конфигураций для обработки")

    op_labels = {
        "block_temp": "Массовая временная блокировка",
        "block_perm": "Массовая постоянная блокировка",
        "unblock": "Массовая разблокировка",
        "delete": "Массовое удаление",
        "renew_cert": "Массовое продление сертификатов",
    }

    def task_callable(progress_updater=None):
        return run_bulk_config_op(
            operation=operation,
            config_ids=config_ids,
            tag_ids=tag_ids,
            block_days=block_days,
            renew_cert_days=renew_cert_days,
            actor_username=actor.username,
            progress_updater=progress_updater,
        )

    task = background_task_service.enqueue_background_task(
        "config_bulk_op",
        task_callable,
        created_by_username=actor.username,
        queued_message=f"{op_labels.get(operation, operation)}: {len(targets)} конфиг.",
    )
    return task.id
