"""Stage 4: deploy preview, rollback, custom provider API tests."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.cidr.cidr_tasks import enable_memory_backend_for_tests
from app.services.cidr.pipeline.deploy_preview import compute_deploy_preview
from app.services.cidr.pipeline.file_pipeline import list_runtime_backups, rollback_from_runtime_backup


@pytest.fixture()
def stage4_env(api_test_env, tmp_path, monkeypatch):
    from app.services.cidr.cidr_tasks import _CIDR_TASKS

    enable_memory_backend_for_tests(True)
    _CIDR_TASKS.clear()

    list_dir = tmp_path / "lists"
    backup_root = tmp_path / "runtime_backups"
    list_dir.mkdir()
    backup_root.mkdir()
    (list_dir / "amazon-ips.txt").write_text("10.0.0.0/8\n10.1.0.0/16\n", encoding="utf-8")

    monkeypatch.setattr("app.services.cidr.pipeline.deploy.LIST_DIR", str(list_dir))
    monkeypatch.setattr("app.services.cidr.pipeline.deploy_preview.LIST_DIR", str(list_dir))
    monkeypatch.setattr("app.services.cidr.pipeline.file_pipeline._cfg", lambda key: {
        "LIST_DIR": str(list_dir),
        "RUNTIME_BACKUP_ROOT": str(backup_root),
        "BASELINE_DIR": str(list_dir / "_baseline"),
        "PROVIDER_SOURCES": {},
    }[key])

    stamp = "20260615T120000Z"
    stamp_dir = backup_root / stamp
    stamp_dir.mkdir()
    (stamp_dir / "amazon-ips.txt").write_text("192.168.0.0/16\n", encoding="utf-8")

    yield {**api_test_env, "list_dir": list_dir, "backup_root": backup_root, "stamp": stamp}
    _CIDR_TASKS.clear()
    enable_memory_backend_for_tests(False)


def _client(env):
    return TestClient(env["app"])


def test_list_runtime_backups(stage4_env):
    backups = list_runtime_backups()
    assert len(backups) == 1
    assert backups[0]["stamp"] == stage4_env["stamp"]
    assert "amazon-ips.txt" in backups[0]["files"]


def test_rollback_from_runtime_backup_restores_files(stage4_env):
    result = rollback_from_runtime_backup(stage4_env["stamp"], selected_files=["amazon-ips.txt"])
    assert result["success"] is True
    assert result["restored"] == ["amazon-ips.txt"]
    content = (stage4_env["list_dir"] / "amazon-ips.txt").read_text(encoding="utf-8")
    assert "192.168.0.0/16" in content


def test_deploy_preview_api(stage4_env):
    client = _client(stage4_env)

    with patch("app.routers.cidr_db.compute_deploy_preview") as preview_fn:
        preview_fn.return_value = {
            "success": True,
            "message": "Preview ok",
            "has_changes": True,
            "per_node": [],
        }
        resp = client.post(
            "/api/routing/cidr-db/deploy/preview",
            headers=stage4_env["admin_headers"],
            json={"all_online": True},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["has_changes"] is True


def test_deploy_preview_rejects_viewer(stage4_env):
    client = _client(stage4_env)
    resp = client.post(
        "/api/routing/cidr-db/deploy/preview",
        headers=stage4_env["viewer_headers"],
        json={},
    )
    assert resp.status_code == 403


def test_rollback_api_returns_202_and_logs_action(stage4_env):
    from app.models import UserActionLog

    client = _client(stage4_env)
    session = stage4_env["session_factory"]()

    with patch("app.routers.cidr_db.run_rollback") as run_rollback:
        run_rollback.return_value = {
            "success": True,
            "message": "ok",
            "restored": ["amazon-ips.txt"],
        }
        resp = client.post(
            "/api/routing/cidr-db/rollback",
            headers=stage4_env["admin_headers"],
            json={"backup_stamp": stage4_env["stamp"], "redeploy_after": False},
        )

    assert resp.status_code == 202
    log = (
        session.query(UserActionLog)
        .filter(UserActionLog.action == "settings_cidr_rollback_queued")
        .order_by(UserActionLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.details == stage4_env["stamp"]


def test_rollback_backups_endpoint(stage4_env):
    client = _client(stage4_env)
    resp = client.get("/api/routing/cidr-db/rollback/backups", headers=stage4_env["admin_headers"])
    assert resp.status_code == 200
    backups = resp.json().get("backups") or []
    assert any(item["stamp"] == stage4_env["stamp"] for item in backups)


def test_status_includes_runtime_backups(stage4_env):
    client = _client(stage4_env)
    resp = client.get("/api/routing/cidr-db/status", headers=stage4_env["admin_headers"])
    assert resp.status_code == 200
    backups = resp.json().get("runtime_backups") or []
    assert len(backups) >= 1


def test_custom_provider_entries_api(stage4_env):
    client = _client(stage4_env)

    with patch("app.routers.cidr_db.CidrDbUpdaterService") as svc_cls:
        svc = MagicMock()
        svc_cls.return_value = svc
        svc.add_custom_provider_entries.return_value = {
            "success": True,
            "message": "Добавлено CIDR: 1, ASN: 1",
            "provider_key": "amazon-ips.txt",
            "cidrs_added": 1,
            "asns_added": 1,
        }
        resp = client.post(
            "/api/routing/cidr-db/providers/amazon-ips.txt/custom",
            headers=stage4_env["admin_headers"],
            json={"cidrs_text": "203.0.113.0/24", "asns": ["AS13335"]},
        )

    assert resp.status_code == 200
    assert resp.json()["cidrs_added"] == 1


def test_compute_deploy_preview_detects_changes(stage4_env):
    db = stage4_env["session_factory"]()
    node = MagicMock()
    node.id = 1
    node.name = "test-node"
    node.status = "online"

    adapter = MagicMock()
    adapter.get_provider_content.return_value = {
        "filename": "amazon-ips.txt",
        "content": "10.0.0.0/8\n",
        "cidr_count": 1,
    }

    with patch("app.services.cidr.pipeline.deploy_preview.resolve_deploy_targets", return_value=([node], [])), patch(
        "app.services.cidr.pipeline.deploy_preview.get_adapter_for_node",
        return_value=adapter,
    ):
        result = compute_deploy_preview(db, target_node_id=1, selected_files=["amazon-ips.txt"])

    assert result["has_changes"] is True
    assert result["per_node"][0]["files_changed"] == 1
    file_diff = result["per_node"][0]["files"][0]["diff"]
    assert file_diff["added"] >= 1


def test_rollback_notify_on_failure(stage4_env):
    from app.services.cidr.cidr_notify import maybe_notify_rollback_failed

    db = MagicMock()
    with patch("app.services.cidr.cidr_notify.admin_notify_service.send_cidr_rollback_failed") as notify:
        maybe_notify_rollback_failed(db, {"success": False, "message": "fail"}, triggered_by="manual:admin")
        notify.assert_called_once()
