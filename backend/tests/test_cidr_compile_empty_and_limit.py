"""Compile stage: keep last-good artifacts and budget routes after collapse.

The real ``update_cidr_files_from_db`` opens app DB sessions; these tests call the
implementation directly with fake sessions and a tmp ``LIST_DIR`` (no network, no DB).
"""

from types import SimpleNamespace

import pytest

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
    """Serves provider metadata for ProviderMeta and rows for ProviderCidr."""

    def __init__(self, meta_rows, cidr_rows):
        self._meta_rows = meta_rows
        self._cidr_rows = cidr_rows

    def query(self, model):
        if model.__name__ == "ProviderMeta":
            return _FakeQuery(self._meta_rows)
        return _FakeQuery(self._cidr_rows)


@pytest.fixture(autouse=True)
def list_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(db_pipeline.constants, "LIST_DIR", str(tmp_path))
    monkeypatch.setattr(db_pipeline, "_make_runtime_backup", lambda files: ("", []))
    return tmp_path


def _run(providers, cidrs_by_provider, *, limit):
    meta_rows = [
        SimpleNamespace(
            provider_key=name,
            refresh_status="ok",
            cidr_count=len(cidrs_by_provider[name]),
            source_used="test",
        )
        for name in providers
    ]
    cidr_rows = [
        SimpleNamespace(provider_key=name, cidr=cidr, region_scope=None, country_codes=None)
        for name in providers
        for cidr in cidrs_by_provider[name]
    ]
    session = _FakeSession(meta_rows, cidr_rows)
    return db_pipeline._update_cidr_files_from_db_impl(
        db=session,
        cidr_db=session,
        selected_files=list(providers),
        total_cidr_limit=limit,
    )


def _routes(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


def test_empty_after_limit_keeps_last_good_file(list_dir):
    stale_path = list_dir / CLOUDFLARE
    stale_content = "# stale cloudflare list\n1.2.3.0/24\n"
    stale_path.write_text(stale_content, encoding="utf-8")

    result = _run(
        [AKAMAI, CLOUDFLARE],
        {
            AKAMAI: ["1.1.1.0/24", "2.2.2.0/24", "3.3.3.0/24"],
            CLOUDFLARE: ["4.4.4.0/24", "5.5.5.0/24"],
        },
        limit=1,
    )

    # Budget 0 must not touch the existing artifact.
    assert stale_path.read_text(encoding="utf-8") == stale_content
    assert CLOUDFLARE not in [item["file"] for item in result["updated"]]
    assert AKAMAI in [item["file"] for item in result["updated"]]

    quality = result["quality_report"]["providers"][CLOUDFLARE]
    assert quality["status"] == "skipped"
    assert quality["skip_reason"] == "empty_after_total_limit"
    assert quality["final_after_limit_count"] == 0
    assert {"file": CLOUDFLARE, "reason": "empty_after_total_limit"} in result["skipped"]


def test_nested_prefixes_collapse_before_limit(list_dir):
    result = _run([AKAMAI], {AKAMAI: ["10.0.0.0/8", "10.1.0.0/16"]}, limit=1)

    assert _routes(list_dir / AKAMAI) == ["10.0.0.0/8"]
    assert [item["cidr_count"] for item in result["updated"]] == [1]


def test_limit_budget_uses_collapsed_route_counts(list_dir):
    # Collapsed total is 1 + 2 = 3 routes, so a limit of 3 must not cut anything.
    result = _run(
        [AKAMAI, CLOUDFLARE],
        {
            AKAMAI: ["10.0.0.0/8", "10.1.0.0/16"],
            CLOUDFLARE: ["20.0.0.0/16", "30.0.0.0/16"],
        },
        limit=3,
    )

    assert _routes(list_dir / AKAMAI) == ["10.0.0.0/8"]
    assert _routes(list_dir / CLOUDFLARE) == ["20.0.0.0/16", "30.0.0.0/16"]
    assert {item["file"]: item["cidr_count"] for item in result["updated"]} == {
        AKAMAI: 1,
        CLOUDFLARE: 2,
    }


def test_non_empty_provider_writes_file(list_dir):
    result = _run([AKAMAI], {AKAMAI: ["1.1.1.0/24", "2.2.2.0/24"]}, limit=100)

    text = (list_dir / AKAMAI).read_text(encoding="utf-8")
    assert "# Auto-generated CIDR list for akamai-ips.txt" in text
    assert _routes(list_dir / AKAMAI) == ["1.1.1.0/24", "2.2.2.0/24"]
    assert [item["file"] for item in result["updated"]] == [AKAMAI]
    assert result["quality_report"]["providers"][AKAMAI]["status"] == "updated"
