"""Config ACL: owned ∪ whitelist for view; mutate only for owner/admin."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import User, UserConfigAccess, UserRole, VpnConfig

_BASE_N_RE = re.compile(r"^(.+)-(\d+)$")


def _grant_matches(client_name: str, grant: str) -> bool:
    """Exact name, plan-style ``base-N``, or explicit prefix with trailing ``*``."""
    name = client_name.lower()
    g = (grant or "").strip().lower()
    if not g:
        return False
    if g.endswith("*"):
        prefix = g[:-1]
        return bool(prefix) and name.startswith(prefix)
    if name == g:
        return True
    # Grant ``ivan`` covers ``ivan-2`` … ``ivan-20`` (provisioning plan names), not ``ivanov``.
    match = _BASE_N_RE.fullmatch(name)
    if match and match.group(1) == g:
        try:
            return 2 <= int(match.group(2)) <= 20
        except ValueError:
            return False
    return False


def get_user_config_grants(db: Session, user_id: int) -> list[str]:
    rows = db.query(UserConfigAccess).filter_by(user_id=user_id).all()
    return [r.config_group for r in rows if (r.config_group or "").strip()]


def matches_user_config_grant(db: Session, user_id: int, client_name: str) -> bool:
    grants = get_user_config_grants(db, user_id)
    if not grants:
        return False
    return any(_grant_matches(client_name, g) for g in grants)


def can_view_config(user: User, config: VpnConfig, db: Session) -> bool:
    if user.role == UserRole.admin:
        return True
    if config.owner_id == user.id:
        return True
    return matches_user_config_grant(db, user.id, config.client_name)


def is_config_owner(user: User, config: VpnConfig) -> bool:
    """Admin always True; else owner. Does NOT check can_manage_configs (portal uses this)."""
    if user.role == UserRole.admin:
        return True
    return config.owner_id == user.id


def can_mutate_config(user: User, config: VpnConfig) -> bool:
    """Admin always True; else owner AND can_manage_configs."""
    if user.role == UserRole.admin:
        return True
    if not is_config_owner(user, config):
        return False
    return bool(getattr(user, "can_manage_configs", False))


def list_accessible_configs(db: Session, user: User, query_base) -> list[VpnConfig]:
    """Filter a VpnConfig query to configs the user may view."""
    if user.role == UserRole.admin:
        return query_base.order_by(VpnConfig.created_at.desc()).all()
    grants = get_user_config_grants(db, user.id)
    configs = query_base.order_by(VpnConfig.created_at.desc()).all()
    if not grants:
        return [c for c in configs if c.owner_id == user.id]
    return [c for c in configs if c.owner_id == user.id or can_view_config(user, c, db)]


def accessible_client_names(db: Session, user: User, *, node_id: int | None = None) -> set[str] | None:
    """Return None for admin (unrestricted). Otherwise owned ∪ grant-matched names on node."""
    if user.role == UserRole.admin:
        return None
    from app.services.self_service import get_owned_client_names

    owned = get_owned_client_names(db, user, node_id=node_id)
    grants = get_user_config_grants(db, user.id)
    if not grants:
        return owned

    query = db.query(VpnConfig.client_name)
    if node_id is not None:
        query = query.filter(VpnConfig.node_id == node_id)
    query = query.filter(VpnConfig.ha_primary_config_id.is_(None))
    names = {name for (name,) in query.all() if name}
    granted = {n for n in names if any(_grant_matches(n, g) for g in grants)}
    return owned | granted


def set_user_config_access(db: Session, user_id: int, config_groups: list[str]) -> None:
    db.query(UserConfigAccess).filter_by(user_id=user_id).delete()
    seen: set[str] = set()
    for raw in config_groups:
        group = (raw or "").strip()
        if not group or group.lower() in seen:
            continue
        seen.add(group.lower())
        db.add(UserConfigAccess(user_id=user_id, config_group=group))
    db.commit()


def migrate_grants_to_explicit_prefix(db: Session) -> int:
    """One-time: rewrite grants without ``*`` to ``name*`` so access stays the same after exact match."""
    from app.services.app_setting_store import _get_setting, _set_setting

    if _get_setting(db, "config_access_explicit_prefix", "") == "1":
        return 0
    rows = db.query(UserConfigAccess).all()
    changed = 0
    for row in rows:
        group = (row.config_group or "").strip()
        if not group or group.endswith("*"):
            continue
        row.config_group = f"{group}*"
        changed += 1
    _set_setting(db, "config_access_explicit_prefix", "1")
    if changed:
        db.commit()
    else:
        db.commit()
    return changed
