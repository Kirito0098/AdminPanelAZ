"""Сводка по фактическим конфигам владельца.

Нужна абонентам без плана: созданным «из существующих» или получившим конфиг
позже. У них нет ``client_base_name`` и назначений узлов, поэтому карточка и
список показывали нули — сводка берётся из ``VpnConfig.owner_id``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import VpnConfig


@dataclass(frozen=True)
class OwnedConfigsSummary:
    """Узлы, протоколы и имена конфигов одного владельца."""

    base_name: str | None
    name_count: int
    protocols: list[str]
    node_ids: list[int]


def summarize_owned_configs(configs: list[VpnConfig]) -> OwnedConfigsSummary:
    """Свести конфиги владельца без обращения к БД.

    ``base_name`` — самое частое имя (при равенстве — первое по алфавиту),
    чтобы подпись «База» совпадала с именем, которое видно в файлах.
    """
    names = Counter(
        (config.client_name or "").strip()
        for config in configs
        if (config.client_name or "").strip()
    )
    base_name = min(names.items(), key=lambda item: (-item[1], item[0]))[0] if names else None
    return OwnedConfigsSummary(
        base_name=base_name,
        name_count=len(names),
        protocols=sorted({config.vpn_type.value for config in configs}),
        node_ids=sorted({config.node_id for config in configs}),
    )


def owned_configs_summaries(
    db: Session, user_ids: list[int]
) -> dict[int, OwnedConfigsSummary]:
    """Сводка по primary-конфигам нескольких владельцев — одним запросом."""
    unique_ids = list(dict.fromkeys(user_ids))
    if not unique_ids:
        return {}
    rows = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.owner_id.in_(unique_ids),
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    by_owner: dict[int, list[VpnConfig]] = {}
    for config in rows:
        by_owner.setdefault(config.owner_id, []).append(config)
    return {owner_id: summarize_owned_configs(configs) for owner_id, configs in by_owner.items()}
