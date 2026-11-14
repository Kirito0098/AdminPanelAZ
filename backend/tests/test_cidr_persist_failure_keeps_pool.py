"""A persist failure must never empty the provider CIDR pool.

The old error handler in ``refresh_all_providers`` deleted every ``ProviderCidr``
row for the provider, so the next compile saw ``no_db_data`` and the provider
dropped out of the routing lists. These tests drive one provider through the
real ``refresh_all_providers`` path on throwaway SQLite files and fail the
persist step on purpose.
"""

import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cidr_database import CidrBase
from app.database import Base
from app.services.cidr.pipeline import cidr_csv_import
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

PROVIDER = "amazon-ips.txt"
OLD_CIDRS = ("10.10.0.0/16", "10.11.0.0/16")
NEW_CIDRS = ("10.20.0.0/16", "10.21.0.0/16", "10.22.0.0/16")


@pytest.fixture
def service(tmp_path, monkeypatch):
    """Service wired to tmp SQLite files, with old CIDRs already in the pool."""
    from app import models as m  # noqa: F401 — populate Base.metadata before create_all

    main_engine = create_engine(f"sqlite:///{tmp_path / 'adminpanel.db'}")
    Base.metadata.create_all(main_engine)
    cidr_path = tmp_path / "cidr.db"
    cidr_engine = create_engine(f"sqlite:///{cidr_path}")
    CidrBase.metadata.create_all(cidr_engine)

    # The native import and CSV staging must stay inside tmp_path.
    monkeypatch.setattr(cidr_csv_import, "get_staging_dir", lambda: tmp_path / "staging")
    monkeypatch.setattr(cidr_csv_import, "get_sqlite_db_path", lambda: cidr_path)

    db = sessionmaker(bind=main_engine)()
    cidr_db = sessionmaker(bind=cidr_engine)()
    svc = CidrDbUpdaterService(db=db, cidr_db=cidr_db)

    db.add(
        m.ProviderMeta(
            provider_key=PROVIDER,
            cidr_count=len(OLD_CIDRS),
            refresh_status="ok",
        )
    )
    for cidr in OLD_CIDRS:
        cidr_db.add(m.ProviderCidr(provider_key=PROVIDER, cidr=cidr))
    db.commit()
    cidr_db.commit()

    def fake_process_provider_refresh_context(**kwargs):
        return {
            "status": "ok",
            "cidr_count": len(NEW_CIDRS),
            "discovered_asns": [],
            "asn_fetch_meta": {},
            "merged_items": [
                {"cidr": cidr, "region": None, "countries": []} for cidr in NEW_CIDRS
            ],
            "source": "stub",
            "asn_errors": [],
            "expected_asn_min": 0,
            "asn_count": 0,
            "active_asn_count": 0,
            "anomaly_level": "none",
            "anomaly_reason": None,
            "fallback_applied": False,
        }

    monkeypatch.setattr(
        svc, "_process_provider_refresh_context", fake_process_provider_refresh_context
    )

    yield svc, main_engine, cidr_engine

    svc.close()
    db.close()
    cidr_db.close()


def _pool_cidrs(cidr_engine):
    from app import models as m

    with sessionmaker(bind=cidr_engine)() as session:
        rows = session.query(m.ProviderCidr).filter_by(provider_key=PROVIDER).all()
        return {row.cidr for row in rows}


def _meta(main_engine):
    from app import models as m

    with sessionmaker(bind=main_engine)() as session:
        return session.query(m.ProviderMeta).filter_by(provider_key=PROVIDER).one()


def test_persist_error_after_import_keeps_new_pool(service, monkeypatch, caplog):
    """The import commits, then the meta write blows up: rows must survive."""
    svc, main_engine, cidr_engine = service
    real_upsert = svc._upsert_provider_cidrs

    def upsert_then_fail(*args, **kwargs):
        real_upsert(*args, **kwargs)  # real staging CSV + native import into tmp DB
        raise RuntimeError("disk I/O error while writing provider meta")

    monkeypatch.setattr(svc, "_upsert_provider_cidrs", upsert_then_fail)

    with caplog.at_level(logging.WARNING, logger="app.services.cidr.pipeline.db_service"):
        result = svc.refresh_all_providers(selected_files=[PROVIDER], triggered_by="test")

    assert result["providers_failed"] == 1
    assert result["per_provider"][PROVIDER]["status"] == "error"
    assert _pool_cidrs(cidr_engine) == set(NEW_CIDRS)
    meta = _meta(main_engine)
    assert meta.refresh_status == "error"
    assert meta.anomaly_level == "critical"
    assert "pool preserved after persist error" in caplog.text


def test_persist_error_before_import_keeps_previous_pool(service, monkeypatch, caplog):
    """A recoverable persist failure leaves the previous pool untouched."""
    svc, main_engine, cidr_engine = service

    def fail_upsert(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(svc, "_upsert_provider_cidrs", fail_upsert)

    with caplog.at_level(logging.WARNING, logger="app.services.cidr.pipeline.db_service"):
        result = svc.refresh_all_providers(selected_files=[PROVIDER], triggered_by="test")

    assert result["providers_failed"] == 1
    assert _pool_cidrs(cidr_engine) == set(OLD_CIDRS)
    meta = _meta(main_engine)
    assert meta.refresh_status == "error"
    assert meta.cidr_count == len(OLD_CIDRS)
    assert "pool preserved after persist error" in caplog.text
