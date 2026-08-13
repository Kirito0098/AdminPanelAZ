#!/usr/bin/env python3
"""Seed (or remove) demo data for proxy↔HA/server ownership UI.

Usage:
  cd /opt/AdminPanelAZ/backend && PYTHONPATH=. ../.venv/bin/python3 scripts/seed_proxy_link_demo.py
  cd /opt/AdminPanelAZ/backend && PYTHONPATH=. ../.venv/bin/python3 scripts/seed_proxy_link_demo.py --cleanup
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python3 scripts/...` from backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Node, NodeStatus, NodeSyncGroup, SyncStatus  # noqa: E402
from app.services.feature_guards import get_feature_service  # noqa: E402
from app.services.node_manager import purge_node_related, store_api_key  # noqa: E402

DEMO_META = json.dumps({"demo": True, "demo_kind": "proxy_link"})
DEMO_PREFIX = "demo-"
DEMO_GROUP_SUFFIX = " (demo)"
DEMO_API_KEY = "demo-proxy-link-key-do-not-use"


def _is_demo_node(node: Node) -> bool:
    if (node.name or "").startswith(DEMO_PREFIX):
        return True
    try:
        meta = json.loads(node.node_metadata or "{}")
    except json.JSONDecodeError:
        return False
    return bool(meta.get("demo"))


def _is_demo_group(group: NodeSyncGroup, demo_ids: set[int]) -> bool:
    if (group.name or "").endswith(DEMO_GROUP_SUFFIX):
        return True
    if group.primary_node_id in demo_ids:
        return True
    try:
        replicas = json.loads(group.replica_node_ids or "[]")
    except json.JSONDecodeError:
        replicas = []
    return any(rid in demo_ids for rid in replicas)


def cleanup(db) -> None:
    demo_nodes = [n for n in db.query(Node).all() if _is_demo_node(n)]
    demo_ids = {n.id for n in demo_nodes}
    if not demo_ids:
        # Still drop leftover demo HA groups by name
        removed_groups = 0
        for group in list(db.query(NodeSyncGroup).all()):
            if _is_demo_group(group, set()):
                db.delete(group)
                removed_groups += 1
        db.commit()
        print(f"No demo nodes left. Removed {removed_groups} demo HA group(s).")
        return

    # 1) Drop HA groups first (FK primary_node_id → nodes)
    removed_groups = 0
    for group in list(db.query(NodeSyncGroup).all()):
        if _is_demo_group(group, demo_ids):
            db.delete(group)
            removed_groups += 1
    db.flush()

    # 2) Clear ownership links to demo VPN/proxy ids
    db.query(Node).filter(Node.linked_vpn_node_id.in_(demo_ids)).update(
        {Node.linked_vpn_node_id: None},
        synchronize_session=False,
    )
    db.flush()

    # 3) Purge dependent rows, delete proxies before VPN nodes
    proxies = [n for n in demo_nodes if (n.node_kind or "vpn") == "proxy"]
    others = [n for n in demo_nodes if (n.node_kind or "vpn") != "proxy"]
    for node in proxies + others:
        purge_node_related(db, node.id)
        db.delete(node)
        db.flush()

    db.commit()
    print(
        f"Removed {len(demo_nodes)} demo node(s) and {removed_groups} HA group(s)."
    )

def seed(db) -> None:
    existing = [n for n in db.query(Node).all() if _is_demo_node(n)]
    if existing:
        print("Demo nodes already present — run with --cleanup first if you want a fresh set.")
        for n in existing:
            print(f"  id={n.id} {n.node_kind} {n.name} linked={n.linked_vpn_node_id}")
        return

    key_hash, key_enc = store_api_key("", DEMO_API_KEY)

    def add_node(*, name: str, kind: str, host: str, port: int, linked: int | None = None, dest: str | None = None) -> Node:
        node = Node(
            name=name,
            host=host,
            port=port,
            api_key_hash=key_hash,
            api_key_encrypted=key_enc,
            is_local=False,
            node_kind=kind,
            status=NodeStatus.offline,
            destination_ip=dest,
            linked_vpn_node_id=linked,
            node_metadata=DEMO_META,
        )
        db.add(node)
        db.flush()
        return node

    primary = add_node(name="demo-vpn-eu-primary", kind="vpn", host="203.0.113.10", port=9100)
    replica = add_node(name="demo-vpn-eu-replica", kind="vpn", host="203.0.113.11", port=9100)
    standalone = add_node(name="demo-vpn-standalone", kind="vpn", host="203.0.113.20", port=9100)

    group = NodeSyncGroup(
        name="Europe (demo)",
        shared_domain="eu.demo.example.com",
        shared_domain_wireguard="eu-wg.demo.example.com",
        primary_node_id=primary.id,
        replica_node_ids=json.dumps([replica.id]),
        sync_mode="manual_full",
        sync_status=SyncStatus.unknown,
    )
    db.add(group)
    db.flush()

    proxy_ha = add_node(
        name="demo-proxy-msk",
        kind="proxy",
        host="185.22.10.5",
        port=9101,
        linked=primary.id,
        dest="203.0.113.10",
    )
    proxy_solo = add_node(
        name="demo-proxy-spb",
        kind="proxy",
        host="185.22.10.8",
        port=9101,
        linked=standalone.id,
        dest="203.0.113.20",
    )
    db.commit()

    svc = get_feature_service()
    svc.update_toggles({"proxy_nodes": True})
    print("Enabled feature toggle: proxy_nodes")
    print("Seeded demo ownership scenario:")
    print(f"  HA «Europe (demo)» primary={primary.id} replica={replica.id}")
    print(f"  standalone VPN id={standalone.id}")
    print(f"  {proxy_ha.name} → HA (linked_vpn_node_id={proxy_ha.linked_vpn_node_id})")
    print(f"  {proxy_solo.name} → standalone (linked_vpn_node_id={proxy_solo.linked_vpn_node_id})")
    print("Open: Узлы or Конфигурация → Прокси. Agents are offline on purpose (UI demo only).")
    print("Cleanup: python3 scripts/seed_proxy_link_demo.py --cleanup")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/cleanup proxy link UI demo data")
    parser.add_argument("--cleanup", action="store_true", help="Remove demo nodes/groups")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.cleanup:
            cleanup(db)
        else:
            seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
