from __future__ import annotations

from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.models import Node
from app.services.openvpn_remote_hosts import apply_openvpn_remote_hosts, parse_hosts_json


def load_node_remote_hosts(db: Session, node_id: int | None) -> list[str]:
    if not node_id:
        return []
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return []
    return parse_hosts_json(node.openvpn_remote_hosts)


def read_profile_file_for_delivery(adapter, path: str, hosts: list[str]) -> str:
    raw = adapter.read_profile_file(path)
    # Match .ovpn case-insensitively on final suffix
    name = PurePosixPath(path.replace("\\", "/")).name
    if not name.lower().endswith(".ovpn"):
        return raw
    return apply_openvpn_remote_hosts(raw, hosts)
