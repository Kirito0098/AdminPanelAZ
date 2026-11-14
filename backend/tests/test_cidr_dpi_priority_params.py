"""DPI priority params: request schema → router kwargs → route budget."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.routers import cidr_db as cidr_db_router
from app.services.cidr.pipeline import db_pipeline

AKAMAI = "akamai-ips.txt"
CLOUDFLARE = "cloudflare-ips.txt"


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def with_entities(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, meta_rows, cidr_rows):
        self._meta_rows = meta_rows
        self._cidr_rows = cidr_rows

    def query(self, model):
        if model.__name__ == "ProviderMeta":
            return _FakeQuery(self._meta_rows)
        return _FakeQuery(self._cidr_rows)


@pytest.fixture
def captured(monkeypatch):
    """Run the router task synchronously and capture pipeline kwargs."""
    seen: dict = {}
    monkeypatch.setattr(cidr_db_router, "require_ha_primary_for_config_ops", lambda db: None)
    monkeypatch.setattr(
        cidr_db_router, "start_pipeline_task", lambda task_type, message: ("task-1", None)
    )

    def _start(task_id, runner):
        seen["result"] = runner(lambda percent, stage: None)

    monkeypatch.setattr(cidr_db_router, "start_cidr_task", _start)

    def _compile(**kwargs):
        seen["compile"] = kwargs
        return {"success": False}

    def _estimate(**kwargs):
        seen["estimate"] = kwargs
        return {"success": True}

    monkeypatch.setattr(cidr_db_router, "run_compile", _compile)
    monkeypatch.setattr(cidr_db_router, "estimate_cidr_matches_from_db", _estimate)
    return seen


def test_generate_forwards_dpi_fields(captured):
    payload = cidr_db_router.CidrDbGenerateRequest(
        action="generate",
        dpi_priority_files=[AKAMAI],
        dpi_mandatory_files=[CLOUDFLARE],
        dpi_priority_min_budget=50,
    )

    cidr_db_router.cidr_db_generate(payload, None, db=object())

    assert captured["compile"]["dpi_priority_files"] == [AKAMAI]
    assert captured["compile"]["dpi_mandatory_files"] == [CLOUDFLARE]
    assert captured["compile"]["dpi_priority_min_budget"] == 50


def test_estimate_forwards_dpi_fields(captured):
    payload = cidr_db_router.CidrDbGenerateRequest(
        action="estimate",
        dpi_priority_files=[CLOUDFLARE],
        dpi_priority_min_budget=10,
    )

    cidr_db_router.cidr_db_generate(payload, None, db=object())

    assert captured["estimate"]["dpi_priority_files"] == [CLOUDFLARE]
    assert captured["estimate"]["dpi_mandatory_files"] is None
    assert captured["estimate"]["dpi_priority_min_budget"] == 10


def test_dry_run_uses_estimate_without_dpi_fields(captured):
    payload = cidr_db_router.CidrDbGenerateRequest(action="generate", dry_run=True)

    cidr_db_router.cidr_db_generate(payload, None, db=object())

    assert "compile" not in captured
    assert captured["estimate"]["dpi_priority_files"] is None
    assert captured["estimate"]["dpi_mandatory_files"] is None
    assert captured["estimate"]["dpi_priority_min_budget"] == 0


def test_unknown_file_name_rejected():
    with pytest.raises(ValidationError):
        cidr_db_router.CidrDbGenerateRequest(dpi_priority_files=["no-such-ips.txt"])


def test_negative_min_budget_rejected():
    with pytest.raises(ValidationError):
        cidr_db_router.CidrDbGenerateRequest(dpi_priority_min_budget=-1)


def test_route_limit_receives_dpi_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(db_pipeline.constants, "LIST_DIR", str(tmp_path))
    monkeypatch.setattr(db_pipeline, "_make_runtime_backup", lambda files: ("", []))
    seen: dict = {}
    real_apply = db_pipeline._apply_total_route_limit

    def _spy(entries, total_limit, **kwargs):
        seen.update(kwargs)
        return real_apply(entries, total_limit, **kwargs)

    monkeypatch.setattr(db_pipeline, "_apply_total_route_limit", _spy)

    meta_rows = [
        SimpleNamespace(
            provider_key=AKAMAI,
            refresh_status="ok",
            cidr_count=2,
            source_used="test",
        )
    ]
    cidr_rows = [
        SimpleNamespace(
            provider_key=AKAMAI, cidr=cidr, region_scope=None, country_codes=None
        )
        for cidr in ("10.0.0.0/8", "20.0.0.0/8")
    ]
    session = _FakeSession(meta_rows, cidr_rows)

    db_pipeline._update_cidr_files_from_db_impl(
        db=session,
        cidr_db=session,
        selected_files=[AKAMAI],
        total_cidr_limit=1,
        dpi_priority_files=[AKAMAI],
        dpi_mandatory_files=[AKAMAI],
        dpi_priority_min_budget=5,
    )

    assert seen == {
        "dpi_priority_files": [AKAMAI],
        "dpi_mandatory_files": [AKAMAI],
        "dpi_priority_min_budget": 5,
    }
