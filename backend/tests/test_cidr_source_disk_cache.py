"""Persistent last-good on-disk cache for CIDR provider sources."""

import json
import time
from pathlib import Path

import pytest

from app.services.cidr.pipeline import db_service
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

URL = "https://example.test/provider.txt"
PAYLOAD = "10.0.0.0/24\n10.1.0.0/24\n"
CACHED_CIDRS = {"10.0.0.0/24", "10.1.0.0/24"}


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "staging" / "source_cache"
    monkeypatch.setattr(db_service, "_source_disk_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(CidrDbUpdaterService, "_source_cache", {})
    monkeypatch.setattr(db_service, "SOURCE_FETCH_RETRIES", 1)
    monkeypatch.delenv("CIDR_DB_SOURCE_DISK_CACHE_MAX_AGE_SECONDS", raising=False)
    return cache_dir


def _service():
    # __init__ opens sessions; the download helpers do not use them.
    return CidrDbUpdaterService.__new__(CidrDbUpdaterService)


def _sources(*, url=URL, name="test"):
    return [{"name": name, "url": url, "format": "cidr_text", "timeout": 5}]


def _write_entry(fetched_at, *, url=URL, payload=PAYLOAD):
    path = db_service._source_disk_cache_path(url, "cidr_text")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "url": url,
                "format": "cidr_text",
                "fetched_at": fetched_at,
                "payload": payload,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_successful_fetch_writes_disk_cache(monkeypatch):
    monkeypatch.setattr(db_service, "_download_text", lambda url, timeout=45: PAYLOAD)

    items, _source_used = _service()._download_cidrs_with_meta(_sources())

    assert {item["cidr"] for item in items} == CACHED_CIDRS
    path = db_service._source_disk_cache_path(URL, "cidr_text")
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["url"] == URL
    assert entry["format"] == "cidr_text"
    assert entry["payload"] == PAYLOAD
    assert entry["fetched_at"] > 0
    # Atomic write must not leave temp files behind.
    assert list(path.parent.glob("*.tmp")) == []


def test_live_memory_cache_skips_http(monkeypatch):
    calls = []

    def fake_download(url, timeout=45):
        calls.append(url)
        return PAYLOAD

    monkeypatch.setattr(db_service, "_download_text", fake_download)
    svc = _service()

    svc._download_cidrs_with_meta(_sources())
    svc._download_cidrs_with_meta(_sources())

    assert len(calls) == 1


def test_upstream_failure_serves_stale_disk_cache(monkeypatch):
    monkeypatch.setattr(db_service, "_download_text", lambda url, timeout=45: PAYLOAD)
    svc = _service()
    svc._download_cidrs_with_meta(_sources())

    # Drop the in-memory layer so only the disk fallback can answer.
    monkeypatch.setattr(CidrDbUpdaterService, "_source_cache", {})

    def timeout_download(url, timeout=45):
        raise TimeoutError("upstream timed out")

    monkeypatch.setattr(db_service, "_download_text", timeout_download)

    items, _source_used, details = svc._download_cidrs_with_meta(
        _sources(), return_source_details=True
    )

    assert {item["cidr"] for item in items} == CACHED_CIDRS
    assert details[0]["status"] == "ok"
    assert details[0]["cache_hit"] is True
    assert details[0]["stale"] is True


def test_expired_disk_cache_is_not_used(monkeypatch):
    monkeypatch.setattr(db_service, "SOURCE_DISK_CACHE_MAX_AGE_SECONDS", 60)
    monkeypatch.setattr(db_service, "SOURCE_FETCH_RETRIES", 1)
    _write_entry(time.time() - 3600)

    def timeout_download(url, timeout=45):
        raise TimeoutError("upstream timed out")

    monkeypatch.setattr(db_service, "_download_text", timeout_download)

    with pytest.raises(ValueError):
        _service()._download_cidrs_with_meta(_sources())


def test_lru_eviction_keeps_fresh_entries(monkeypatch):
    now = time.time()
    paths = [
        _write_entry(now - 300, url=f"https://example.test/a{i}.txt") for i in range(3)
    ]
    oldest, fresh_one, fresh_two = paths
    total = sum(path.stat().st_size for path in paths)
    # Evicting the single oldest entry is exactly enough to fit the limit.
    monkeypatch.setattr(
        db_service, "SOURCE_DISK_CACHE_MAX_BYTES", total - oldest.stat().st_size
    )
    db_service._prune_source_disk_cache()

    assert not oldest.exists()
    assert fresh_one.exists()
    assert fresh_two.exists()


def test_disk_cache_errors_do_not_break_refresh(tmp_path, monkeypatch):
    # Point the cache at a path that cannot be created (a file in the way).
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(db_service, "_source_disk_cache_dir", lambda: blocker / "source_cache")
    monkeypatch.setattr(db_service, "_download_text", lambda url, timeout=45: PAYLOAD)

    items, _source_used = _service()._download_cidrs_with_meta(_sources())

    assert {item["cidr"] for item in items} == CACHED_CIDRS
    assert Path(blocker).is_file()
