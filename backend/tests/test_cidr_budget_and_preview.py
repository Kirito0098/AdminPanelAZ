"""Route budget fallbacks and deploy preview include-file staleness.

Both read filesystem state only (LIST_DIR + node config dir): no network, no DB.
"""

from types import SimpleNamespace

import pytest

from app.services.cidr import route_budget
from app.services.cidr.pipeline import deploy, deploy_preview
from app.services.cidr.pipeline.route_limits import _apply_total_route_limit

CLOUDFLARE = "cloudflare-ips.txt"
CLOUDFLARE_INCLUDE = "AP-cloudflare-include-ips.txt"


class _FakeAdapter:
    """Stands in for a node adapter that already returns the given content."""

    def __init__(self, content: str) -> None:
        self._content = content

    def get_provider_content(self, filename: str) -> dict:
        return {
            "filename": filename,
            "content": self._content,
            "cidr_count": len(deploy_preview._route_lines(self._content)),
        }

    def get_routing_overview(self) -> dict:
        return {"providers": [], "route_stats": {}}


class _FakeNodeAdapter:
    """Node adapter returning route result files or raising like an offline node."""

    def __init__(self, files: list[dict] | None = None, error: Exception | None = None) -> None:
        self._files = files or []
        self._error = error

    def get_route_result_files(self) -> dict:
        if self._error is not None:
            raise self._error
        return {"files": self._files}


@pytest.fixture
def list_dir(tmp_path, monkeypatch):
    root = tmp_path / "list"
    root.mkdir()
    monkeypatch.setattr(deploy, "LIST_DIR", str(root))
    return root


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_preview, "ANTIZAPRET_PATH", str(tmp_path))
    root = tmp_path / "config"
    root.mkdir()
    return root


def _write(path, *cidrs: str) -> None:
    path.write_text("# test\n" + "".join(f"{cidr}\n" for cidr in cidrs), encoding="utf-8")


def test_budget_falls_back_to_artifacts(list_dir, monkeypatch):
    # The estimate ran but kept no route-limit meta.
    monkeypatch.setattr(
        route_budget,
        "find_last_completed_cidr_task",
        lambda _task_type: {"task_id": "t1", "status": "completed", "result": {}},
    )
    monkeypatch.setattr(route_budget, "_get_openvpn_route_total_cidr_limit", lambda: 100)
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24", "2.2.2.0/24")
    _write(list_dir / "akamai-ips.txt", "3.3.3.0/24")

    payload = route_budget.build_route_budget_payload()

    assert payload["available"] is True
    assert payload["source"] == "artifacts"
    assert payload["used"] == 3
    assert payload["limit"] == 100
    assert payload["remaining"] == 97
    assert payload["original_total"] is None
    assert payload["finished_at"]


def test_budget_source_is_estimate_when_task_has_meta(monkeypatch):
    monkeypatch.setattr(
        route_budget,
        "find_last_completed_cidr_task",
        lambda _task_type: {
            "task_id": "t2",
            "status": "completed",
            "finished_at": "2026-01-01T00:00:00+00:00",
            "result": {
                "global_route_optimization": {
                    "strategy": "none",
                    "limit": 50,
                    "original_total_cidr_count": 40,
                    "compressed_total_cidr_count": 40,
                    "warning": None,
                }
            },
        },
    )

    payload = route_budget.build_route_budget_payload()

    assert payload["available"] is True
    assert payload["source"] == "estimate"
    assert payload["used"] == 40
    assert payload["remaining"] == 10


def test_budget_unavailable_without_estimate_and_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "LIST_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(route_budget, "find_last_completed_cidr_task", lambda _task_type: None)

    payload = route_budget.build_route_budget_payload()

    assert payload["available"] is False
    assert payload["message"]


def test_budget_source_is_node_route_ips(list_dir, monkeypatch):
    monkeypatch.setattr(route_budget, "_get_openvpn_route_total_cidr_limit", lambda: 900)
    monkeypatch.setattr(route_budget, "find_last_completed_cidr_task", lambda _task_type: None)
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24", "2.2.2.0/24")
    _write(list_dir / "akamai-ips.txt", "3.3.3.0/24")
    adapter = _FakeNodeAdapter(
        [
            {"key": "route_ips", "filename": "route-ips.txt", "exists": True, "line_count": 254},
            {"key": "result_ips", "filename": "result-ips.txt", "exists": True, "line_count": 999},
        ]
    )

    payload = route_budget.build_route_budget_payload(adapter=adapter)

    assert payload["available"] is True
    assert payload["source"] == "node"
    assert payload["used"] == 254
    assert payload["panel_used"] == 3
    assert payload["limit"] == 900
    assert payload["remaining"] == 646
    assert payload["original_total"] is None
    assert payload["warning"] is None


def test_budget_falls_back_when_node_raises(list_dir, monkeypatch):
    monkeypatch.setattr(route_budget, "_get_openvpn_route_total_cidr_limit", lambda: 100)
    monkeypatch.setattr(
        route_budget,
        "find_last_completed_cidr_task",
        lambda _task_type: {
            "task_id": "t3",
            "status": "completed",
            "finished_at": "2026-01-01T00:00:00+00:00",
            "result": {
                "global_route_optimization": {
                    "strategy": "none",
                    "limit": 50,
                    "original_total_cidr_count": 40,
                    "compressed_total_cidr_count": 40,
                    "warning": None,
                }
            },
        },
    )
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24")

    payload = route_budget.build_route_budget_payload(
        adapter=_FakeNodeAdapter(error=RuntimeError("node offline"))
    )

    assert payload["source"] == "estimate"
    assert payload["used"] == 40
    assert payload["panel_used"] == 1


@pytest.mark.parametrize(
    "files",
    [
        [],
        [{"key": "result_ips", "filename": "result-ips.txt", "exists": True, "line_count": 5}],
        [{"key": "route_ips", "filename": "route-ips.txt", "exists": False, "line_count": 0}],
    ],
)
def test_budget_falls_back_without_node_route_ips(list_dir, monkeypatch, files):
    monkeypatch.setattr(route_budget, "_get_openvpn_route_total_cidr_limit", lambda: 100)
    monkeypatch.setattr(route_budget, "find_last_completed_cidr_task", lambda _task_type: None)
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24", "2.2.2.0/24")

    payload = route_budget.build_route_budget_payload(adapter=_FakeNodeAdapter(files))

    assert payload["source"] == "artifacts"
    assert payload["used"] == 2
    assert payload["panel_used"] == 2


def test_budget_node_warns_when_over_limit(list_dir, monkeypatch):
    monkeypatch.setattr(route_budget, "_get_openvpn_route_total_cidr_limit", lambda: 900)
    monkeypatch.setattr(route_budget, "find_last_completed_cidr_task", lambda _task_type: None)
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24")
    adapter = _FakeNodeAdapter(
        [{"key": "route_ips", "filename": "route-ips.txt", "exists": True, "line_count": 950}]
    )

    payload = route_budget.build_route_budget_payload(adapter=adapter)

    assert payload["source"] == "node"
    assert payload["remaining"] == 0
    assert payload["warning"]


def test_budget_without_adapter_keeps_estimate_priority(list_dir, monkeypatch):
    monkeypatch.setattr(
        route_budget,
        "find_last_completed_cidr_task",
        lambda _task_type: {
            "task_id": "t4",
            "status": "completed",
            "finished_at": "2026-01-01T00:00:00+00:00",
            "result": {
                "global_route_optimization": {
                    "strategy": "none",
                    "limit": 50,
                    "original_total_cidr_count": 40,
                    "compressed_total_cidr_count": 40,
                    "warning": None,
                }
            },
        },
    )
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24", "2.2.2.0/24")

    payload = route_budget.build_route_budget_payload()

    assert payload["source"] == "estimate"
    assert payload["used"] == 40
    assert payload["remaining"] == 10
    assert payload["panel_used"] == 2
    assert payload.get("node_used") is None


def test_total_route_limit_keeps_meta_when_under_limit():
    entries = [{"file": CLOUDFLARE, "cidrs": ["1.1.1.0/24", "2.2.2.0/24"]}]

    adjusted, meta = _apply_total_route_limit(entries, 10)

    assert adjusted == entries
    assert meta is not None
    assert meta["strategy"] == "none"
    assert meta["limit"] == 10
    assert meta["original_total_cidr_count"] == 2
    assert meta["compressed_total_cidr_count"] == 2
    assert meta["warning"] is None


@pytest.mark.parametrize(
    ("include_content", "expected_status"),
    [
        (None, "not_enabled"),
        ("# stale\n1.1.1.0/24\n", "stale"),
        ("1.1.1.0/24\n2.2.2.0/24\n", "in_sync"),
    ],
)
def test_preview_local_include_states(
    list_dir, config_dir, monkeypatch, include_content, expected_status
):
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24", "2.2.2.0/24")
    if include_content is not None:
        (config_dir / CLOUDFLARE_INCLUDE).write_text(include_content, encoding="utf-8")
    node = SimpleNamespace(id=1, name="local", is_local=True, node_metadata="")
    monkeypatch.setattr(
        deploy_preview,
        "get_adapter_for_node",
        lambda _node: _FakeAdapter("1.1.1.0/24\n2.2.2.0/24\n"),
    )

    entry = deploy_preview._preview_node(node, [CLOUDFLARE])

    file_entry = entry["files"][0]
    assert file_entry["include_file"] == CLOUDFLARE_INCLUDE
    assert file_entry["include_status"] == expected_status
    if expected_status == "stale":
        assert entry["files_stale"] == 1
        assert entry["stale_files"] == [CLOUDFLARE_INCLUDE]
    else:
        assert entry["files_stale"] == 0
        assert entry["stale_files"] == []


def test_preview_reports_stale_files_in_summary(list_dir, config_dir, monkeypatch):
    _write(list_dir / CLOUDFLARE, "1.1.1.0/24")
    (config_dir / CLOUDFLARE_INCLUDE).write_text("9.9.9.0/24\n", encoding="utf-8")
    node = SimpleNamespace(id=1, name="local", is_local=True, node_metadata="")
    monkeypatch.setattr(
        deploy_preview, "get_adapter_for_node", lambda _node: _FakeAdapter("1.1.1.0/24\n")
    )
    monkeypatch.setattr(deploy_preview, "resolve_deploy_targets", lambda *_args, **_kwargs: ([node], []))

    preview = deploy_preview.compute_deploy_preview(object())

    assert preview["has_changes"] is True
    assert preview["has_stale_includes"] is True
    assert preview["stale_files"] == [CLOUDFLARE_INCLUDE]
    assert "include-файлы" in preview["message"]
    assert preview["summary"]


def test_preview_survives_missing_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "LIST_DIR", str(tmp_path / "no-list"))
    monkeypatch.setattr(deploy_preview, "ANTIZAPRET_PATH", str(tmp_path / "no-az"))
    node = SimpleNamespace(id=7, name="local", is_local=True, node_metadata="")
    monkeypatch.setattr(deploy_preview, "get_adapter_for_node", lambda _node: _FakeAdapter(""))
    monkeypatch.setattr(deploy_preview, "resolve_deploy_targets", lambda *_args, **_kwargs: ([node], []))

    preview = deploy_preview.compute_deploy_preview(object(), selected_files=[CLOUDFLARE])

    assert preview["success"] is True
    assert preview["per_node"][0]["status"] == "ok"
    assert preview["stale_files"] == []
    assert preview["has_stale_includes"] is False
