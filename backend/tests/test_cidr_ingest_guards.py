from __future__ import annotations

from types import SimpleNamespace

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
