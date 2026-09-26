"""WARP/RPZ config files and Knot Resolver custom.lua in the file editor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers import edit_files
from app.services import edit_files_transfer
from app.services.antizapret import AntiZapretService
from app.services.file_editor import ConfigFileUnsupportedError
from app.services.node_adapter import RemoteNodeAdapter


def _completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


@pytest.fixture
def service(tmp_path: Path) -> AntiZapretService:
    svc = AntiZapretService(base_path=tmp_path / "antizapret")
    svc.config_dir.mkdir(parents=True)
    svc.knot_resolver_dir = tmp_path / "knot-resolver"
    svc.knot_resolver_dir.mkdir()
    return svc


@pytest.fixture
def systemctl(monkeypatch):
    run = MagicMock(return_value=_completed(0))
    monkeypatch.setattr("app.services.antizapret.subprocess.run", run)
    return run


def _restarted_units(run: MagicMock) -> list[str]:
    return [call.args[0][2] for call in run.call_args_list if call.args[0][:2] == ["systemctl", "restart"]]


@pytest.mark.parametrize(
    "filename",
    [
        "include-warp-hosts.txt",
        "exclude-warp-hosts.txt",
        "deny-rpz.txt",
        "deny2-rpz.txt",
        "warp-rpz.txt",
        "proxy-rpz.txt",
    ],
)
def test_warp_and_rpz_files_live_in_config_dir(service: AntiZapretService, systemctl, filename: str):
    service.write_config_file(filename, "example.com\n")

    assert (service.config_dir / filename).read_text(encoding="utf-8") == "example.com\n"
    assert service.read_config_file(filename) == "example.com\n"
    systemctl.assert_not_called()


@pytest.mark.parametrize("filename", ["kresd.conf", "../setup", "custom3.lua"])
def test_files_outside_allowlist_are_rejected(service: AntiZapretService, filename: str):
    with pytest.raises(HTTPException) as read_exc:
        service.read_config_file(filename)
    with pytest.raises(HTTPException) as write_exc:
        service.write_config_file(filename, "x")

    assert read_exc.value.status_code == write_exc.value.status_code == 400


@pytest.mark.parametrize(("filename", "unit"), [("custom.lua", "kresd@1"), ("custom2.lua", "kresd@2")])
def test_kresd_custom_is_written_to_knot_resolver_and_restarts_its_instance(
    service: AntiZapretService, systemctl, filename: str, unit: str
):
    service.write_config_file(filename, "policy.add(policy.all(policy.PASS))\n")

    assert (service.knot_resolver_dir / filename).read_text(encoding="utf-8") == "policy.add(policy.all(policy.PASS))\n"
    assert not (service.config_dir / filename).exists()
    assert _restarted_units(systemctl) == [unit]
    assert service.read_config_file(filename) == "policy.add(policy.all(policy.PASS))\n"


def test_unchanged_kresd_custom_does_not_restart(service: AntiZapretService, systemctl):
    (service.knot_resolver_dir / "custom.lua").write_text("-- same\n", encoding="utf-8")

    service.write_config_file("custom.lua", "-- same\n")

    systemctl.assert_not_called()


def test_failed_kresd_restart_restores_previous_file(service: AntiZapretService, systemctl):
    path = service.knot_resolver_dir / "custom.lua"
    path.write_text("-- good\n", encoding="utf-8")
    systemctl.side_effect = lambda args, **_: (
        _completed(1, "Job for kresd@1.service failed")
        if args[:2] == ["systemctl", "restart"] and path.read_text(encoding="utf-8") == "broken(\n"
        else _completed(0)
    )

    with pytest.raises(HTTPException) as exc:
        service.write_config_file("custom.lua", "broken(\n")

    assert exc.value.status_code == 400
    assert "kresd@1" in exc.value.detail
    assert "прежний файл восстановлен" in exc.value.detail
    assert "После отката" not in exc.value.detail
    assert path.read_text(encoding="utf-8") == "-- good\n"
    assert _restarted_units(systemctl) == ["kresd@1", "kresd@1"]


def test_failed_kresd_restart_without_previous_file_leaves_empty_file(service: AntiZapretService, systemctl):
    path = service.knot_resolver_dir / "custom2.lua"
    systemctl.side_effect = lambda args, **_: (
        _completed(1, "failed")
        if args[:2] == ["systemctl", "restart"] and path.read_text(encoding="utf-8")
        else _completed(0)
    )

    with pytest.raises(HTTPException):
        service.write_config_file("custom2.lua", "broken(\n")

    assert path.read_text(encoding="utf-8") == ""


def _remote_adapter(error: HTTPException) -> RemoteNodeAdapter:
    adapter = RemoteNodeAdapter(host="127.0.0.1", port=9100, api_key="k" * 32)
    adapter._request = MagicMock(side_effect=error)
    return adapter


@pytest.mark.parametrize("filename", ["warp-rpz.txt", "custom.lua"])
def test_old_agent_rejection_of_new_file_becomes_update_hint(filename: str):
    adapter = _remote_adapter(HTTPException(status_code=400, detail="Недопустимый конфигурационный файл"))

    with pytest.raises(ConfigFileUnsupportedError) as read_exc:
        adapter.read_config_file(filename)
    with pytest.raises(ConfigFileUnsupportedError) as write_exc:
        adapter.write_config_file(filename, "x")

    assert read_exc.value.status_code == 503
    assert "1.10.0" in write_exc.value.detail
    assert filename in write_exc.value.detail


def test_old_agent_rejection_of_known_file_is_not_rewritten():
    adapter = _remote_adapter(HTTPException(status_code=400, detail="Недопустимый конфигурационный файл"))

    with pytest.raises(HTTPException) as exc:
        adapter.read_config_file("include-hosts.txt")

    assert not isinstance(exc.value, ConfigFileUnsupportedError)
    assert exc.value.status_code == 400


def test_kresd_custom_write_gets_longer_timeout():
    adapter = RemoteNodeAdapter(host="127.0.0.1", port=9100, api_key="k" * 32)
    adapter._request = MagicMock(return_value={})

    adapter.write_config_file("custom.lua", "x")
    lua_timeout = adapter._request.call_args.kwargs["timeout"]
    adapter.write_config_file("include-hosts.txt", "x")

    assert lua_timeout > adapter._request.call_args.kwargs["timeout"]


def _vpn_node(node_id: int) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = f"node-{node_id}"
    node.node_kind = "vpn"
    return node


def _transfer(monkeypatch, target: MagicMock, **kwargs):
    source_node, target_node = _vpn_node(1), _vpn_node(2)
    source = MagicMock()
    source.read_config_file.side_effect = lambda fname: f"{fname} content"
    adapters = {1: source, 2: target}
    monkeypatch.setattr(edit_files_transfer, "get_active_node", lambda _db: source_node)
    monkeypatch.setattr(edit_files_transfer, "get_adapter_for_node", lambda node: adapters[node.id])
    monkeypatch.setattr(edit_files_transfer, "resolve_deploy_targets", lambda _db, **_: ([target_node], []))
    return edit_files_transfer.run_edit_files_transfer(MagicMock(), target_node_ids=[2], **kwargs)


def _old_agent_target() -> MagicMock:
    target = MagicMock()

    def write(fname, _content):
        if fname == "warp-rpz.txt":
            raise ConfigFileUnsupportedError(fname)

    target.write_config_file.side_effect = write
    return target


def test_transfer_skip_unsupported_keeps_node_successful(monkeypatch):
    target = _old_agent_target()

    result = _transfer(monkeypatch, target, file_keys=["include_hosts", "warp_rpz"], skip_unsupported=True)

    (entry,) = result["per_node"]
    assert entry["status"] == "success"
    assert entry["transferred_files"] == ["include-hosts.txt"]
    assert entry["unsupported_files"] == ["warp-rpz.txt"]


def test_manual_transfer_reports_unsupported_file(monkeypatch):
    target = _old_agent_target()

    result = _transfer(monkeypatch, target, file_keys=["include_hosts", "warp_rpz"])

    (entry,) = result["per_node"]
    assert entry["status"] == "failed"
    assert entry["failed"][0]["file"] == "warp-rpz.txt"
    assert "node agent" in entry["error"]


def test_transfer_of_only_kresd_custom_skips_doall(monkeypatch):
    target = MagicMock()

    result = _transfer(monkeypatch, target, file_keys=["kresd_custom", "kresd_custom2"], run_doall=True)

    assert result["run_doall"] is False
    target.apply_config_changes.assert_not_called()
    assert result["per_node"][0]["transferred_files"] == ["custom.lua", "custom2.lua"]


def test_transfer_with_txt_file_still_runs_doall(monkeypatch):
    target = MagicMock()
    monkeypatch.setattr(
        "app.services.openvpn_multihome.maybe_ensure_node_openvpn_multihome", lambda *_args, **_kwargs: None
    )

    result = _transfer(monkeypatch, target, file_keys=["kresd_custom", "warp_rpz"], run_doall=True)

    assert result["run_doall"] is True
    target.apply_config_changes.assert_called_once()


@pytest.fixture
def router_env(monkeypatch):
    adapter = MagicMock()
    replicate = MagicMock()
    monkeypatch.setattr(edit_files, "require_ha_primary_for_config_ops", lambda _db: None)
    monkeypatch.setattr(edit_files, "get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr(edit_files, "get_active_node", lambda _db: _vpn_node(1))
    monkeypatch.setattr(edit_files, "maybe_replicate_config_files", replicate)
    return adapter, replicate


def test_save_kresd_custom_does_not_run_doall(router_env):
    adapter, replicate = router_env

    response = edit_files.save_edit_file(
        "kresd_custom", edit_files.FileContentUpdate(content="-- x"), db=MagicMock(), current_user=MagicMock()
    )

    adapter.write_config_file.assert_called_once_with("custom.lua", "-- x")
    adapter.apply_config_changes.assert_not_called()
    assert replicate.call_args.kwargs["run_doall"] is False
    assert "перезапущен" in response.message


def test_save_kresd_custom_failure_keeps_agent_error(router_env):
    adapter, replicate = router_env
    adapter.write_config_file.side_effect = HTTPException(status_code=400, detail="kresd@1 не запустился")

    with pytest.raises(HTTPException) as exc:
        edit_files.save_edit_file(
            "kresd_custom", edit_files.FileContentUpdate(content="broken("), db=MagicMock(), current_user=MagicMock()
        )

    assert (exc.value.status_code, exc.value.detail) == (400, "kresd@1 не запустился")
    replicate.assert_not_called()


def test_batch_with_only_kresd_custom_skips_doall(router_env):
    adapter, replicate = router_env

    edit_files.save_batch(edit_files.BatchUpdate(files={"kresd_custom2": "-- x"}), db=MagicMock(), _=MagicMock())

    adapter.apply_config_changes.assert_not_called()
    assert replicate.call_args.kwargs["run_doall"] is False


def test_batch_rejects_unknown_key_before_writing(router_env):
    adapter, _replicate = router_env

    with pytest.raises(HTTPException) as exc:
        edit_files.save_batch(
            edit_files.BatchUpdate(files={"include_hosts": "a", "bogus": "b"}), db=MagicMock(), _=MagicMock()
        )

    assert exc.value.status_code == 400
    adapter.write_config_file.assert_not_called()
