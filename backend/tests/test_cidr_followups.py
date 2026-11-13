"""Follow-ups: HA deploy from DB, custom-ips DB import, service-level task summaries."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

from app import database as database_module
from app.routers import cidr_db, routing
from app.services import tg_mini_status
from app.services.cidr import task_summary
from app.services.cidr.pipeline.provider_sources import CUSTOM_PROVIDER_KEY

ADMIN = SimpleNamespace(username="admin", id=1)
CUSTOM_CONTENT = "203.0.113.0/24\n198.51.100.0/24\n"


class _FakeAdapter:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []

    def save_provider_content(self, filename: str, content: str) -> dict:
        self.saved.append((filename, content))
        return {"filename": filename, "cidr_count": 2}


class _FakeUpdater:
    instances: list["_FakeUpdater"] = []
    error: Exception | None = None
    result: dict = {"success": True, "per_provider": {}}

    def __init__(self, *, db, cidr_db) -> None:
        self.db = db
        self.cidr_db = cidr_db
        self.calls: list[dict] = []
        self.closed = False
        _FakeUpdater.instances.append(self)

    def refresh_all_providers(self, **kwargs):
        self.calls.append(kwargs)
        if _FakeUpdater.error is not None:
            raise _FakeUpdater.error
        return _FakeUpdater.result

    def close(self) -> None:
        self.closed = True


def _prepare_routing(monkeypatch) -> tuple[_FakeAdapter, MagicMock, MagicMock]:
    adapter = _FakeAdapter()
    node = SimpleNamespace(id=1, name="primary")
    cidr_db_session = MagicMock()
    monkeypatch.setattr(routing, "require_ha_primary_for_config_ops", lambda db: None)
    monkeypatch.setattr(routing, "get_active_adapter", lambda db: adapter)
    monkeypatch.setattr(routing, "get_active_node", lambda db: node)
    monkeypatch.setattr(routing, "find_sync_group_for_primary", lambda db, node_id: None)
    monkeypatch.setattr(routing, "CidrDbUpdaterService", _FakeUpdater)
    _FakeUpdater.instances = []
    _FakeUpdater.error = None
    _FakeUpdater.result = {"success": True, "per_provider": {}}
    return adapter, MagicMock(), cidr_db_session


def _save_provider(filename: str, content: str, cidr_db_session: MagicMock) -> dict:
    return routing.save_provider(
        filename,
        routing.ContentUpdate(content=content),
        _=ADMIN,
        db=MagicMock(),
        cidr_db=cidr_db_session,
    )


def test_custom_ips_save_imports_into_db(monkeypatch):
    adapter, _db, cidr_db_session = _prepare_routing(monkeypatch)

    result = _save_provider(CUSTOM_PROVIDER_KEY, CUSTOM_CONTENT, cidr_db_session)

    assert adapter.saved == [(CUSTOM_PROVIDER_KEY, CUSTOM_CONTENT)]
    assert len(_FakeUpdater.instances) == 1
    updater = _FakeUpdater.instances[0]
    assert updater.cidr_db is cidr_db_session
    assert updater.calls == [
        {"triggered_by": "panel:custom-ips", "selected_files": [CUSTOM_PROVIDER_KEY]}
    ]
    assert updater.closed is True
    assert "warnings" not in result


def test_custom_ips_import_error_is_a_warning_but_file_stays_saved(monkeypatch):
    adapter, _db, cidr_db_session = _prepare_routing(monkeypatch)
    _FakeUpdater.error = RuntimeError("db is locked")

    result = _save_provider(CUSTOM_PROVIDER_KEY, CUSTOM_CONTENT, cidr_db_session)

    assert adapter.saved == [(CUSTOM_PROVIDER_KEY, CUSTOM_CONTENT)]
    assert len(result["warnings"]) == 1
    assert "db is locked" in result["warnings"][0]
    assert _FakeUpdater.instances[0].closed is True


def test_other_providers_do_not_import(monkeypatch):
    adapter, _db, cidr_db_session = _prepare_routing(monkeypatch)

    _save_provider("cloudflare-ips.txt", "203.0.113.0/24\n", cidr_db_session)

    assert adapter.saved == [("cloudflare-ips.txt", "203.0.113.0/24\n")]
    assert _FakeUpdater.instances == []


def test_generate_from_db_passes_db_and_node_to_deploy(monkeypatch):
    node = SimpleNamespace(id=7, name="ha-primary", openvpn_multihome=False)

    class _Query:
        def filter(self, *args):
            return self

        def first(self):
            return node

    class _Session:
        def __init__(self) -> None:
            self.closed = False

        def query(self, model):
            return _Query()

        def close(self) -> None:
            self.closed = True

    session = _Session()
    adapter = MagicMock()
    deploy_kwargs: dict = {}
    runner_holder: dict = {}

    monkeypatch.setattr(database_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(cidr_db, "require_ha_primary_for_config_ops", lambda db: None)
    monkeypatch.setattr(cidr_db, "start_pipeline_task", lambda task_type, message: ("task-1", None))
    monkeypatch.setattr(cidr_db, "run_compile", lambda **kwargs: {"success": True, "updated": ["custom-ips.txt"]})
    monkeypatch.setattr(cidr_db, "is_cancel_requested", lambda task_id: False)
    monkeypatch.setattr(cidr_db, "get_adapter_for_node", lambda target: adapter)

    def _fake_deploy(target_adapter, **kwargs):
        deploy_kwargs.update(kwargs)
        deploy_kwargs["adapter"] = target_adapter
        return {"pushed": ["custom-ips.txt"], "failed": []}

    monkeypatch.setattr(cidr_db, "run_deploy", _fake_deploy)
    monkeypatch.setattr(cidr_db, "start_cidr_task", lambda task_id, runner: runner_holder.update(runner=runner))

    payload = cidr_db.CidrDbGenerateRequest(
        target_node_id=7,
        deploy_after=True,
        sync_after=False,
    )
    response = cidr_db.cidr_db_generate(payload, _=ADMIN, db=MagicMock())
    result = runner_holder["runner"](None)

    assert response["queued"] is True
    assert result["deploy"] == {"pushed": ["custom-ips.txt"], "failed": []}
    assert deploy_kwargs["adapter"] is adapter
    assert deploy_kwargs["files"] == ["custom-ips.txt"]
    assert deploy_kwargs["db"] is session
    assert deploy_kwargs["node"] is node
    assert session.closed is True


def test_tg_mini_status_reads_summaries_from_service(monkeypatch):
    assert "app.routers.cidr_db" not in inspect.getsource(tg_mini_status)
    assert tg_mini_status.summarize_last_compile is task_summary.summarize_last_compile
    assert tg_mini_status.summarize_last_deploy is task_summary.summarize_last_deploy

    tasks = {
        "cidr_generate_from_db": {
            "finished_at": "2026-11-13T10:00:00Z",
            "status": "completed",
            "result": {"updated": ["a.txt", "b.txt"], "artifact_stamp": "stamp-1"},
            "message": "ok",
        },
        "cidr_deploy": {
            "finished_at": "2026-11-13T10:05:00Z",
            "status": "completed",
            "result": {
                "deploy": {"pushed": ["a.txt"], "failed": []},
                "target_node_id": 7,
                "artifact_stamp": "stamp-1",
                "per_node": [],
            },
            "message": "ok",
        },
    }
    monkeypatch.setattr(task_summary, "find_last_completed_cidr_task", lambda task_type: tasks.get(task_type))

    compile_row = task_summary.summarize_last_compile()
    deploy_row = task_summary.summarize_last_deploy()

    assert compile_row["files_updated"] == 2
    assert compile_row["artifact_stamp"] == "stamp-1"
    assert deploy_row["pushed_count"] == 1
    assert deploy_row["target_node_id"] == 7
