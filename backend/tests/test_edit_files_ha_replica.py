import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from app.routers.edit_files import FileContentUpdate, save_edit_file


def _ha_replica_context():
    replica = MagicMock()
    replica.id = 2
    replica.name = "replica-1"

    group = MagicMock()
    group.id = 1
    group.name = "test-ha"
    group.shared_domain = "vpn.example.com"
    group.primary_node_id = 1

    primary = MagicMock()
    primary.id = 1
    primary.name = "primary-1"

    db = MagicMock()

    def fake_get(model, node_id):
        if node_id == 2:
            return replica
        if node_id == 1:
            return primary
        return None

    db.get.side_effect = fake_get
    return db, replica, group


def test_save_edit_file_returns_403_on_ha_replica():
    db, replica, group = _ha_replica_context()
    admin = MagicMock()
    payload = FileContentUpdate(content="127.0.0.1 example.test")

    with patch("app.services.node_manager.get_active_node", return_value=replica):
        with patch("app.services.node_sync.groups.find_group_for_node", return_value=group):
            with pytest.raises(HTTPException) as exc:
                save_edit_file("hosts", payload, db=db, current_user=admin)

    assert exc.value.status_code == 403
    assert "replica" in exc.value.detail.lower()
    assert "test-ha" in exc.value.detail
