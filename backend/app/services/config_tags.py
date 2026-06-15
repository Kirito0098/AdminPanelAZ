"""Config tag CRUD and assignment helpers."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ConfigTag, VpnConfig, VpnConfigTagLink


def list_tags(db: Session, node_id: int) -> list[tuple[ConfigTag, int]]:
    rows = (
        db.query(ConfigTag, func.count(VpnConfigTagLink.id).label("config_count"))
        .outerjoin(VpnConfigTagLink, VpnConfigTagLink.tag_id == ConfigTag.id)
        .filter(ConfigTag.node_id == node_id)
        .group_by(ConfigTag.id)
        .order_by(ConfigTag.name.asc())
        .all()
    )
    return [(tag, int(count or 0)) for tag, count in rows]


def get_tag(db: Session, node_id: int, tag_id: int) -> ConfigTag | None:
    return db.query(ConfigTag).filter(ConfigTag.node_id == node_id, ConfigTag.id == tag_id).first()


def create_tag(db: Session, node_id: int, *, name: str, color: str | None) -> ConfigTag:
    existing = (
        db.query(ConfigTag)
        .filter(ConfigTag.node_id == node_id, ConfigTag.name == name.strip())
        .first()
    )
    if existing:
        raise ValueError("Тег с таким именем уже существует")
    tag = ConfigTag(node_id=node_id, name=name.strip(), color=color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def update_tag(
    db: Session,
    tag: ConfigTag,
    *,
    name: str | None = None,
    color: str | None = None,
) -> ConfigTag:
    if name is not None:
        name = name.strip()
        conflict = (
            db.query(ConfigTag)
            .filter(
                ConfigTag.node_id == tag.node_id,
                ConfigTag.name == name,
                ConfigTag.id != tag.id,
            )
            .first()
        )
        if conflict:
            raise ValueError("Тег с таким именем уже существует")
        tag.name = name
    if color is not None:
        tag.color = color
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag: ConfigTag) -> None:
    db.delete(tag)
    db.commit()


def get_tags_for_configs(db: Session, config_ids: list[int]) -> dict[int, list[ConfigTag]]:
    if not config_ids:
        return {}
    rows = (
        db.query(VpnConfigTagLink.vpn_config_id, ConfigTag)
        .join(ConfigTag, ConfigTag.id == VpnConfigTagLink.tag_id)
        .filter(VpnConfigTagLink.vpn_config_id.in_(config_ids))
        .order_by(ConfigTag.name.asc())
        .all()
    )
    result: dict[int, list[ConfigTag]] = {cid: [] for cid in config_ids}
    for config_id, tag in rows:
        result.setdefault(config_id, []).append(tag)
    return result


def assign_tags(db: Session, config: VpnConfig, tag_ids: list[int], node_id: int) -> list[ConfigTag]:
    valid_tags = (
        db.query(ConfigTag)
        .filter(ConfigTag.node_id == node_id, ConfigTag.id.in_(tag_ids))
        .all()
    )
    valid_ids = {t.id for t in valid_tags}
    if len(valid_ids) != len(set(tag_ids)):
        raise ValueError("Один или несколько тегов не найдены")

    db.query(VpnConfigTagLink).filter(VpnConfigTagLink.vpn_config_id == config.id).delete(
        synchronize_session=False
    )
    for tag_id in valid_ids:
        db.add(VpnConfigTagLink(vpn_config_id=config.id, tag_id=tag_id))
    db.commit()
    return valid_tags


def resolve_config_ids_by_tags(
    db: Session,
    node_id: int,
    tag_ids: list[int],
    *,
    base_config_ids: list[int] | None = None,
) -> list[int]:
    if not tag_ids:
        return list(dict.fromkeys(base_config_ids or []))

    query = (
        db.query(VpnConfigTagLink.vpn_config_id)
        .join(VpnConfig, VpnConfig.id == VpnConfigTagLink.vpn_config_id)
        .filter(VpnConfig.node_id == node_id, VpnConfigTagLink.tag_id.in_(tag_ids))
    )
    from_tags = {row[0] for row in query.all()}
    if base_config_ids:
        from_tags.update(base_config_ids)
    return sorted(from_tags)
