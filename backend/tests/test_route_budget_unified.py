"""Route budget: counts path and CIDR-list path must share one algorithm.

The list path (``_apply_total_route_limit``) is used by the real build, the
counts path (``_estimate_cidr_matches_from_db_impl``) by the fast preview.
Both must hand out the same per-file budget for the same input.
"""

import random
from types import SimpleNamespace

import pytest

from app.models import ProviderMeta
from app.services.cidr.constants import IP_FILES
from app.services.cidr.pipeline import db_pipeline, route_limits

FILES = [
    "akamai-ips.txt",
    "amazon-ips.txt",
    "cloudflare-ips.txt",
    "fastly-ips.txt",
    "google-ips.txt",
    "hetzner-ips.txt",
    "ovh-ips.txt",
]

AKAMAI = "akamai-ips.txt"
AMAZON = "amazon-ips.txt"
CLOUDFLARE = "cloudflare-ips.txt"
FASTLY = "fastly-ips.txt"

# Snapshots taken at import time: the live provider catalog is one mutable dict
# shared by every module, so a leaked change from another test would silently
# make the counts path skip a provider that the list path still keeps.
_CATALOG = dict(IP_FILES)
_ALLOCATE_ROUTE_BUDGET = route_limits._allocate_route_budget
_APPLY_TOTAL_ROUTE_LIMIT = route_limits._apply_total_route_limit
_COMPRESS_CIDRS_TO_LIMIT = route_limits._compress_cidrs_to_limit


@pytest.fixture(autouse=True)
def _pinned_budget_state(monkeypatch):
    """Keep the budget paths on this module's own module-level state.

    Both paths read ``IP_FILES`` (counts path filters selected files by it, the
    list path does not), the env-driven default limit and function references
    kept per module. Pinning them makes the test independent of what other
    tests in the full run did before it.
    """
    catalog = dict(_CATALOG)
    missing = [name for name in FILES if name not in catalog]
    assert not missing, f"provider catalog lost {missing}"

    monkeypatch.setattr(db_pipeline, "IP_FILES", catalog)
    monkeypatch.setattr(route_limits, "IP_FILES", catalog)
    monkeypatch.setattr(db_pipeline, "_allocate_route_budget", _ALLOCATE_ROUTE_BUDGET)
    monkeypatch.setattr(route_limits, "_allocate_route_budget", _ALLOCATE_ROUTE_BUDGET)
    monkeypatch.setattr(db_pipeline, "_apply_total_route_limit", _APPLY_TOTAL_ROUTE_LIMIT)
    monkeypatch.setattr(route_limits, "_apply_total_route_limit", _APPLY_TOTAL_ROUTE_LIMIT)
    monkeypatch.setattr(route_limits, "_compress_cidrs_to_limit", _COMPRESS_CIDRS_TO_LIMIT)
    monkeypatch.setattr(db_pipeline, "_get_openvpn_route_total_cidr_limit", lambda: 1500)


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
    """Only ProviderMeta is read by the fast estimate path."""

    def __init__(self, meta_rows):
        self._meta_rows = meta_rows

    def query(self, model):
        if model is ProviderMeta:
            return _FakeQuery(self._meta_rows)
        return _FakeQuery([])


def _distinct_cidrs(count, base):
    """Distinct /24 blocks from distinct /16s — no containment, no duplicates.

    With such input ``_compress_cidrs_to_limit`` keeps exactly ``min(count, budget)``
    routes, so the list path exposes the raw budget directly.
    """
    return [f"{base}.{index // 256}.{index % 256}.0/24" for index in range(count)]


def _counts_path(counts, limit, **dpi):
    """Budgets from the estimate path (the one that works with counts only)."""
    session = _FakeSession(
        [
            SimpleNamespace(
                provider_key=name,
                refresh_status="ok",
                cidr_count=count,
                source_used="test",
            )
            for name, count in counts.items()
        ]
    )
    result = db_pipeline._estimate_cidr_matches_from_db_impl(
        db=session,
        cidr_db=session,
        selected_files=list(counts),
        region_scopes=["all"],
        filter_by_antifilter=False,
        total_cidr_limit=limit,
        **dpi,
    )
    budgets = {item["file"]: item["cidr_count"] for item in result["estimated"]}
    return budgets, result.get("global_route_optimization")


def _list_path(counts, limit, **dpi):
    """Budgets from the list path (the one that compresses real CIDR lists)."""
    entries = [
        {"file": name, "cidrs": _distinct_cidrs(count, 10 + index)}
        for index, (name, count) in enumerate(counts.items())
    ]
    adjusted, meta = route_limits._apply_total_route_limit(entries, limit, **dpi)
    budgets = {item["file"]: len(item["cidrs"]) for item in adjusted}
    return budgets, meta


def _scenario(rng):
    names = rng.sample(FILES, rng.randint(2, len(FILES)))
    counts = {name: rng.randint(1, 40) for name in names}
    total = sum(counts.values())
    limit = rng.choice(
        [
            rng.randint(1, len(names)),
            rng.randint(len(names), total),
            max(1, total - 1),
            total + 1,
            total + 20,
        ]
    )
    priority = rng.sample(names, rng.randint(0, min(2, len(names))))
    mandatory_pool = [name for name in names if name not in priority]
    mandatory = rng.sample(mandatory_pool, rng.randint(0, min(1, len(mandatory_pool))))
    min_budget = rng.choice([0, 1, 5, 20, 100])
    return counts, limit, priority, mandatory, min_budget


def test_counts_and_list_path_agree_on_random_budgets():
    rng = random.Random(20261113)

    for _ in range(20):
        counts, limit, priority, mandatory, min_budget = _scenario(rng)
        dpi = {
            "dpi_priority_files": priority or None,
            "dpi_mandatory_files": mandatory or None,
            "dpi_priority_min_budget": min_budget,
        }

        counts_budgets, counts_meta = _counts_path(counts, limit, **dpi)
        list_budgets, list_meta = _list_path(counts, limit, **dpi)

        assert counts_budgets == list_budgets
        assert (counts_meta is None) == (list_meta is None)
        if counts_meta is None:
            continue

        assert counts_meta["strategy"] == list_meta["strategy"]
        assert counts_meta["limit"] == list_meta["limit"] == limit
        assert counts_meta["original_total_cidr_count"] == sum(counts.values())
        assert (
            counts_meta["compressed_total_cidr_count"]
            == list_meta["compressed_total_cidr_count"]
            == sum(list_budgets.values())
        )
        # Same key set on both paths, so the UI reads one meta format.
        assert set(counts_meta) == set(list_meta)
        if counts_meta["strategy"] == "none":
            continue
        assert [item["file"] for item in counts_meta["files"]] == [
            item["file"] for item in list_meta["files"]
        ]


def test_dpi_priority_and_mandatory_are_respected():
    counts = {AKAMAI: 50, AMAZON: 50, CLOUDFLARE: 10, FASTLY: 10}
    dpi = {
        "dpi_priority_files": [FASTLY],
        "dpi_mandatory_files": [CLOUDFLARE],
        "dpi_priority_min_budget": 8,
    }

    for budgets, meta in (
        _counts_path(counts, 30, **dpi),
        _list_path(counts, 30, **dpi),
    ):
        assert sum(budgets.values()) == 30
        # Mandatory file always survives with at least one route.
        assert budgets[CLOUDFLARE] >= 1
        # Priority file keeps its reserved minimum.
        assert budgets[FASTLY] >= 8
        assert meta["strategy"] == "global_total_route_limit"
        assert meta["dpi_mandatory"]["mandatory_files"] == [CLOUDFLARE]
        assert meta["dpi_mandatory"]["dropped_mandatory_files"] == []
        assert "warning" not in meta
        assert meta["dpi_priority"]["priority_files"] == [CLOUDFLARE, FASTLY]
        assert meta["dpi_priority"]["priority_min_budget"] == 8
        flags = {item["file"]: (item["dpi_priority"], item["dpi_mandatory"]) for item in meta["files"]}
        assert flags[FASTLY] == (True, False)
        assert flags[CLOUDFLARE] == (True, True)
        assert flags[AKAMAI] == (False, False)


def test_mandatory_dropped_sets_warning_on_both_paths():
    counts = {AKAMAI: 40, AMAZON: 30, CLOUDFLARE: 10}
    dpi = {"dpi_mandatory_files": [AKAMAI, AMAZON, CLOUDFLARE]}

    # Three mandatory files, two routes: the smallest mandatory one is dropped
    # and both paths report it the same way.
    for budgets, meta in (
        _counts_path(counts, 2, **dpi),
        _list_path(counts, 2, **dpi),
    ):
        assert budgets == {AKAMAI: 1, AMAZON: 1, CLOUDFLARE: 0}
        assert meta["dpi_mandatory"]["dropped_mandatory_files"] == [CLOUDFLARE]
        assert meta["warning"] == "Не все обязательные detected-провайдеры поместились в лимит"


def test_under_limit_keeps_strategy_none_and_totals():
    counts = {AKAMAI: 3, CLOUDFLARE: 4}

    for budgets, meta in (
        _counts_path(counts, 10),
        _list_path(counts, 10),
    ):
        assert budgets == counts
        assert meta == {
            "strategy": "none",
            "limit": 10,
            "original_total_cidr_count": 7,
            "compressed_total_cidr_count": 7,
            "warning": None,
        }


def test_limit_below_file_count_gives_one_route_to_limit_files():
    # Fixed semantics: when the limit is smaller than the number of non-empty
    # files, exactly `limit` files keep one route each (priority/mandatory first),
    # the rest get zero. No file gets more than one route in that branch.
    counts = {AKAMAI: 5, AMAZON: 30, CLOUDFLARE: 9, FASTLY: 1}

    for budgets, meta in (
        _counts_path(counts, 2),
        _list_path(counts, 2),
    ):
        assert set(budgets.values()) == {0, 1}
        assert sum(budgets.values()) == 2
        assert meta["strategy"] == "global_total_route_limit"
        assert meta["compressed_total_cidr_count"] == 2
        # Biggest files win when no DPI preference is given.
        assert budgets[AMAZON] == 1
        assert budgets[CLOUDFLARE] == 1

    for budgets, _meta in (
        _counts_path(counts, 2, dpi_mandatory_files=[FASTLY]),
        _list_path(counts, 2, dpi_mandatory_files=[FASTLY]),
    ):
        assert budgets[FASTLY] == 1
        assert sum(budgets.values()) == 2


def test_file_order_does_not_change_distribution():
    counts = {
        AKAMAI: 13,
        AMAZON: 27,
        CLOUDFLARE: 7,
        FASTLY: 21,
        "google-ips.txt": 3,
    }
    dpi = {"dpi_priority_files": [CLOUDFLARE], "dpi_priority_min_budget": 4}
    reference, _meta = _counts_path(counts, 25, **dpi)

    rng = random.Random(7)
    for _ in range(10):
        shuffled = list(counts.items())
        rng.shuffle(shuffled)
        shuffled_counts = dict(shuffled)
        budgets, _meta = _counts_path(shuffled_counts, 25, **dpi)
        assert budgets == reference
        list_budgets, _meta = _list_path(shuffled_counts, 25, **dpi)
        assert list_budgets == reference


def test_estimate_quality_report_keeps_keys():
    counts = {AKAMAI: 40, CLOUDFLARE: 20}
    session = _FakeSession(
        [
            SimpleNamespace(
                provider_key=name,
                refresh_status="ok",
                cidr_count=count,
                source_used="test",
            )
            for name, count in counts.items()
        ]
    )

    result = db_pipeline._estimate_cidr_matches_from_db_impl(
        db=session,
        cidr_db=session,
        selected_files=list(counts),
        total_cidr_limit=30,
        dpi_mandatory_files=[CLOUDFLARE],
    )

    assert set(result["quality_report"]) == {"providers", "totals", "dropped_mandatory_files", "warnings"}
    assert set(result["quality_report"]["totals"]) == {
        "requested_files",
        "raw_db_cidrs",
        "after_scope_cidrs",
        "after_ru_exclusion_cidrs",
        "after_antifilter_cidrs",
        "final_after_limit_cidrs",
    }
    assert set(result["global_route_optimization"]) == {
        "strategy",
        "limit",
        "original_total_cidr_count",
        "compressed_total_cidr_count",
        "files",
        "dpi_mandatory",
    }
