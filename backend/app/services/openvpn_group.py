"""Per-user OpenVPN UDP/TCP folder group preference."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.constants.public_routes import (
    DEFAULT_OPENVPN_GROUP,
    OPENVPN_GROUP_LABELS,
    OPENVPN_GROUP_VARIANTS,
)
from app.models import AppSetting


def _setting_key(user_id: int) -> str:
    return f"openvpn_group:user:{user_id}"


def normalize_openvpn_group(group: str | None) -> str:
    raw = (group or "").strip() or DEFAULT_OPENVPN_GROUP
    if raw not in OPENVPN_GROUP_VARIANTS:
        return DEFAULT_OPENVPN_GROUP
    return raw


def get_user_openvpn_group(db: Session, user_id: int) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == _setting_key(user_id)).first()
    return normalize_openvpn_group(row.value if row else None)


def set_user_openvpn_group(db: Session, user_id: int, group: str) -> str:
    normalized = normalize_openvpn_group(group)
    key = _setting_key(user_id)
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = normalized
    else:
        db.add(AppSetting(key=key, value=normalized))
    db.commit()
    return normalized


def list_openvpn_groups() -> list[dict[str, str]]:
    return [
        {"key": key, "label": OPENVPN_GROUP_LABELS.get(key, key)}
        for key in OPENVPN_GROUP_VARIANTS
    ]


def filter_openvpn_profile_files(files: list[dict[str, str]], group: str) -> list[dict[str, str]]:
    allowed = OPENVPN_GROUP_VARIANTS.get(normalize_openvpn_group(group), OPENVPN_GROUP_VARIANTS[DEFAULT_OPENVPN_GROUP])
    return [item for item in files if item.get("variant") in allowed]
