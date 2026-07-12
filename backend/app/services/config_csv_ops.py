"""CSV import/export for VPN client configs."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import OpenVpnAccessPolicy, User, UserRole, VpnConfig, VpnType, WgAccessPolicy
from app.services.access_policy import AccessPolicyService
from app.services.background_tasks import background_task_service
from app.services.feature_guards import get_feature_service, require_vpn_type
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node, get_node_antizapret_path
from app.services.node_sync.groups import find_sync_group_for_primary, get_replica_nodes, require_ha_primary_for_client_ops
from app.services.node_sync.client_sync import maybe_replicate_create
from app.services.node_sync.policy_sync import maybe_replicate_policy_op
from app.services.node_sync.vpn_state_sync import copy_openvpn_profiles_from_primary
from app.services.openvpn_profile_repair import recreate_openvpn_profiles_after_admin_change
from app.services.traffic_limit import parse_traffic_limit_period_days

logger = logging.getLogger(__name__)

CSV_HEADERS = (
    "id",
    "client_name",
    "vpn_type",
    "owner_username",
    "cert_expire_days",
    "description",
    "traffic_limit_bytes",
    "traffic_limit_days",
    "block_mode",
    "created_at",
    "updated_at",
)

IMPORT_REQUIRED_HEADERS = ("client_name", "vpn_type")
IMPORT_HEADERS = IMPORT_REQUIRED_HEADERS + (
    "owner_username",
    "cert_expire_days",
    "description",
    "traffic_limit_bytes",
    "traffic_limit_days",
    "block_mode",
)


def _encode_block_mode(policy) -> str:
    if policy is None:
        return ""
    if getattr(policy, "is_permanent_blocked", False):
        return "permanent"
    if getattr(policy, "is_temp_blocked", False):
        days = getattr(policy, "block_days", None)
        return f"temp:{days}" if days else "temp"
    return ""


def _policy_row(db: Session, *, node_id: int, client_name: str, vpn_type: VpnType):
    if vpn_type == VpnType.openvpn:
        return (
            db.query(OpenVpnAccessPolicy)
            .filter(OpenVpnAccessPolicy.node_id == node_id, OpenVpnAccessPolicy.client_name == client_name)
            .first()
        )
    lookup_name = client_name.strip().lower()
    return (
        db.query(WgAccessPolicy)
        .filter(WgAccessPolicy.node_id == node_id, WgAccessPolicy.client_name == lookup_name)
        .first()
    )


def _parse_block_mode(raw: str) -> tuple[str | None, int | None]:
    value = (raw or "").strip().lower()
    if not value:
        return None, None
    if value in {"permanent", "perm"}:
        return "block_permanent", None
    if value == "temp":
        return "block_temp", 7
    if value.startswith("temp:"):
        days_raw = value.split(":", 1)[1].strip()
        try:
            days = int(days_raw)
        except ValueError as exc:
            raise ValueError("block_mode temp:N — N должно быть целым числом") from exc
        if days < 1:
            raise ValueError("block_mode temp:N — N должно быть ≥ 1")
        return "block_temp", days
    raise ValueError("block_mode: допустимо permanent, temp или temp:N")


def _parse_policy_fields(row: dict[str, str]) -> dict[str, Any]:
    limit_raw = row.get("traffic_limit_bytes", "").strip()
    days_raw = row.get("traffic_limit_days", "").strip()
    block_raw = row.get("block_mode", "").strip()

    limit_bytes: int | None = None
    if limit_raw:
        try:
            limit_bytes = int(limit_raw)
        except ValueError as exc:
            raise ValueError("traffic_limit_bytes должен быть целым числом") from exc
        if limit_bytes < 1:
            raise ValueError("traffic_limit_bytes должен быть ≥ 1")

    period_days = parse_traffic_limit_period_days(days_raw) if days_raw else None
    block_op, block_days = _parse_block_mode(block_raw)

    return {
        "limit_bytes": limit_bytes,
        "period_days": period_days,
        "block_op": block_op,
        "block_days": block_days,
    }


def _apply_csv_policies_on_primary(
    db: Session,
    *,
    node_id: int,
    client_name: str,
    vpn_type: VpnType,
    actor_username: str,
    policy_fields: dict[str, Any],
) -> None:
    limit_bytes = policy_fields.get("limit_bytes")
    period_days = policy_fields.get("period_days")
    block_op = policy_fields.get("block_op")
    block_days = policy_fields.get("block_days")

    if limit_bytes is None and block_op is None:
        return

    adapter = get_active_adapter(db)
    svc = AccessPolicyService(
        db,
        antizapret_path=get_node_antizapret_path(db),
        node_id=node_id,
        adapter=adapter,
    )

    if limit_bytes is not None:
        if vpn_type == VpnType.openvpn:
            svc.openvpn_set_traffic_limit(
                client_name,
                limit_bytes,
                period_days=period_days,
                actor=actor_username,
            )
        else:
            svc.wg_set_traffic_limit(
                client_name,
                limit_bytes,
                period_days=period_days,
                actor=actor_username,
            )

    if block_op == "block_temp":
        days = int(block_days or 7)
        if vpn_type == VpnType.openvpn:
            svc.openvpn_temp_block(client_name, days, actor=actor_username)
        else:
            svc.wg_temp_block(client_name, days, actor=actor_username)
    elif block_op == "block_permanent":
        if vpn_type == VpnType.openvpn:
            svc.openvpn_permanent_block(client_name, actor=actor_username)
        else:
            svc.wg_permanent_block(client_name, actor=actor_username)


def _replicate_csv_policies(
    db: Session,
    *,
    node_id: int,
    client_name: str,
    vpn_type: VpnType,
    actor_username: str,
    policy_fields: dict[str, Any],
) -> None:
    limit_bytes = policy_fields.get("limit_bytes")
    period_days = policy_fields.get("period_days")
    block_op = policy_fields.get("block_op")
    block_days = policy_fields.get("block_days")

    if limit_bytes is not None:
        maybe_replicate_policy_op(
            db,
            node_id=node_id,
            client_name=client_name,
            vpn_type=vpn_type,
            op="set_traffic_limit",
            actor=actor_username,
            limit_bytes=limit_bytes,
            period_days=period_days,
        )

    if block_op == "block_temp":
        maybe_replicate_policy_op(
            db,
            node_id=node_id,
            client_name=client_name,
            vpn_type=vpn_type,
            op="block_temp",
            actor=actor_username,
            days=int(block_days or 7),
        )
    elif block_op == "block_permanent":
        maybe_replicate_policy_op(
            db,
            node_id=node_id,
            client_name=client_name,
            vpn_type=vpn_type,
            op="block_permanent",
            actor=actor_username,
        )


def _normalize_vpn_type(raw: str) -> VpnType | None:
    value = (raw or "").strip().lower()
    if value in {"openvpn", "ovpn"}:
        return VpnType.openvpn
    if value in {"wireguard", "wg", "amneziawg", "awg"}:
        return VpnType.wireguard
    return None


def iter_config_export_csv(db: Session, *, node_id: int):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    rows = (
        db.query(VpnConfig, User.username)
        .join(User, VpnConfig.owner_id == User.id)
        .filter(VpnConfig.node_id == node_id, VpnConfig.ha_primary_config_id.is_(None))
        .order_by(VpnConfig.id)
        .all()
    )
    for config, owner_username in rows:
        policy = _policy_row(db, node_id=node_id, client_name=config.client_name, vpn_type=config.vpn_type)
        limit_bytes = policy.traffic_limit_bytes if policy and policy.traffic_limit_bytes is not None else ""
        limit_days = policy.traffic_limit_period_days if policy and policy.traffic_limit_period_days is not None else ""
        block_mode = _encode_block_mode(policy)
        writer.writerow(
            [
                config.id,
                config.client_name,
                config.vpn_type.value,
                owner_username or "",
                config.cert_expire_days if config.cert_expire_days is not None else "",
                config.description or "",
                limit_bytes,
                limit_days,
                block_mode,
                config.created_at.isoformat() if config.created_at else "",
                config.updated_at.isoformat() if config.updated_at else "",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def parse_import_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV пуст или без заголовка")
    normalized_fields = {f.strip().lower(): f for f in reader.fieldnames if f}
    missing = [h for h in IMPORT_REQUIRED_HEADERS if h not in normalized_fields]
    if missing:
        raise ValueError(f"Отсутствуют обязательные колонки: {', '.join(missing)}")

    rows: list[dict[str, str]] = []
    for idx, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        parsed: dict[str, str] = {}
        for key in IMPORT_HEADERS:
            source_key = normalized_fields.get(key)
            parsed[key] = (row.get(source_key or key) or "").strip()
        parsed["_line"] = str(idx)
        rows.append(parsed)
    if not rows:
        raise ValueError("CSV не содержит строк для импорта")
    return rows


def _import_single_row(
    db: Session,
    *,
    row: dict[str, str],
    node_id: int,
    default_owner_id: int,
    owner_by_username: dict[str, int],
    actor_username: str,
) -> dict[str, Any]:
    client_name = row.get("client_name", "").strip()
    if not client_name:
        return {"line": row.get("_line"), "ok": False, "error": "client_name пуст"}

    vpn_type = _normalize_vpn_type(row.get("vpn_type", ""))
    if vpn_type is None:
        return {"line": row.get("_line"), "ok": False, "error": "неизвестный vpn_type"}

    owner_username = row.get("owner_username", "").strip()
    owner_id = owner_by_username.get(owner_username) if owner_username else default_owner_id
    if owner_id is None:
        return {"line": row.get("_line"), "ok": False, "error": f"владелец не найден: {owner_username}"}

    cert_raw = row.get("cert_expire_days", "").strip()
    cert_expire_days: int | None = None
    if cert_raw:
        try:
            cert_expire_days = int(cert_raw)
        except ValueError:
            return {"line": row.get("_line"), "ok": False, "error": "cert_expire_days должен быть числом"}

    existing = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == client_name,
            VpnConfig.vpn_type == vpn_type,
        )
        .first()
    )
    if existing:
        return {"line": row.get("_line"), "client_name": client_name, "ok": False, "error": "уже существует"}

    try:
        require_vpn_type(vpn_type.value, service=get_feature_service())
    except Exception as exc:
        return {"line": row.get("_line"), "client_name": client_name, "ok": False, "error": str(exc)}

    adapter = get_active_adapter(db)
    try:
        if vpn_type == VpnType.openvpn:
            adapter.add_openvpn_client(client_name, cert_expire_days or 3650)
        else:
            adapter.add_wireguard_client(client_name)
    except Exception as exc:
        return {"line": row.get("_line"), "client_name": client_name, "ok": False, "error": str(exc)}

    config = VpnConfig(
        node_id=node_id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=owner_id,
        cert_expire_days=cert_expire_days,
        description=row.get("description") or None,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    try:
        policy_fields = _parse_policy_fields(row)
    except ValueError as exc:
        return {
            "line": row.get("_line"),
            "client_name": client_name,
            "config_id": config.id,
            "ok": False,
            "error": str(exc),
        }

    try:
        _apply_csv_policies_on_primary(
            db,
            node_id=node_id,
            client_name=client_name,
            vpn_type=vpn_type,
            actor_username=actor_username,
            policy_fields=policy_fields,
        )
    except Exception as exc:
        return {
            "line": row.get("_line"),
            "client_name": client_name,
            "config_id": config.id,
            "ok": False,
            "error": f"политика: {exc}",
        }

    maybe_replicate_create(db, node_id=node_id, primary_config=config)

    try:
        _replicate_csv_policies(
            db,
            node_id=node_id,
            client_name=client_name,
            vpn_type=vpn_type,
            actor_username=actor_username,
            policy_fields=policy_fields,
        )
    except Exception as exc:
        return {
            "line": row.get("_line"),
            "client_name": client_name,
            "config_id": config.id,
            "ok": False,
            "error": f"репликация политики: {exc}",
        }

    return {
        "line": row.get("_line"),
        "client_name": client_name,
        "config_id": config.id,
        "vpn_type": vpn_type.value,
        "ok": True,
    }


def run_config_csv_import(
    *,
    rows: list[dict[str, str]],
    actor_username: str,
    default_owner_id: int,
    progress_updater: Callable[[int, str, str | None], None] | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        node = get_active_node(db)
        require_ha_primary_for_client_ops(db, node=node)
        node_id = node.id
        users = db.query(User).filter(User.is_active.is_(True)).all()
        owner_by_username = {u.username: u.id for u in users}
    finally:
        db.close()

    total = len(rows)
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        row_db = SessionLocal()
        try:
            result = _import_single_row(
                row_db,
                row=row,
                node_id=node_id,
                default_owner_id=default_owner_id,
                owner_by_username=owner_by_username,
                actor_username=actor_username,
            )
        except Exception as exc:
            row_db.rollback()
            logger.exception("CSV import row failed: %s", exc)
            result = {"line": row.get("_line"), "ok": False, "error": str(exc)}
        finally:
            row_db.close()

        if result.get("ok"):
            succeeded.append(result)
        else:
            failed.append(result)

        if progress_updater:
            label = result.get("client_name") or str(row.get("_line"))
            pct = int(idx * 100 / total)
            progress_updater(pct, f"{label} ({idx}/{total})")

    recreate_warnings = _recreate_ovpn_profiles_after_import(
        succeeded, node_id=node_id, progress_updater=progress_updater
    )

    summary = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "actor": actor_username,
    }
    if recreate_warnings:
        summary["recreate_warnings"] = recreate_warnings
    msg = f"Импорт CSV: {len(succeeded)}/{total}, ошибок: {len(failed)}"
    if recreate_warnings:
        msg += f"; предупреждения профилей: {len(recreate_warnings)}"
    return {
        "message": msg,
        "output": json.dumps(summary, ensure_ascii=False),
    }


def _recreate_ovpn_profiles_after_import(
    succeeded: list[dict[str, Any]],
    *,
    node_id: int,
    progress_updater: Callable[[int, str, str | None], None] | None = None,
) -> list[str]:
    """One batch client.sh 7 after import so new .ovpn embed current setup hosts.

    On an HA primary the recreated profiles are then byte-copied to replicas to
    keep parity (per-row crypto replication ran before the batch recreate).
    """
    ovpn_names = [
        str(item.get("client_name"))
        for item in succeeded
        if item.get("vpn_type") == VpnType.openvpn.value and item.get("client_name")
    ]
    if not ovpn_names:
        return []

    warnings: list[str] = []
    if progress_updater:
        progress_updater(100, "Пересоздание OpenVPN-профилей…")
    db = SessionLocal()
    try:
        adapter = get_active_adapter(db)
        try:
            recreate_openvpn_profiles_after_admin_change(adapter, client_names=ovpn_names)
        except Exception as exc:
            logger.warning("CSV import: profile recreate failed: %s", exc)
            return [f"Пересоздание профилей: {exc}"]

        group = find_sync_group_for_primary(db, node_id)
        if group:
            for replica_node in get_replica_nodes(db, group):
                try:
                    copy_openvpn_profiles_from_primary(
                        adapter, get_adapter_for_node(replica_node)
                    )
                except Exception as exc:
                    logger.warning(
                        "CSV import: .ovpn copy to replica %s failed: %s",
                        replica_node.name,
                        exc,
                    )
                    warnings.append(f"Копия .ovpn на реплику {replica_node.name}: {exc}")
    finally:
        db.close()
    return warnings


def enqueue_config_csv_import(
    db: Session,
    *,
    rows: list[dict[str, str]],
    actor: User,
) -> str:
    def task_callable(progress_updater=None):
        return run_config_csv_import(
            rows=rows,
            actor_username=actor.username,
            default_owner_id=actor.id,
            progress_updater=progress_updater,
        )

    task = background_task_service.enqueue_background_task(
        "config_csv_import",
        task_callable,
        created_by_username=actor.username,
        queued_message=f"Импорт CSV: {len(rows)} клиент(ов)",
    )
    return task.id


def should_import_async(row_count: int) -> bool:
    threshold = max(1, int(get_settings().config_csv_import_async_threshold))
    return row_count >= threshold
