"""``custom-ips.txt`` is a provider without network sources.

The manual list lives in ``LIST_DIR`` and is imported into the CIDR DB on
refresh; it must show up in status, be cleared with the DB, and never trigger
an HTTP request. Run on throwaway SQLite files, like the neighbouring tests.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cidr_database import CidrBase
from app.database import Base
from app.services.cidr.pipeline import cidr_csv_import
from app.services.cidr.pipeline import constants as pipeline_constants
from app.services.cidr.pipeline import db_service
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.cidr.pipeline.provider_sources import CUSTOM_PROVIDER_KEY, PROVIDER_SOURCES

MANUAL_A = "203.0.113.0/24"
MANUAL_B = "198.51.100.0/24"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Service on tmp SQLite files, LIST_DIR in tmp_path, downloads forbidden."""
    from app import models as m  # noqa: F401 — populate Base.metadata before create_all

    main_engine = create_engine(f"sqlite:///{tmp_path / 'adminpanel.db'}")
    Base.metadata.create_all(main_engine)
    cidr_path = tmp_path / "cidr.db"
    cidr_engine = create_engine(f"sqlite:///{cidr_path}")
    CidrBase.metadata.create_all(cidr_engine)

    list_dir = tmp_path / "list"
    list_dir.mkdir()
    monkeypatch.setattr(pipeline_constants, "LIST_DIR", str(list_dir))
    monkeypatch.setattr(cidr_csv_import, "get_staging_dir", lambda: tmp_path / "staging")
    monkeypatch.setattr(cidr_csv_import, "get_sqlite_db_path", lambda: cidr_path)

    downloads = []

    def fake_download(url, timeout=45):
        downloads.append(url)
        raise AssertionError(f"custom provider must not download {url}")

    monkeypatch.setattr(db_service, "_download_text", fake_download)
    monkeypatch.setattr(CidrDbUpdaterService, "_source_cache", {})

    db = sessionmaker(bind=main_engine)()
    cidr_db = sessionmaker(bind=cidr_engine)()
    svc = CidrDbUpdaterService(db=db, cidr_db=cidr_db)

    yield svc, list_dir, main_engine, cidr_engine, downloads

    svc.close()
    db.close()
    cidr_db.close()


def _pool(cidr_engine):
    from app import models as m

    with sessionmaker(bind=cidr_engine)() as session:
        rows = session.query(m.ProviderCidr).filter_by(provider_key=CUSTOM_PROVIDER_KEY).all()
        return {row.cidr for row in rows}


def _meta(main_engine):
    from app import models as m

    with sessionmaker(bind=main_engine)() as session:
        return session.query(m.ProviderMeta).filter_by(provider_key=CUSTOM_PROVIDER_KEY).one_or_none()


def test_custom_provider_is_registered():
    assert CUSTOM_PROVIDER_KEY in PROVIDER_SOURCES
    assert PROVIDER_SOURCES[CUSTOM_PROVIDER_KEY] == []


def test_refresh_imports_custom_file_without_network(env):
    svc, list_dir, main_engine, cidr_engine, downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(
        f"# manual list\n{MANUAL_A}\n{MANUAL_B}\n", encoding="utf-8"
    )

    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    assert result["success"] is True
    per_provider = result["per_provider"][CUSTOM_PROVIDER_KEY]
    assert per_provider["status"] == "ok"
    assert per_provider["cidr_count"] == 2
    assert per_provider["source"] == "manual"
    assert _pool(cidr_engine) == {MANUAL_A, MANUAL_B}

    meta = _meta(main_engine)
    assert meta.refresh_status == "ok"
    assert meta.cidr_count == 2
    assert meta.source_used == "manual"
    assert meta.last_refreshed_at is not None
    assert downloads == []


def test_missing_file_is_ok_without_error(env):
    svc, _list_dir, main_engine, cidr_engine, downloads = env

    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    assert result["success"] is True
    assert result["per_provider"][CUSTOM_PROVIDER_KEY]["status"] == "ok"
    assert result["per_provider"][CUSTOM_PROVIDER_KEY]["cidr_count"] == 0
    assert _pool(cidr_engine) == set()
    meta = _meta(main_engine)
    assert meta.refresh_status == "ok"
    assert meta.refresh_error is None
    assert downloads == []


def test_empty_file_clears_pool(env):
    svc, list_dir, main_engine, cidr_engine, _downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(f"{MANUAL_A}\n", encoding="utf-8")
    svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")
    assert _pool(cidr_engine) == {MANUAL_A}

    # Emptying the file on purpose must empty the pool, not fall back to it.
    (list_dir / CUSTOM_PROVIDER_KEY).write_text("# nothing here\n", encoding="utf-8")
    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    assert result["per_provider"][CUSTOM_PROVIDER_KEY]["status"] == "ok"
    assert _pool(cidr_engine) == set()
    assert _meta(main_engine).cidr_count == 0


def test_missing_file_keeps_wizard_rows(env):
    """Rows added by the wizard before the first compile must survive a refresh."""
    from app import models as m

    svc, _list_dir, _main_engine, cidr_engine, _downloads = env
    svc.cidr_db.add(m.ProviderCidr(provider_key=CUSTOM_PROVIDER_KEY, cidr=MANUAL_A))
    svc.cidr_db.commit()

    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    assert result["per_provider"][CUSTOM_PROVIDER_KEY]["status"] == "ok"
    assert result["per_provider"][CUSTOM_PROVIDER_KEY]["cidr_count"] == 1
    assert _pool(cidr_engine) == {MANUAL_A}


def test_status_lists_custom_provider(env):
    svc, list_dir, _main_engine, _cidr_engine, _downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(f"{MANUAL_A}\n", encoding="utf-8")
    svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    status = svc.get_db_status()

    assert CUSTOM_PROVIDER_KEY in status["providers"]
    info = status["providers"][CUSTOM_PROVIDER_KEY]
    assert info["cidr_count"] == 1
    assert info["refresh_status"] == "ok"
    assert info["source_used"] == "manual"


def test_clear_removes_custom_provider(env):
    svc, list_dir, main_engine, cidr_engine, _downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(f"{MANUAL_A}\n{MANUAL_B}\n", encoding="utf-8")
    svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    result = svc.clear_provider_data(selected_files=[CUSTOM_PROVIDER_KEY])

    assert result["success"] is True
    assert result["providers_cleared"] == 1
    assert _pool(cidr_engine) == set()
    assert _meta(main_engine) is None
    status = svc.get_db_status()
    assert status["providers"][CUSTOM_PROVIDER_KEY]["refresh_status"] == "never"


def test_invalid_line_is_skipped_and_reported(env):
    svc, list_dir, main_engine, cidr_engine, _downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(f"{MANUAL_A}\nnot-a-cidr\n", encoding="utf-8")

    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    per_provider = result["per_provider"][CUSTOM_PROVIDER_KEY]
    assert per_provider["status"] == "partial"
    assert per_provider["cidr_count"] == 1
    assert _pool(cidr_engine) == {MANUAL_A}
    meta = _meta(main_engine)
    assert meta.refresh_status == "partial"
    assert "некорректные строки" in meta.refresh_error


def test_all_invalid_file_keeps_previous_pool(env):
    """A broken file must not wipe the pool the user already has."""
    svc, list_dir, main_engine, cidr_engine, _downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(f"{MANUAL_A}\n", encoding="utf-8")
    svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    (list_dir / CUSTOM_PROVIDER_KEY).write_text("not-a-cidr\n", encoding="utf-8")
    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    assert result["providers_failed"] == 1
    assert _pool(cidr_engine) == {MANUAL_A}
    assert _meta(main_engine).refresh_status == "error"


def test_negation_lines_are_reported_not_imported(env):
    """``!`` exclusions cannot live in ProviderCidr; they are surfaced, not widened."""
    svc, list_dir, main_engine, cidr_engine, _downloads = env
    (list_dir / CUSTOM_PROVIDER_KEY).write_text(f"!{MANUAL_A}\n{MANUAL_B}\n", encoding="utf-8")

    result = svc.refresh_all_providers(selected_files=[CUSTOM_PROVIDER_KEY], triggered_by="test")

    per_provider = result["per_provider"][CUSTOM_PROVIDER_KEY]
    assert per_provider["status"] == "partial"
    assert _pool(cidr_engine) == {MANUAL_B}
    assert "«!»" in _meta(main_engine).refresh_error
