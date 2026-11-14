"""Hanging optional CIDR sources must not block ASN ingestion.

These tests drive the real production source lists (``_download_asn_cidrs_with_meta``
builds them from module constants); only ``db_service._download_text`` is faked.
"""

import json
import threading
import time

import pytest

from app.services.cidr.pipeline import db_service
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

MAIN_PREFIX = "1.1.1.0/24"
GEO_PREFIX = "2.2.2.0/24"
OPTIONAL_PREFIX = "9.9.9.0/24"


def _ripe_json(prefix):
    return json.dumps({"data": {"prefixes": [{"prefix": prefix}]}})


def _ripe_geo_json(prefix):
    return json.dumps({
        "data": {
            "located_resources": [
                {"locations": [{"country": "US", "resources": [prefix]}]},
            ],
        },
    })


def _bgp_state_json(prefix):
    return json.dumps({"data": {"bgp_state": [{"target_prefix": prefix}]}})


@pytest.fixture(autouse=True)
def _fast_optional_source(monkeypatch):
    monkeypatch.setattr(db_service, "OPTIONAL_SOURCE_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(CidrDbUpdaterService, "_source_cache", {})
    monkeypatch.setenv("CIDR_DB_SOURCE_FETCH_WORKERS", "4")


def _service():
    # __init__ opens sessions; the download helpers do not use them.
    return CidrDbUpdaterService.__new__(CidrDbUpdaterService)


def _asn_sources(asn=64500):
    """Only for tests targeting the generic method a caller would pass."""
    return [
        {
            "name": f"ripe-as{asn}",
            "url": db_service.RIPE_ANNOUNCED_PREFIXES_URL.format(asn=asn),
            "format": "ripe_json",
            "timeout": db_service.ASN_FETCH_SOURCE_TIMEOUT_SECONDS,
        },
        {
            "name": f"ripe-as{asn}-geo",
            "url": db_service.RIPE_GEO_BY_ASN_URL.format(asn=asn),
            "format": "ripe_geo_json",
            "timeout": db_service.ASN_FETCH_SOURCE_TIMEOUT_SECONDS,
        },
        {
            "name": f"ripe-as{asn}-bgpstate",
            "url": db_service.RIPE_BGP_STATE_URL.format(asn=asn),
            "format": "ripe_bgp_state_json",
            "timeout": db_service.ASN_OPTIONAL_SOURCE_TIMEOUT_SECONDS,
            "optional": True,
            "retries": 1,
        },
    ]


def test_hung_optional_source_does_not_block_asn_result(monkeypatch):
    svc = _service()

    def fake_download(url, timeout=45):
        if "bgp-state" in url:
            # Self-terminating wait: the abandoned worker does not outlive the test.
            threading.Event().wait(2)
            return _bgp_state_json(OPTIONAL_PREFIX)
        if "announced-prefixes" in url:
            return _ripe_json(MAIN_PREFIX)
        return _ripe_geo_json(GEO_PREFIX)

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    started = time.monotonic()
    items, _source_used, error = svc._download_asn_cidrs_with_meta(64500)
    elapsed = time.monotonic() - started

    assert elapsed < 1.5
    assert error is None
    assert items
    assert {item["cidr"] for item in items} == {MAIN_PREFIX, GEO_PREFIX}


def test_optional_source_retries_once_from_real_config(monkeypatch):
    svc = _service()
    # Pin the default retry count: dropping `retries: 1` from the production
    # source list must show up as extra bgp-state calls instead of passing.
    monkeypatch.setattr(db_service, "SOURCE_FETCH_RETRIES", 3)
    # Wide grace so a regression to SOURCE_FETCH_RETRIES=3 is visible as extra calls.
    monkeypatch.setattr(db_service, "OPTIONAL_SOURCE_GRACE_SECONDS", 3.5)
    bgp_state_calls = []

    def fake_download(url, timeout=45):
        if "bgp-state" in url:
            bgp_state_calls.append(url)
            raise OSError("timed out")
        if "announced-prefixes" in url:
            return _ripe_json(MAIN_PREFIX)
        return _ripe_geo_json(GEO_PREFIX)

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    _items, _source_used, error = svc._download_asn_cidrs_with_meta(64501)

    assert error is None
    assert len(bgp_state_calls) == 1


def test_real_asn_source_list_uses_short_optional_timeout(monkeypatch):
    svc = _service()
    captured = {}

    def fake_download_cidrs(sources, *, return_source_details=False):
        captured["sources"] = list(sources)
        return [], "stub"

    monkeypatch.setattr(svc, "_download_cidrs_with_meta", fake_download_cidrs)

    items, source_used, error = svc._download_asn_cidrs_with_meta(64505)

    assert items == []
    assert source_used == "stub"
    assert error is None
    by_name = {source["name"]: source for source in captured["sources"]}
    bgp_state = by_name["ripe-as64505-bgpstate"]
    assert bgp_state["timeout"] == db_service.ASN_OPTIONAL_SOURCE_TIMEOUT_SECONDS


def test_all_sources_down_returns_error_without_raising(monkeypatch):
    svc = _service()
    # Keep the retry/backoff loops from stretching the test past its time budget.
    monkeypatch.setattr(db_service, "SOURCE_FETCH_RETRIES", 1)
    monkeypatch.setattr(db_service, "ASN_FETCH_ATTEMPTS", 1)

    def fake_download(url, timeout=45):
        raise OSError("HTTP 503")

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    items, source_used, error = svc._download_asn_cidrs_with_meta(64502)

    assert items == []
    assert source_used is None
    assert error
    assert "503" in error


def test_empty_source_list_raises(monkeypatch):
    svc = _service()

    with pytest.raises(ValueError):
        svc._download_cidrs_with_meta([])


def test_hung_optional_source_does_not_block_general_method(monkeypatch):
    svc = _service()

    def fake_download(url, timeout=45):
        if "bgp-state" in url:
            threading.Event().wait(2)
            return _bgp_state_json(OPTIONAL_PREFIX)
        if "announced-prefixes" in url:
            return _ripe_json(MAIN_PREFIX)
        return _ripe_geo_json(GEO_PREFIX)

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    started = time.monotonic()
    items, _source_used, details = svc._download_cidrs_with_meta(
        _asn_sources(64503),
        return_source_details=True,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 1.5
    assert {item["cidr"] for item in items} == {MAIN_PREFIX, GEO_PREFIX}

    by_name = {detail["name"]: detail for detail in details}
    assert by_name["ripe-as64503"]["status"] == "ok"
    bgp_state = by_name["ripe-as64503-bgpstate"]
    assert bgp_state["status"] == "error"
    assert "не получен за отведённое время" in bgp_state["error"]


def test_optional_source_used_when_required_sources_fail(monkeypatch):
    svc = _service()
    monkeypatch.setattr(db_service, "SOURCE_FETCH_RETRIES", 1)

    def fake_download(url, timeout=45):
        if "bgp-state" in url:
            return _bgp_state_json(OPTIONAL_PREFIX)
        raise OSError("HTTP 503")

    monkeypatch.setattr(db_service, "_download_text", fake_download)

    items, source_used, details = svc._download_cidrs_with_meta(
        _asn_sources(64504),
        return_source_details=True,
    )

    assert [item["cidr"] for item in items] == [OPTIONAL_PREFIX]
    assert source_used == "ripe-as64504-bgpstate"
    by_name = {detail["name"]: detail for detail in details}
    assert by_name["ripe-as64504-bgpstate"]["status"] == "ok"
    assert by_name["ripe-as64504"]["status"] == "error"
