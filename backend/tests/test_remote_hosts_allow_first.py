"""Tests for POST /nodes/{id}/remote-hosts/allow-first (06c)."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers.nodes import allow_first_remote_host
from app.services.openvpn_remote_hosts import append_host_to_allow_ips, hosts_to_json


def test_append_host_to_empty():
    new, added = append_host_to_allow_ips("", "1.2.3.4")
    assert added is True
    assert new == "1.2.3.4\n"


def test_append_host_to_existing_body():
    new, added = append_host_to_allow_ips("10.0.0.1\n", "1.2.3.4")
    assert added is True
    assert new == "10.0.0.1\n1.2.3.4\n"


def test_append_skips_duplicate():
    content = "# comment\n1.2.3.4\n"
    new, added = append_host_to_allow_ips(content, "1.2.3.4")
    assert added is False
    assert new == content


def test_append_ignores_comment_lookalike():
    content = "# 1.2.3.4\n"
    new, added = append_host_to_allow_ips(content, "1.2.3.4")
    assert added is True
    assert "1.2.3.4" in new.splitlines()


def _node(*, hosts_json: str | None):
    node = MagicMock()
    node.id = 7
    node.openvpn_remote_hosts = hosts_json
    return node


def _db_with_node(node):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.first.return_value = node
    db.query.return_value = query
    return db


def test_allow_first_empty_hosts_400(monkeypatch):
    db = _db_with_node(_node(hosts_json=None))
    monkeypatch.setattr("app.routers.nodes.get_adapter_for_node", MagicMock())

    with pytest.raises(HTTPException) as exc:
        allow_first_remote_host(
            node_id=7,
            request=MagicMock(),
            admin=MagicMock(id=1, username="admin"),
            db=db,
        )
    assert exc.value.status_code == 400
    assert "адреса" in exc.value.detail


def test_allow_first_adds_and_applies(monkeypatch):
    node = _node(hosts_json=hosts_to_json(["10.1.2.3", "vpn.example.com"]))
    db = _db_with_node(node)
    adapter = MagicMock()
    adapter.read_config_file.return_value = "192.168.0.1\n"
    adapter.apply_config_changes.return_value = "ok"
    replicate = MagicMock()
    monkeypatch.setattr("app.routers.nodes.get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr("app.routers.nodes.settings.audit_log_enabled", False)
    monkeypatch.setattr("app.routers.nodes.maybe_replicate_config_files", replicate)

    result = allow_first_remote_host(
        node_id=7,
        request=MagicMock(),
        admin=MagicMock(id=1, username="admin"),
        db=db,
    )
    assert result.added is True
    assert result.host == "10.1.2.3"
    adapter.read_config_file.assert_called_once_with("allow-ips.txt")
    adapter.write_config_file.assert_called_once_with("allow-ips.txt", "192.168.0.1\n10.1.2.3\n")
    adapter.apply_config_changes.assert_called_once()
    replicate.assert_called_once_with(
        db,
        node_id=7,
        file_keys=["allow_ips"],
        run_doall=True,
        content_overrides={"allow_ips": "192.168.0.1\n10.1.2.3\n"},
    )


def test_allow_first_duplicate_skips_write(monkeypatch):
    node = _node(hosts_json=hosts_to_json(["10.1.2.3"]))
    db = _db_with_node(node)
    adapter = MagicMock()
    adapter.read_config_file.return_value = "10.1.2.3\nother\n"
    replicate = MagicMock()
    monkeypatch.setattr("app.routers.nodes.get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr("app.routers.nodes.settings.audit_log_enabled", False)
    monkeypatch.setattr("app.routers.nodes.maybe_replicate_config_files", replicate)

    result = allow_first_remote_host(
        node_id=7,
        request=MagicMock(),
        admin=MagicMock(id=1, username="admin"),
        db=db,
    )
    assert result.added is False
    assert result.host == "10.1.2.3"
    assert result.detail == "уже есть"
    adapter.write_config_file.assert_not_called()
    adapter.apply_config_changes.assert_not_called()
    replicate.assert_not_called()


def test_allow_first_apply_failure_is_warning(monkeypatch):
    node = _node(hosts_json=hosts_to_json(["10.1.2.3"]))
    db = _db_with_node(node)
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.apply_config_changes.side_effect = RuntimeError("doall failed")
    replicate = MagicMock()
    monkeypatch.setattr("app.routers.nodes.get_adapter_for_node", lambda _n: adapter)
    monkeypatch.setattr("app.routers.nodes.settings.audit_log_enabled", False)
    monkeypatch.setattr("app.routers.nodes.maybe_replicate_config_files", replicate)

    result = allow_first_remote_host(
        node_id=7,
        request=MagicMock(),
        admin=MagicMock(id=1, username="admin"),
        db=db,
    )
    assert result.added is True
    assert result.warnings
    assert "doall" in result.warnings[0].lower() or "ошибка" in result.warnings[0]
    adapter.write_config_file.assert_called_once()
    replicate.assert_called_once()
