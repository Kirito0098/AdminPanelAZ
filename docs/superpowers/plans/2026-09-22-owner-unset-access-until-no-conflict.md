# Owner-unset access_until: no client conflict — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user has no `access_until`, allow setting any per-client access deadline without `409 access_until_conflict`; keep conflict+override when the owner deadline is set.

**Architecture:** Single rule change in `client_access_conflicts_with_owner`. All PATCH access-until / WG set-expiry paths already call `_maybe_access_until_conflict`. No API or UI redesign.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, pytest, existing dashboard conflict dialog.

**Spec:** `docs/superpowers/specs/2026-09-22-owner-unset-access-until-no-conflict-design.md`

## Global Constraints

- User-facing copy in Russian
- TDD: failing test first, then minimal production code
- Do not commit unless the user explicitly asks; skip commit steps (or leave them unchecked) until asked
- Work on branch `release/2.26.0` (never feature→main)
- Choice **A**: owner **with** deadline → any divergence still conflicts (409 + confirm override)
- Owner `access_until is None` → never conflict for client deadline writes
- Keep safe 409 payload (`isoformat` only when datetime is not None) — already partially applied in working tree
- CHANGELOG `[Unreleased]` note in Russian when done
- Update `docs/podpiska.md` to match the new rule

---

## File map

| File | Responsibility |
|------|----------------|
| Modify: `backend/app/services/user_subscription.py` | Conflict rule: no conflict when owner deadline is unset |
| Modify: `backend/app/routers/client_access.py` | Keep null-safe `user_access_until` in 409 JSON (defensive) |
| Modify: `backend/tests/test_user_subscription.py` | Unit coverage for owner-unset + client date |
| Modify: `backend/tests/test_access_until.py` | Endpoint: owner unset + client date → 200, not 409 |
| Modify: `docs/podpiska.md` | Document exception when owner has no deadline |
| Modify: `CHANGELOG.md` | `[Unreleased]` Changed note |

Optional (out of core success criteria; only if already dirty on branch): `frontend/src/components/dashboard/ClientActionsDialog.tsx` toast should surface `Error.message` — do not expand scope for UI polish unless asked.

---

### Task 1: Unit rule — owner without deadline never conflicts

**Files:**
- Modify: `backend/tests/test_user_subscription.py` (`test_client_access_conflicts_with_owner_compares_normalized_deadlines` area ~156–174)
- Modify: `backend/app/services/user_subscription.py` (`client_access_conflicts_with_owner` ~94–106)

**Interfaces:**
- Consumes: `get_user_access_until(owner) -> datetime | None`, `_as_utc`
- Produces: `client_access_conflicts_with_owner(db, *, owner, client_access_until) -> bool` with new semantics

- [ ] **Step 1: Write the failing unit assertions**

Extend `test_client_access_conflicts_with_owner_compares_normalized_deadlines` (or add a sibling test in the same file) with an owner that has `access_until=None`:

```python
def test_client_access_conflicts_with_owner_unset_allows_any_client_deadline(db):
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    owner = User(
        username="owner-no-deadline",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=None,
    )
    db.add(owner)
    db.commit()

    assert usub.client_access_conflicts_with_owner(db, owner=owner, client_access_until=None) is False
    assert usub.client_access_conflicts_with_owner(db, owner=owner, client_access_until=future) is False
```

Keep existing assertions for owner **with** deadline unchanged (equal → False; later / None → True).

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -m pytest \
  tests/test_user_subscription.py::test_client_access_conflicts_with_owner_unset_allows_any_client_deadline -v
```

Expected: FAIL — `client_access_until=future` currently returns `True` (treated as conflict).

- [ ] **Step 3: Minimal implementation**

Replace body of `client_access_conflicts_with_owner` in `backend/app/services/user_subscription.py` with:

```python
def client_access_conflicts_with_owner(
    db: Session,
    *,
    owner: User | None,
    client_access_until: datetime | None,
) -> bool:
    _ = db
    if owner is None:
        return False
    user_until = get_user_access_until(owner)
    if user_until is None:
        return False
    return _as_utc(client_access_until) != user_until
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run:

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -m pytest \
  tests/test_user_subscription.py::test_client_access_conflicts_with_owner_compares_normalized_deadlines \
  tests/test_user_subscription.py::test_client_access_conflicts_with_owner_unset_allows_any_client_deadline -v
```

Expected: PASS (both).

- [ ] **Step 5: Commit** (only if user asked)

```bash
git add backend/app/services/user_subscription.py backend/tests/test_user_subscription.py
git commit -m "$(cat <<'EOF'
fix(subscription): allow client access_until when owner has none

EOF
)"
```

---

### Task 2: Endpoint — PATCH succeeds when owner has no deadline

**Files:**
- Modify: `backend/tests/test_access_until.py` (`test_client_access_until_conflict_when_owner_has_no_deadline` ~512–544 — rewrite)
- Modify: `backend/app/routers/client_access.py` (`_maybe_access_until_conflict` ~91–115 — ensure null-safe 409 payload)

**Interfaces:**
- Consumes: `client_access_conflicts_with_owner` from Task 1
- Produces: HTTP 200 + `_set_access_until` called when owner has no deadline; HTTP 409 unchanged when owner has a different deadline

- [ ] **Step 1: Rewrite the failing/incorrect endpoint expectation**

Replace `test_client_access_until_conflict_when_owner_has_no_deadline` with a test that expects **no** conflict:

```python
def test_client_access_until_allows_deadline_when_owner_has_none():
    """Owner without access_until: client deadline may be set freely (no 409)."""
    engine, db = _make_db()
    try:
        node = _make_node(db)
        requested_until = datetime(2026, 12, 31, 23, 59, 59, 999000, tzinfo=timezone.utc)
        admin = _make_user(db, username="admin", role=UserRole.admin)
        owner = _make_user(db, username="Novikov", role=UserRole.user, access_until=None)
        _make_owned_client(
            db,
            node_id=node.id,
            owner_id=owner.id,
            client_name="TopTinker",
            protocols=[VpnType.openvpn],
        )
        client = _client_access_api(db, admin=admin)

        with (
            patch.object(
                client_access,
                "_set_access_until",
                return_value={"access_until": requested_until.isoformat()},
            ) as set_until,
            patch.object(client_access, "log_action"),
            patch.object(client_access, "_replicate_policy_after_success"),
        ):
            response = client.patch(
                "/api/client-access/openvpn/TopTinker/access-until",
                json={"access_until": requested_until.isoformat()},
            )

        assert response.status_code == 200
        assert response.json()["access_until"] == requested_until.isoformat()
        set_until.assert_called_once()
    finally:
        db.close()
        engine.dispose()
```

If this test already exists expecting 409, renaming + rewriting is required so CI matches the spec.

Also confirm `test_client_access_until_conflict_returns_409_without_override` still expects 409 when the owner **has** a deadline.

- [ ] **Step 2: Run endpoint tests**

If Task 1 is done, this new test should **pass** immediately. If Task 1 is not done, it should still fail with 409/500 — finish Task 1 first.

Run:

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -m pytest \
  tests/test_access_until.py::test_client_access_until_allows_deadline_when_owner_has_none \
  tests/test_access_until.py::test_client_access_until_conflict_returns_409_without_override -v
```

Expected: both PASS.

- [ ] **Step 3: Ensure null-safe 409 payload**

In `backend/app/routers/client_access.py`, `_maybe_access_until_conflict` must build JSON like:

```python
user_until = user_subscription.get_user_access_until(owner) if owner else None
return JSONResponse(
    status_code=status.HTTP_409_CONFLICT,
    content={
        "code": "access_until_conflict",
        "user_access_until": user_until.isoformat() if user_until else None,
        "client_access_until": access_until.isoformat() if access_until else None,
    },
)
```

Do **not** call `.isoformat()` on a possibly-`None` `get_user_access_until(owner)` result. If the working tree already has this, leave it; do not regress.

- [ ] **Step 4: Re-run related suite slice**

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -m pytest \
  tests/test_user_subscription.py::test_client_access_conflicts_with_owner_compares_normalized_deadlines \
  tests/test_user_subscription.py::test_client_access_conflicts_with_owner_unset_allows_any_client_deadline \
  tests/test_access_until.py::test_client_access_until_allows_deadline_when_owner_has_none \
  tests/test_access_until.py::test_client_access_until_conflict_returns_409_without_override \
  tests/test_access_until.py::test_wg_set_expiry_conflict_returns_409_without_override -q
```

Expected: all PASS.

- [ ] **Step 5: Commit** (only if user asked)

```bash
git add backend/tests/test_access_until.py backend/app/routers/client_access.py
git commit -m "$(cat <<'EOF'
test(subscription): PATCH access-until when owner has no deadline

EOF
)"
```

---

### Task 3: Docs + CHANGELOG

**Files:**
- Modify: `docs/podpiska.md` (section «Срок на клиенте vs на пользователе» ~38–42)
- Modify: `CHANGELOG.md` (`## [Unreleased]` → `### 🔄 Changed`)

**Interfaces:** none (documentation only)

- [ ] **Step 1: Update podpiska.md**

Replace the conflict paragraph so it states the exception explicitly, for example:

```markdown
На дашборде в карточке клиента по-прежнему можно менять **срок доступа профиля**.
Если у владельца **не задан** `access_until`, срок профиля можно выставлять свободно (без `409`).
Если у владельца срок **задан** и новый срок профиля **не совпадает** с ним, панель вернёт **409** с кодом `access_until_conflict`. Можно подтвердить переопределение или нажать **«Синхронизировать с пользователем»** — тогда срок этого клиента (все протоколы на узле) приводится к сроку владельца.
```

Keep the following sentences about end-of-day and WireGuard «Продлить срок» (still guarded when owner has a deadline).

- [ ] **Step 2: Add CHANGELOG entry**

Under `## [Unreleased]` → `### 🔄 Changed`, add:

```markdown
- **Дашборд / срок профиля** — если у владельца не задан `access_until`, срок конфига можно сохранять без `409 access_until_conflict`; при заданном сроке владельца поведение без изменений (подтверждение переопределения / синхронизация).
```

- [ ] **Step 3: Commit** (only if user asked)

```bash
git add docs/podpiska.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: free client access_until when owner has none

EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|---|---|
| Owner unset → no conflict for any client deadline | Task 1 |
| Owner set → divergence still 409 / override (choice A) | Task 1 keep + Task 2 regression |
| Null-safe 409 payload | Task 2 Step 3 |
| Endpoint TopTinker/Novikov style success | Task 2 |
| `docs/podpiska.md` + CHANGELOG | Task 3 |
| No frontend redesign | (explicitly skipped) |
| Cascade when owner later gets a deadline | unchanged; not in scope |

No placeholders remain. Types match existing helpers.
