from __future__ import annotations


from app.services.cidr.pipeline.db_service import CidrDbUpdaterService as S


def test_fallback_on_critical_drop_without_asn_errors():
    # Akamai-class: 32705 → 3952 (~87%), no ASN errors
    assert (
        S._should_preserve_previous_pool(
            previous_cidr_count=32705,
            candidate_cidr_count=3952,
            asn_errors=[],
        )
        is True
    )


def test_no_fallback_on_mild_drop_without_asn_errors():
    assert (
        S._should_preserve_previous_pool(
            previous_cidr_count=1000,
            candidate_cidr_count=800,  # 20%
            asn_errors=[],
        )
        is False
    )


def test_fallback_exactly_at_50_percent_drop():
    assert (
        S._should_preserve_previous_pool(
            previous_cidr_count=1000,
            candidate_cidr_count=500,
            asn_errors=[],
        )
        is True
    )


def test_empty_candidate_still_falls_back():
    assert (
        S._should_preserve_previous_pool(
            previous_cidr_count=1000,
            candidate_cidr_count=0,
            asn_errors=[],
        )
        is True
    )


def test_small_provider_no_spurious_fallback():
    # Both sides below MIN candidate, mild change, no ASN errors
    assert (
        S._should_preserve_previous_pool(
            previous_cidr_count=400,
            candidate_cidr_count=350,
            asn_errors=[],
        )
        is False
    )


def test_update_provider_meta_clears_anomaly_reason_when_none_passed():
    # Lightweight stand-in: call the method with a fake meta object via monkeypatch
    # Prefer testing the branch logic with a minimal fake service + meta.

    class Meta:
        provider_key = "akamai-ips.txt"
        cidr_count = 3952
        anomaly_level = "critical"
        anomaly_reason = "CIDR упали на 87%"
        source_used = None
        expected_asn_min = None
        asn_count = None
        active_asn_count = None
        refresh_status = "ok"
        refresh_error = None
        last_refreshed_at = None

    meta = Meta()

    class FakeQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return meta

    class FakeDb:
        def query(self, *_a, **_k):
            return FakeQuery()

        def add(self, *_a, **_k):
            return None

        def commit(self):
            return None

    svc = S.__new__(S)
    svc.db = FakeDb()
    svc._update_provider_meta(
        "akamai-ips.txt",
        cidr_count=32752,
        source_used="ripe-as20940-geo, ripe-as20940-announced",
        status="ok",
        error=None,
        anomaly_level="none",
        anomaly_reason=None,  # must CLEAR, not skip
        commit=False,
    )
    assert meta.anomaly_level == "none"
    assert meta.anomaly_reason is None
