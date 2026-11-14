"""Attribution of VPN client names to the users who own their configs.

NOC monitoring and traffic monitoring operate on ``client_name`` values, while
the provisioning module groups configs by user. These helpers resolve the owner
of a client name once per request so both pages can offer a per-user view
without an N+1 query per connection or traffic row.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User, VpnConfig


@dataclass(frozen=True)
class ClientOwner:
    """Minimal owner identity attached to monitoring rows."""

    user_id: int
    username: str


OwnerMap = dict[tuple[int, str], ClientOwner]


def _normalize_name(client_name: str | None) -> str:
    return (client_name or "").strip().lower()


def load_client_owners(db: Session, node_ids: Iterable[int] | None = None) -> OwnerMap:
    """Map ``(node_id, lower(client_name))`` to the owning user.

    ``node_ids=None`` loads owners for every node. HA shadow configs live on
    their own node, so a per-node key is enough to attribute a live connection
    or a traffic row that was aggregated per node.
    """
    query = db.query(
        VpnConfig.node_id,
        VpnConfig.client_name,
        User.id,
        User.username,
    ).join(User, User.id == VpnConfig.owner_id)
    if node_ids is not None:
        ids = sorted({int(node_id) for node_id in node_ids})
        if not ids:
            return {}
        query = query.filter(VpnConfig.node_id.in_(ids))

    owners: OwnerMap = {}
    for node_id, client_name, user_id, username in query.all():
        name = _normalize_name(client_name)
        if not name:
            continue
        key = (int(node_id), name)
        # A node may hold both OpenVPN and WireGuard configs for one name; the
        # owner is the same, so the first row wins and duplicates are cheap.
        owners.setdefault(key, ClientOwner(user_id=int(user_id), username=username))
    return owners


def find_client_owner(
    owners: OwnerMap,
    node_ids: Iterable[int],
    client_name: str | None,
) -> ClientOwner | None:
    """Find the owner of ``client_name`` on any of ``node_ids`` (HA scope)."""
    name = _normalize_name(client_name)
    if not name:
        return None
    for node_id in node_ids:
        owner = owners.get((int(node_id), name))
        if owner is not None:
            return owner
    return None


def owner_fields(owner: ClientOwner | None) -> dict[str, int | str | None]:
    """Response fields shared by monitoring and traffic schemas."""
    return {
        "owner_id": owner.user_id if owner else None,
        "owner_username": owner.username if owner else None,
    }


def owner_fields_for_viewer(
    owner: ClientOwner | None,
    *,
    viewer_id: int | None,
    is_admin: bool,
) -> dict[str, int | str | None]:
    """Owner fields respecting the config ACL privacy rule.

    Admins see every owner; a user sees ownership only for their own configs.
    Grantees (view access to somebody else's config group) must not learn the
    owner id or username, so their rows fall back to the "unowned" bucket.
    """
    if owner is None:
        return owner_fields(None)
    if is_admin or (viewer_id is not None and owner.user_id == viewer_id):
        return owner_fields(owner)
    return owner_fields(None)
