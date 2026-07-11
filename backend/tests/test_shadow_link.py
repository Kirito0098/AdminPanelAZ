from unittest.mock import MagicMock

import pytest

from app.models import VpnType
from app.services.node_sync import client_sync, shadow_link
from app.services.node_sync.replicate import upsert_shadow_config


def _make_config(
    *,
    config_id: int,
    node_id: int,
    client_name: str,
    vpn_type: VpnType = VpnType.wireguard,
    ha_primary_config_id: int | None = None,
    sync_group_id: int | None = None,
) -> MagicMock:
    config = MagicMock()
    config.id = config_id
    config.node_id = node_id
    config.client_name = client_name
    config.vpn_type = vpn_type
    config.ha_primary_config_id = ha_primary_config_id
    config.sync_group_id = sync_group_id
    config.owner_id = 1
    config.cert_expire_days = None
    config.description = None
    return config


class _QueryStub:
    def __init__(self, items: list[MagicMock]):
        self._items = items

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


def test_upsert_shadow_config_links_existing():
    db = MagicMock()
    group = MagicMock()
    group.id = 10
    primary = _make_config(config_id=1, node_id=1, client_name="alice")
    existing = _make_config(config_id=2, node_id=2, client_name="alice")

    shadow = upsert_shadow_config(db, group, 2, primary, existing)

    assert shadow is existing
    assert existing.sync_group_id == 10
    assert existing.ha_primary_config_id == 1
    db.add.assert_not_called()


def test_upsert_shadow_config_creates_new():
    db = MagicMock()
    group = MagicMock()
    group.id = 10
    primary = _make_config(config_id=1, node_id=1, client_name="bob")

    shadow = upsert_shadow_config(db, group, 2, primary, None)

    db.add.assert_called_once()
    db.flush.assert_called_once()
    assert shadow.node_id == 2
    assert shadow.ha_primary_config_id == 1
    assert shadow.sync_group_id == 10


def test_link_shadow_configs_links_existing_replica_row(monkeypatch):
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1
    group.sync_mode = "auto"

    replica = MagicMock()
    replica.id = 2
    replica.name = "replica-1"

    primary = _make_config(config_id=1, node_id=1, client_name="alice")
    replica_row = _make_config(config_id=2, node_id=2, client_name="alice")

    db = MagicMock()

    def fake_query(model):
        if model.__name__ == "VpnConfig":
            call_count = fake_query.call_count
            fake_query.call_count += 1
            if call_count == 0:
                return _QueryStub([primary])
            if call_count == 1:
                return _QueryStub([replica_row])
            if call_count == 2:
                return _QueryStub([])
        raise AssertionError(f"unexpected query for {model}")

    fake_query.call_count = 0
    db.query.side_effect = fake_query

    monkeypatch.setattr("app.services.node_sync.shadow_link.is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr("app.services.node_sync.shadow_link.get_replica_nodes", lambda _db, _group: [replica])

    result = shadow_link.link_shadow_configs_for_group(db, group)

    assert len(result["linked"]) == 1
    assert result["linked"][0]["client_name"] == "alice"
    assert replica_row.ha_primary_config_id == 1
    assert primary.sync_group_id == 10


def test_link_shadow_configs_creates_missing_replica_row(monkeypatch):
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1
    group.sync_mode = "auto"

    replica = MagicMock()
    replica.id = 2
    replica.name = "replica-1"
    primary = _make_config(config_id=1, node_id=1, client_name="carol")

    db = MagicMock()

    def fake_query(model):
        if model.__name__ == "VpnConfig":
            call_count = fake_query.call_count
            fake_query.call_count += 1
            if call_count == 0:
                return _QueryStub([primary])
            if call_count == 1:
                return _QueryStub([])
            if call_count == 2:
                return _QueryStub([])
        raise AssertionError(f"unexpected query for {model}")

    fake_query.call_count = 0
    db.query.side_effect = fake_query

    monkeypatch.setattr("app.services.node_sync.shadow_link.is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr("app.services.node_sync.shadow_link.get_replica_nodes", lambda _db, _group: [replica])

    result = shadow_link.link_shadow_configs_for_group(db, group)

    assert len(result["created"]) == 1
    db.add.assert_called_once()


def test_link_shadow_configs_skips_already_linked(monkeypatch):
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1

    replica = MagicMock()
    replica.id = 2
    replica.name = "replica-1"

    primary = _make_config(config_id=1, node_id=1, client_name="dave")
    replica_row = _make_config(config_id=2, node_id=2, client_name="dave", ha_primary_config_id=1)

    db = MagicMock()

    def fake_query(model):
        if model.__name__ == "VpnConfig":
            call_count = fake_query.call_count
            fake_query.call_count += 1
            if call_count == 0:
                return _QueryStub([primary])
            if call_count == 1:
                return _QueryStub([replica_row])
            if call_count == 2:
                return _QueryStub([])
        raise AssertionError(f"unexpected query for {model}")

    fake_query.call_count = 0
    db.query.side_effect = fake_query

    monkeypatch.setattr("app.services.node_sync.shadow_link.is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr("app.services.node_sync.shadow_link.get_replica_nodes", lambda _db, _group: [replica])

    result = shadow_link.link_shadow_configs_for_group(db, group)

    assert len(result["already_linked"]) == 1
    assert result["linked"] == []
    assert result["created"] == []


def test_link_shadow_configs_records_conflict(monkeypatch):
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1

    replica = MagicMock()
    replica.id = 2
    replica.name = "replica-1"

    primary = _make_config(config_id=1, node_id=1, client_name="eve")
    replica_row = _make_config(config_id=2, node_id=2, client_name="eve", ha_primary_config_id=99)

    db = MagicMock()

    def fake_query(model):
        if model.__name__ == "VpnConfig":
            call_count = fake_query.call_count
            fake_query.call_count += 1
            if call_count == 0:
                return _QueryStub([primary])
            if call_count == 1:
                return _QueryStub([replica_row])
            if call_count == 2:
                return _QueryStub([replica_row])
        raise AssertionError(f"unexpected query for {model}")

    fake_query.call_count = 0
    db.query.side_effect = fake_query

    monkeypatch.setattr("app.services.node_sync.shadow_link.is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr("app.services.node_sync.shadow_link.get_replica_nodes", lambda _db, _group: [replica])

    result = shadow_link.link_shadow_configs_for_group(db, group)

    assert len(result["conflicts"]) == 1
    assert result["linked"] == []


def test_link_shadow_configs_detects_orphan_replica(monkeypatch):
    group = MagicMock()
    group.id = 10
    group.primary_node_id = 1

    replica = MagicMock()
    replica.id = 2
    replica.name = "replica-1"

    primary = _make_config(config_id=1, node_id=1, client_name="frank")
    orphan = _make_config(config_id=3, node_id=2, client_name="ghost")

    db = MagicMock()

    def fake_query(model):
        if model.__name__ == "VpnConfig":
            call_count = fake_query.call_count
            fake_query.call_count += 1
            if call_count == 0:
                return _QueryStub([primary])
            if call_count == 1:
                return _QueryStub([])
            if call_count == 2:
                return _QueryStub([orphan])
        raise AssertionError(f"unexpected query for {model}")

    fake_query.call_count = 0
    db.query.side_effect = fake_query

    monkeypatch.setattr("app.services.node_sync.shadow_link.is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr("app.services.node_sync.shadow_link.get_replica_nodes", lambda _db, _group: [replica])

    result = shadow_link.link_shadow_configs_for_group(db, group)

    assert len(result["orphan_replica"]) == 1
    assert result["orphan_replica"][0]["client_name"] == "ghost"


def test_link_shadow_configs_noop_in_manual_full(monkeypatch):
    monkeypatch.setattr("app.services.node_sync.shadow_link.is_auto_sync_enabled", lambda _group: False)

    result = shadow_link.link_shadow_configs_for_group(MagicMock(), MagicMock())

    assert result == {
        "linked": [],
        "created": [],
        "already_linked": [],
        "orphan_replica": [],
        "conflicts": [],
    }


def test_format_shadow_link_warning():
    assert shadow_link.format_shadow_link_warning({"conflicts": [], "orphan_replica": []}) is None
    warning = shadow_link.format_shadow_link_warning(
        {
            "conflicts": [{"client_name": "x"}],
            "orphan_replica": [{"client_name": "Test"}],
        }
    )
    assert warning is not None
    assert "конфликты shadow" in warning
    assert "Test" in warning


def test_maybe_replicate_delete_fallback_when_no_shadows(monkeypatch):
    primary_config = MagicMock()
    primary_config.id = 1
    group = MagicMock()

    delete_result = {"deleted": [], "errors": [], "skipped": False}
    crypto_result = {"successes": [{"node_id": 2}], "errors": []}

    monkeypatch.setattr(client_sync, "find_sync_group_for_primary", lambda _db, _node_id: group)
    monkeypatch.setattr(client_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(client_sync, "replicate_client_delete", lambda _db, _group, _cfg: delete_result)
    monkeypatch.setattr(
        client_sync,
        "replicate_primary_crypto_to_replicas",
        lambda _db, _group, _cfg: crypto_result,
    )

    result = client_sync.maybe_replicate_delete(MagicMock(), node_id=1, primary_config=primary_config)

    assert result is not None
    assert result["fallback"] is True
    assert result["deleted"] == [{"node_id": 2}]


def test_maybe_replicate_delete_skips_fallback_when_shadow_deleted(monkeypatch):
    primary_config = MagicMock()
    group = MagicMock()
    delete_result = {"deleted": [{"node_id": 2}], "errors": [], "skipped": False}

    monkeypatch.setattr(client_sync, "find_sync_group_for_primary", lambda _db, _node_id: group)
    monkeypatch.setattr(client_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(client_sync, "replicate_client_delete", lambda _db, _group, _cfg: delete_result)
    fallback = MagicMock()
    monkeypatch.setattr(client_sync, "replicate_primary_crypto_to_replicas", fallback)

    result = client_sync.maybe_replicate_delete(MagicMock(), node_id=1, primary_config=primary_config)

    assert result == delete_result
    fallback.assert_not_called()
