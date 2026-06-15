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
from app.models import User, UserRole, VpnConfig, VpnType
from app.services.background_tasks import background_task_service
from app.services.feature_guards import get_feature_service, require_vpn_type
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.client_sync import maybe_replicate_create
from app.services.node_sync.groups import find_sync_group_for_primary

logger = logging.getLogger(__name__)

CSV_HEADERS = (
    "id",
    "client_name",
    "vpn_type",
    "owner_username",
    "cert_expire_days",
    "description",
    "created_at",
    "updated_at",
)

IMPORT_HEADERS = ("client_name", "vpn_type", "owner_username", "cert_expire_days", "description")


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
        writer.writerow(
            [
                config.id,
                config.client_name,
                config.vpn_type.value,
                owner_username or "",
                config.cert_expire_days if config.cert_expire_days is not None else "",
                config.description or "",
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
    missing = [h for h in IMPORT_HEADERS[:2] if h not in normalized_fields]
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

    group = find_sync_group_for_primary(db, node_id)
    if group:
        maybe_replicate_create(db, node_id=node_id, primary_config=config)

    return {"line": row.get("_line"), "client_name": client_name, "config_id": config.id, "ok": True}


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

    summary = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "actor": actor_username,
    }
    msg = f"Импорт CSV: {len(succeeded)}/{total}, ошибок: {len(failed)}"
    return {
        "message": msg,
        "output": json.dumps(summary, ensure_ascii=False),
    }


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
