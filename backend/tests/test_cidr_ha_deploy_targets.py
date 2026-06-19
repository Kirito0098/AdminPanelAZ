"""HA-aware deploy target resolution tests (step D.1 audit)."""

from __future__ import annotations

import pytest

from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus
from app.services.cidr.pipeline.orchestrator import resolve_deploy_targets
from app.services.node_sync.groups import serialize_replica_node_ids


@pytest.fixture()
def deploy_env(api_test_env):
    from app.services.cidr.cidr_tasks import _CIDR_TASKS, enable_memory_backend_for_tests

    enable_memory_backend_for_tests(True)
    _CIDR_TASKS.clear()
    yield api_test_env
    _CIDR_TASKS.clear()
    enable_memory_backend_for_tests(False)


def _add_remote_node(session, name, node_status=NodeStatus.online):
    node = Node(
        name=name,
        host=f"{name}.example.com",
        port=9100,
        is_local=False,
        status=node_status,
        api_key_hash="hash",
        api_key_encrypted="enc",
    )
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def test_resolve_deploy_targets_default_is_active_node_only(deploy_env):
    """Default path does not expand HA replicas — only active node."""
    session = deploy_env["session_factory"]()
    primary = session.query(Node).filter_by(is_local=True).one()
    replica = _add_remote_node(session, "ha-replica", NodeStatus.online)

    group = NodeSyncGroup(
        name="HA deploy",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
        sync_status=SyncStatus.synced,
    )
    session.add(group)
    session.commit()

    nodes, skipped = resolve_deploy_targets(session)
    assert skipped == []
    assert len(nodes) == 1
    assert nodes[0].id == primary.id
