"""CRUD для шаблонов предоставления доступа (provisioning presets).

Шаблоны всегда опциональны: не более одного шаблона с флагом ``is_default``.
При создании/обновлении default-шаблона флаг снимается со всех остальных.
``node_ids``/``protocols`` хранятся как JSON-строки.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models import ProvisioningPreset

logger = logging.getLogger(__name__)


def _as_json_list(value: list[int] | list[str] | str | None) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        return value
    return json.dumps(list(value), ensure_ascii=False)


def list_presets(db: Session) -> list[ProvisioningPreset]:
    """Все шаблоны, отсортированные по id."""
    return db.query(ProvisioningPreset).order_by(ProvisioningPreset.id.asc()).all()


def get_preset(db: Session, preset_id: int) -> ProvisioningPreset | None:
    return db.get(ProvisioningPreset, preset_id)


def create_preset(
    db: Session,
    *,
    name: str,
    node_ids: list[int] | str | None = None,
    protocols: list[str] | str | None = None,
    config_count: int = 1,
    config_quota: int | None = None,
    traffic_limit_bytes: int | None = None,
    access_days: int | None = None,
    is_default: bool = False,
) -> ProvisioningPreset:
    if is_default:
        # Только один default: снимем флаг со всех остальных.
        (
            db.query(ProvisioningPreset)
            .filter(ProvisioningPreset.is_default.is_(True))
            .update({ProvisioningPreset.is_default: False}, synchronize_session=False)
        )
    row = ProvisioningPreset(
        name=name,
        node_ids=_as_json_list(node_ids),
        protocols=_as_json_list(protocols),
        config_count=config_count,
        config_quota=config_quota,
        traffic_limit_bytes=traffic_limit_bytes,
        access_days=access_days,
        is_default=is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_preset(
    db: Session,
    preset_id: int,
    *,
    name: str | None = None,
    node_ids: list[int] | str | None = None,
    protocols: list[str] | str | None = None,
    config_count: int | None = None,
    config_quota: int | None = None,
    traffic_limit_bytes: int | None = None,
    access_days: int | None = None,
    is_default: bool | None = None,
) -> ProvisioningPreset | None:
    row = db.get(ProvisioningPreset, preset_id)
    if row is None:
        return None
    if is_default:
        (
            db.query(ProvisioningPreset)
            .filter(ProvisioningPreset.id != preset_id)
            .filter(ProvisioningPreset.is_default.is_(True))
            .update({ProvisioningPreset.is_default: False}, synchronize_session=False)
        )
    if name is not None:
        row.name = name
    if node_ids is not None:
        row.node_ids = _as_json_list(node_ids)
    if protocols is not None:
        row.protocols = _as_json_list(protocols)
    if config_count is not None:
        row.config_count = config_count
    if config_quota is not None:
        row.config_quota = config_quota
    if traffic_limit_bytes is not None:
        row.traffic_limit_bytes = traffic_limit_bytes
    if access_days is not None:
        row.access_days = access_days
    if is_default is not None:
        row.is_default = is_default
    db.commit()
    db.refresh(row)
    return row


def delete_preset(db: Session, preset_id: int) -> bool:
    row = db.get(ProvisioningPreset, preset_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def remove_node_from_presets(db: Session, node_id: int) -> int:
    """Удаляет ``node_id`` из списка узлов каждого шаблона.

    Возвращает число изменённых шаблонов. Вызывается из ``purge_node_related``
    при удалении узла, чтобы preset'ы не ссылались на несуществующий узел.
    """
    changed = 0
    for row in db.query(ProvisioningPreset).all():
        try:
            ids = json.loads(row.node_ids or "[]")
        except (ValueError, TypeError):
            ids = []
        if not isinstance(ids, list):
            ids = []
        filtered = [int(item) for item in ids if int(item) != node_id]
        if len(filtered) != len(ids):
            row.node_ids = json.dumps(filtered, ensure_ascii=False)
            changed += 1
    if changed:
        db.commit()
    return changed
