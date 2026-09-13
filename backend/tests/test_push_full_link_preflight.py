from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.node_sync import push_full


def test_preflight_push_full_links_blocks_auth_failure():
    group = SimpleNamespace(primary_node_id=1, replica_node_ids="[2]")
    primary = SimpleNamespace(id=1, name="primary")
    replica = SimpleNamespace(id=2, name="replica")

    def fake_get(model, node_id):
        return {1: primary, 2: replica}.get(node_id)

    db = MagicMock()
    db.get.side_effect = fake_get

    def fake_health(node):
        if node.id == 2:
            return {
                "status": "offline",
                "error": "bad key",
                "error_code": "node_auth",
                "link_error": {
                    "code": "node_auth",
                    "message": "bad key",
                    "hint": "check key",
                },
            }
        return {"status": "online"}

    with patch.object(push_full, "parse_replica_node_ids", return_value=[2]):
        with patch("app.services.node_manager.check_node_health", side_effect=fake_health):
            blockers = push_full.preflight_push_full_links(db, group)

    assert len(blockers) == 1
    assert blockers[0]["code"] == "node_auth"
    assert blockers[0]["node_name"] == "replica"


def test_run_push_full_aborts_on_link_preflight(monkeypatch):
    group = SimpleNamespace(
        id=9,
        primary_node_id=1,
        replica_node_ids="[2]",
        sync_status=None,
        last_sync_error=None,
    )
    db = MagicMock()
    monkeypatch.setattr(push_full, "validate_sync_group_payload", lambda *a, **k: [])
    monkeypatch.setattr(
        push_full,
        "preflight_push_full_links",
        lambda *a, **k: [
            {
                "node_id": 2,
                "node_name": "replica",
                "code": "node_tls_mismatch",
                "message": "tls",
                "hint": "fix tls",
            }
        ],
    )
    try:
        push_full.run_push_full(db, group, auto_verify=False)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "проблем" in str(exc).lower() or "tls" in str(exc).lower()
        assert "node_tls_mismatch" in str(exc)
