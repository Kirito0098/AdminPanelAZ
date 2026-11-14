"""Parallel provider fetch phase of ``refresh_all_providers``.

Providers are downloaded concurrently (network/CPU only, no DB access) and then
persisted one by one in the original order. These tests drive the real fetch
and persist code on throwaway SQLite files; only ``_download_text`` is faked.
"""

import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cidr_database import CidrBase
from app.database import Base
from app.services.cidr import cidr_tasks
from app.services.cidr.pipeline import cidr_csv_import, db_service, provider_sources
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

FETCH_SLEEP = 0.2
MAIN_THREAD = threading.main_thread().name


def _providers(count):
    return [f"p{index}-ips.txt" for index in range(count)]


def _patch_providers(monkeypatch, names):
    """Replace the real provider catalogue with cheap cidr_text sources."""
    sources = {
        name: [
            {
                "name": f"{name}-source",
                "url": f"https://example.test/{name}.txt",
                "format": "cidr_text",
                "timeout": 5,
                "retries": 1,
            }
        ]
        for name in names
    }
    monkeypatch.setattr(provider_sources, "PROVIDER_SOURCES", sources)
    return sources


@pytest.fixture(autouse=True)
def _isolated_source_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_service, "_source_disk_cache_dir", lambda: tmp_path / "staging" / "source_cache"
    )
    monkeypatch.setattr(CidrDbUpdaterService, "_source_cache", {})
    monkeypatch.delenv("CIDR_DB_SOURCE_DISK_CACHE_MAX_AGE_SECONDS", raising=False)
    monkeypatch.delenv("CIDR_DB_PROVIDER_FETCH_WORKERS", raising=False)


@pytest.fixture
def service(tmp_path, monkeypatch):
    from app import models as m  # noqa: F401 — populate Base.metadata before create_all

    main_engine = create_engine(f"sqlite:///{tmp_path / 'adminpanel.db'}")
    Base.metadata.create_all(main_engine)
    cidr_path = tmp_path / "cidr.db"
    cidr_engine = create_engine(f"sqlite:///{cidr_path}")
    CidrBase.metadata.create_all(cidr_engine)

    monkeypatch.setattr(cidr_csv_import, "get_staging_dir", lambda: tmp_path / "staging")
    monkeypatch.setattr(cidr_csv_import, "get_sqlite_db_path", lambda: cidr_path)

    db = sessionmaker(bind=main_engine)()
    cidr_db = sessionmaker(bind=cidr_engine)()
    svc = CidrDbUpdaterService(db=db, cidr_db=cidr_db)
    try:
        yield svc, main_engine, cidr_engine
    finally:
        svc.close()
        db.close()
        cidr_db.close()


def _count(engine, model):
    with sessionmaker(bind=engine)() as session:
        return session.query(model).count()


def test_six_providers_fetched_in_parallel_keep_order(service, monkeypatch):
    svc, _main_engine, _cidr_engine = service
    names = _providers(6)
    _patch_providers(monkeypatch, names)

    def fake_download(url, timeout=45):
        time.sleep(FETCH_SLEEP)
        return "10.10.0.0/24\n10.11.0.0/24\n"

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    monkeypatch.setenv("CIDR_DB_PROVIDER_FETCH_WORKERS", "1")
    started = time.monotonic()
    serial_result = svc.refresh_all_providers(selected_files=names, triggered_by="test")
    serial_elapsed = time.monotonic() - started
    assert serial_result["providers_updated"] == len(names)

    CidrDbUpdaterService._source_cache.clear()
    monkeypatch.setenv("CIDR_DB_PROVIDER_FETCH_WORKERS", "3")
    started = time.monotonic()
    result = svc.refresh_all_providers(selected_files=names, triggered_by="test")
    parallel_elapsed = time.monotonic() - started

    assert result["providers_updated"] == len(names)
    assert list(result["per_provider"]) == names
    # Two waves of three workers stay well below the serial run.
    assert parallel_elapsed < serial_elapsed * 0.6, (serial_elapsed, parallel_elapsed)
    assert parallel_elapsed < 2 * FETCH_SLEEP * 2.5, parallel_elapsed


def test_one_provider_failure_does_not_break_others(service, monkeypatch):
    svc, _main_engine, _cidr_engine = service
    names = _providers(3)
    _patch_providers(monkeypatch, names)
    failing = names[1]

    def fake_download(url, timeout=45):
        if failing in url:
            raise RuntimeError("upstream is down")
        return "10.20.0.0/24\n"

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    result = svc.refresh_all_providers(selected_files=names, triggered_by="test")

    assert result["providers_failed"] == 1
    assert result["status"] == "partial"
    assert result["per_provider"][failing]["status"] == "error"
    assert "upstream is down" in result["per_provider"][failing]["error"]
    for name in names:
        if name == failing:
            continue
        assert result["per_provider"][name]["status"] == "ok"
        assert result["per_provider"][name]["cidr_count"] == 1


def test_progress_callback_only_runs_in_main_thread(service, monkeypatch):
    svc, _main_engine, _cidr_engine = service
    names = _providers(4)
    _patch_providers(monkeypatch, names)
    monkeypatch.setattr(
        db_service,
        "_download_text",
        lambda url, timeout=45: (time.sleep(FETCH_SLEEP / 2), "10.30.0.0/24\n")[1],
    )

    threads = []
    stages = []

    def progress(percent, stage):
        threads.append(threading.current_thread().name)
        stages.append((percent, stage))

    svc.refresh_all_providers(selected_files=names, triggered_by="test", progress_callback=progress)

    assert threads
    assert set(threads) == {MAIN_THREAD}
    assert stages[-1][0] == 100


def test_cancel_during_fetch_stops_new_providers(service, monkeypatch):
    svc, _main_engine, _cidr_engine = service
    names = _providers(4)
    _patch_providers(monkeypatch, names)
    monkeypatch.setenv("CIDR_DB_PROVIDER_FETCH_WORKERS", "1")

    task_id = "test-cancel-during-fetch"
    cidr_tasks.clear_cancel(task_id)
    downloaded = []

    def fake_download(url, timeout=45):
        downloaded.append(url)
        if len(downloaded) == 1:
            cidr_tasks.request_cancel(task_id)
        return "10.40.0.0/24\n"

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    try:
        with pytest.raises(cidr_tasks.CidrTaskCancelled):
            svc.refresh_all_providers(selected_files=names, triggered_by="test", task_id=task_id)
    finally:
        cidr_tasks.clear_cancel(task_id)

    assert len(downloaded) == 1


def test_dry_run_parallel_phase_does_not_write(service, monkeypatch):
    from app import models as m

    svc, main_engine, cidr_engine = service
    names = _providers(4)
    _patch_providers(monkeypatch, names)
    monkeypatch.setattr(
        db_service,
        "_download_text",
        lambda url, timeout=45: (time.sleep(FETCH_SLEEP / 2), "10.50.0.0/24\n10.51.0.0/24\n")[1],
    )

    result = svc.refresh_all_providers(selected_files=names, triggered_by="test", dry_run=True)

    assert result["dry_run"] is True
    assert result["log_id"] is None
    assert result["providers_updated"] == len(names)
    assert list(result["per_provider"]) == names
    assert result["total_cidrs"] == len(names) * 2
    assert _count(main_engine, m.ProviderMeta) == 0
    assert _count(main_engine, m.CidrDbRefreshLog) == 0
    assert _count(cidr_engine, m.ProviderCidr) == 0
