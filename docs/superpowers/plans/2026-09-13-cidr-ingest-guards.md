# CIDR P0 Correctness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop large CIDR pool collapses without ASN errors from overwriting good data, stop false global «пул снизился» alerts after partial ingest, and clear stale `anomaly_reason` when a provider is healthy again.

**Architecture:** Keep changes inside `CidrDbUpdaterService` pure helpers + meta/log finalization. Unit-test `_should_preserve_previous_pool` and `_build_degradation_alerts` / `_update_provider_meta` without full network ingest. P1 UX is out of this plan.

**Tech Stack:** Python 3, pytest, SQLAlchemy models `ProviderMeta` / `CidrDbRefreshLog`, existing `PROVIDER_SOURCES`.

**Spec:** `docs/superpowers/specs/2026-09-13-cidr-routing-analysis-design.md`

## Global Constraints

- P0 only: fallback ≥50% drop, global alert / log totals, clear `anomaly_reason`. No P1 UX, no auto-compile, no DPI/antifilter changes.
- Align fallback threshold with existing critical anomaly: **drop ≥ 0.5**.
- Do not break «naturally small» providers (e.g. Cloudflare ~15): no fallback on tiny absolute pools without large drop ratio when already below `CIDR_FALLBACK_MIN_CANDIDATE` (existing branch).
- Preserve previous pool means: do **not** replace `provider_cidr` rows (existing `fallback_applied` path).
- Russian alert strings may stay; behavior change only.
- Commit after each task; `git add -f` for `docs/superpowers/` if needed.
- Run tests via `cd backend && ../.venv/bin/pytest …` or `backend/.venv/bin/pytest` (project venv).

## File map

| File | Role |
|------|------|
| `backend/app/services/cidr/pipeline/db_service.py` | `_should_preserve_previous_pool`, `_build_degradation_alerts`, `_update_provider_meta`, log `total_cidrs` finalization |
| `backend/tests/test_cidr_ingest_guards.py` | Unit tests for P0-1/P0-2/P0-3 |
| `CHANGELOG.md` | Unreleased Fixed |

---

### Task 1: P0-1 — fallback on critical drop (≥50%)

**Files:**
- Modify: `backend/app/services/cidr/pipeline/db_service.py` (`_should_preserve_previous_pool`)
- Create: `backend/tests/test_cidr_ingest_guards.py`

**Interfaces:**
- Consumes: existing `CIDR_FALLBACK_MIN_CANDIDATE`, `CIDR_FALLBACK_DROP_RATIO_WITH_ERRORS`
- Produces: same signature

```python
@staticmethod
def _should_preserve_previous_pool(*, previous_cidr_count, candidate_cidr_count, asn_errors) -> bool
```

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_cidr_ingest_guards.py
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
```

- [ ] **Step 2: Run tests — expect FAIL on Akamai-class case**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_cidr_ingest_guards.py::test_fallback_on_critical_drop_without_asn_errors tests/test_cidr_ingest_guards.py::test_fallback_exactly_at_50_percent_drop -v`

Expected: FAIL (`assert False is True`) — current code returns False when candidate ≥ 500 and no asn_errors.

- [ ] **Step 3: Implement**

In `_should_preserve_previous_pool`, **before** the early return:

```python
if candidate_cidr_count >= CIDR_FALLBACK_MIN_CANDIDATE and not asn_errors:
    return False
```

insert critical-drop check. Concrete final function body:

```python
@staticmethod
def _should_preserve_previous_pool(*, previous_cidr_count, candidate_cidr_count, asn_errors):
    if previous_cidr_count <= 0:
        return False
    if candidate_cidr_count <= 0:
        return True

    if candidate_cidr_count == previous_cidr_count and not asn_errors:
        return False

    drop_ratio = 1.0 - (float(candidate_cidr_count) / float(previous_cidr_count))

    # Align with critical anomaly (≥50%): preserve even without ASN errors.
    if drop_ratio >= 0.5:
        return True

    if candidate_cidr_count >= CIDR_FALLBACK_MIN_CANDIDATE and not asn_errors:
        return False

    if candidate_cidr_count < CIDR_FALLBACK_MIN_CANDIDATE:
        if previous_cidr_count < CIDR_FALLBACK_MIN_CANDIDATE and not asn_errors:
            return False
        return True

    if asn_errors and drop_ratio >= CIDR_FALLBACK_DROP_RATIO_WITH_ERRORS:
        return True
    return False
```

Note: compute `drop_ratio` once; the later ASN-error branch still uses `CIDR_FALLBACK_DROP_RATIO_WITH_ERRORS` (0.45) for drops in `[0.45, 0.5)` when ASN errors exist.

- [ ] **Step 4: Run full new test file**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_cidr_ingest_guards.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cidr/pipeline/db_service.py backend/tests/test_cidr_ingest_guards.py
git commit -m "$(cat <<'EOF'
Preserve CIDR pools on critical drop without ASN errors.

EOF
)"
```

---

### Task 2: P0-3 — clear stale `anomaly_reason`

**Files:**
- Modify: `backend/app/services/cidr/pipeline/db_service.py` (`_update_provider_meta`)
- Modify: `backend/tests/test_cidr_ingest_guards.py`

**Interfaces:**
- Problem: callers pass `anomaly_reason=result.get("anomaly_reason")` which is `None` when healthy, but `_update_provider_meta` treats `None` as «do not update field».
- Fix: use an explicit unset sentinel so `None` clears the column.

- [ ] **Step 1: Failing test**

Append to `test_cidr_ingest_guards.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL** (reason still `"CIDR упали на 87%"`)

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_cidr_ingest_guards.py::test_update_provider_meta_clears_anomaly_reason_when_none_passed -v`

- [ ] **Step 3: Implement sentinel in `_update_provider_meta`**

Near top of `db_service.py` (module level):

```python
_UNSET = object()
```

Change signature default:

```python
def _update_provider_meta(
    self,
    provider_key,
    *,
    cidr_count,
    source_used,
    status,
    error,
    expected_asn_min=None,
    asn_count=None,
    active_asn_count=None,
    anomaly_level=None,
    anomaly_reason=_UNSET,
    commit=True,
):
```

Replace reason update block:

```python
if anomaly_level is not None:
    meta.anomaly_level = str(anomaly_level)
if anomaly_reason is not _UNSET:
    meta.anomaly_reason = str(anomaly_reason) if anomaly_reason else None
elif anomaly_level is not None and str(anomaly_level) in ("none", "info"):
    # Belt-and-suspenders if a caller omits reason
    meta.anomaly_reason = None
```

Call sites that already pass `anomaly_reason=result.get("anomaly_reason")` now correctly clear on `None`. Call sites that omit `anomaly_reason` keep previous reason unless level is none/info (belt-and-suspenders).

- [ ] **Step 4: Run tests**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_cidr_ingest_guards.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cidr/pipeline/db_service.py backend/tests/test_cidr_ingest_guards.py
git commit -m "$(cat <<'EOF'
Clear stale CIDR anomaly_reason when provider is healthy.

EOF
)"
```

---

### Task 3: P0-2 — fix global drop alert / log totals

**Files:**
- Modify: `backend/app/services/cidr/pipeline/db_service.py` (`refresh_all_providers` log finalization + `_build_degradation_alerts`)
- Modify: `backend/tests/test_cidr_ingest_guards.py`

**Design (minimal + preferred):**

1. When finishing a refresh log, set `log_entry.total_cidrs` to **sum of all `ProviderMeta.cidr_count`**, not only providers touched in this run.  
2. In `_build_degradation_alerts`, skip global compare when last log is **partial refresh**: `providers_updated < len(PROVIDER_SOURCES)` (import `PROVIDER_SOURCES`).  
3. For full refreshes, compare log totals as today (now meaningful after (1)), threshold remains `current < previous * 0.7`.

- [ ] **Step 1: Failing tests**

```python
def test_build_degradation_alerts_skips_global_for_partial_log():
    from app.services.cidr.pipeline.provider_sources import PROVIDER_SOURCES

    last = SimpleNamespace(
        id=5,
        status="ok",
        total_cidrs=32752,
        providers_updated=1,
        started_at=None,
    )
    prev = SimpleNamespace(
        id=4,
        status="ok",
        total_cidrs=121539,
        providers_updated=len(PROVIDER_SOURCES),
        started_at=None,
    )
    metas = [
        SimpleNamespace(
            provider_key="akamai-ips.txt",
            anomaly_level="none",
            anomaly_reason=None,
            cidr_count=32752,
        )
    ]

    class FakeLogQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return self._rows[0] if self._rows else None

    class FakeDb:
        def query(self, model):
            # prev_log lookup
            return FakeLogQuery([prev])

    svc = S.__new__(S)
    svc.db = FakeDb()

    # Monkeypatch model access used inside method
    import app.services.cidr.pipeline.db_service as mod

    real_get = mod._get_models

    class FakeModels:
        CidrDbRefreshLog = object

    mod._get_models = lambda: FakeModels
    try:
        alerts = svc._build_degradation_alerts(last, metas)
    finally:
        mod._get_models = real_get

    assert not any(a.get("scope") == "global" for a in alerts)


def test_build_degradation_alerts_flags_global_on_full_drop():
    from app.services.cidr.pipeline.provider_sources import PROVIDER_SOURCES

    n = len(PROVIDER_SOURCES)
    last = SimpleNamespace(id=2, status="ok", total_cidrs=50000, providers_updated=n, started_at=None)
    prev = SimpleNamespace(id=1, status="ok", total_cidrs=150000, providers_updated=n, started_at=None)
    metas = []

    class FakeLogQuery:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return prev

    class FakeDb:
        def query(self, model):
            return FakeLogQuery()

    svc = S.__new__(S)
    svc.db = FakeDb()
    import app.services.cidr.pipeline.db_service as mod

    real_get = mod._get_models

    class FakeModels:
        CidrDbRefreshLog = object

    mod._get_models = lambda: FakeModels
    try:
        alerts = svc._build_degradation_alerts(last, metas)
    finally:
        mod._get_models = real_get

    assert any(a.get("scope") == "global" for a in alerts)
```

If FakeDb/query patching is too brittle against real SQLAlchemy `filter`, prefer extracting a tiny pure helper:

```python
@staticmethod
def _should_emit_global_pool_drop_alert(*, last_log, prev_log, known_provider_count: int) -> bool:
    ...
```

and unit-test that instead (recommended if `_build_degradation_alerts` resists mocking). Implementer may extract this helper — keep behavior identical.

- [ ] **Step 2: Run — expect FAIL** (partial currently emits global)

- [ ] **Step 3: Implement**

**A. Log total = full meta sum** in `refresh_all_providers` where `log_entry.total_cidrs = total_cidrs` (~line 744):

```python
m = _get_models()
full_pool_total = int(
    sum(int(pm.cidr_count or 0) for pm in self.db.query(m.ProviderMeta).all())
)
log_entry.total_cidrs = full_pool_total
# keep local `total_cidrs` return value as full_pool_total for API consistency
total_cidrs = full_pool_total
```

Also set the returned summary `"total_cidrs": total_cidrs` accordingly (already uses variable).

**B. Skip partial in `_build_degradation_alerts`:**

```python
from app.services.cidr.pipeline.provider_sources import PROVIDER_SOURCES

known = len(PROVIDER_SOURCES)
...
if last_log and prev_log and ...:
    updated = int(getattr(last_log, "providers_updated", 0) or 0)
    if updated < known:
        # partial ingest — do not compare run totals
        pass
    else:
        previous_total = int(prev_log.total_cidrs or 0)
        current_total = int(last_log.total_cidrs or 0)
        if current_total < int(previous_total * 0.7):
            alerts.append({...})
```

- [ ] **Step 4: pytest**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_cidr_ingest_guards.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cidr/pipeline/db_service.py backend/tests/test_cidr_ingest_guards.py
git commit -m "$(cat <<'EOF'
Fix CIDR global drop alert for partial refreshes.

EOF
)"
```

---

### Task 4: Changelog + optional one-shot meta cleanup note

**Files:**
- Modify: `CHANGELOG.md` under `## [Unreleased]` → `### 🐛 Fixed`

- [ ] **Step 1: Add bullets**

```markdown
- **CIDR safe-fallback** — при падении пула ≥50% предыдущий набор сохраняется даже без ASN-errors (кейс Akamai geo empty).
- **CIDR global alert** — partial refresh больше не сравнивается с full-логом как «общий пул упал»; в журнал пишется сумма всех `provider_meta`.
- **CIDR anomaly_reason** — при `anomaly_level=none` причина очищается.
```

- [ ] **Step 2: Optional ops note in report only** (no code): existing stale `anomaly_reason` on live DB clears on next successful provider refresh; or one-liner SQL if operator wants immediate clear — document in commit body, do not run destructive SQL in plan unless user asks.

- [ ] **Step 3: Mark analysis spec implemented**

Set `**Статус:** implemented` in `docs/superpowers/specs/2026-09-13-cidr-routing-analysis-design.md` and `git add -f`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git add -f docs/superpowers/specs/2026-09-13-cidr-routing-analysis-design.md
git commit -m "$(cat <<'EOF'
Document CIDR ingest guard fixes in changelog.

EOF
)"
```

---

## Spec coverage (self-review)

| Spec item | Task |
|-----------|------|
| P0-1 fallback ≥50% without ASN errors | 1 |
| Small-provider behavior preserved | 1 tests |
| P0-3 clear anomaly_reason | 2 |
| P0-2 global alert / partial | 3 |
| Log total semantics | 3 |
| Changelog | 4 |
| P1 UX | out of plan |

**Placeholder scan:** none.  
**Type consistency:** `_UNSET` sentinel; `_should_preserve_previous_pool` signature unchanged.
