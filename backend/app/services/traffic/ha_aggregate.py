"""HA (Sync Group) scope resolution for traffic monitoring.

The traffic tables (``UserTrafficStatProtocol`` / ``UserTrafficSample`` /
``TrafficSessionState``) store rows per ``node_id``. A single logical client in
a Node Sync Group can accumulate traffic on several nodes (primary/replica
failover). For the *Traffic monitoring* page we want to present the **sum**
across all member nodes of the group that the active node belongs to.

This module resolves the set of node ids that should be aggregated together and
exposes the HA metadata badge for those rows. It intentionally reuses the
existing Sync Group helpers (``find_sync_group_containing_node``,
``group_member_node_ids``, ``build_ha_metadata``) instead of duplicating the
live-connection lookup used by the NOC overview (which collapses to a single
node via ``max`` rather than summing).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Node
from app.schemas import VpnConfigHaInfo
from app.services.node_sync.groups import (
    build_ha_metadata,
    find_sync_group_containing_node,
    group_member_node_ids,
)


@dataclass
class TrafficScope:
    """Resolved set of nodes whose traffic should be aggregated together."""

    node_ids: list[int]
    node_names: dict[int, str] = field(default_factory=dict)
    ha_info: VpnConfigHaInfo | None = None
    group_name: str | None = None

    @property
    def is_ha(self) -> bool:
        return self.ha_info is not None and len(self.node_ids) > 1

    def node_name(self, node_id: int) -> str:
        return self.node_names.get(node_id) or f"node-{node_id}"


def resolve_traffic_scope(db: Session, node_id: int) -> TrafficScope:
    """Resolve the traffic aggregation scope for ``node_id``.

    - Node not in a Sync Group → solo scope (``[node_id]``), no HA metadata.
    - Node in a Sync Group → all member node ids (primary + replicas) with the
      group's HA badge metadata, regardless of whether the active node is the
      primary or a replica.
    """
    group, _role = find_sync_group_containing_node(db, node_id)
    if not group:
        node = db.get(Node, node_id)
        names = {node_id: node.name} if node else {}
        return TrafficScope(node_ids=[node_id], node_names=names)

    member_ids = sorted(group_member_node_ids(group))
    nodes = db.query(Node).filter(Node.id.in_(member_ids)).all()
    node_names = {node.id: node.name for node in nodes}
    meta = build_ha_metadata(group)
    ha_info = VpnConfigHaInfo(**meta) if meta else None
    return TrafficScope(
        node_ids=member_ids,
        node_names=node_names,
        ha_info=ha_info,
        group_name=group.name,
    )
