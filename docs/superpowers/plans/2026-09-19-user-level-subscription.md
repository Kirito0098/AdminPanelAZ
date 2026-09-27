# User-Level Subscription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move subscription access period to `User.access_until`, cascade expiry/renewal/unlock to owned clients, add user portal links, dual TG reminders, and admin conflict guards — per Fider #28.

**Architecture:** `User.access_until` is source of truth. New `app/services/user_subscription.py` owns cascade (set user deadline → sync owned clients; expire → `access_expired` only; unlock → extend user then cascade). Existing per-client policies and `ClientPortalToken` remain. `UserPortalToken` lists all owned clients. Create-config gate checks user subscription. Client `access_until` PATCH requires `confirm_override` when diverging from owner.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, React+Vite, pytest, existing `access_until` / unlock / portal / admin_notify / user_reminder pipelines.

**Spec:** `docs/superpowers/specs/2026-09-19-user-level-subscription-design.md`

## Global Constraints

- User-facing copy in Russian
- TDD: failing test first, then minimal production code
- Do not commit unless the user explicitly asks; skip commit steps in this plan
- Work on branch `release/2.26.0` (never feature→main)
- Manual / permanent client blocks must never be cleared by user unlock or user extend
- `User.access_until = NULL` means unlimited (no subscription cascade)
- Orphan clients (no `owner_id`) keep legacy client-only behavior
- CHANGELOG `[Unreleased]` notes in Russian when feature is complete
- Do not remove cert-expiry Telegram reminders

---

## File map

| File | Responsibility |
|------|----------------|
| Modify: `backend/app/models.py` | `User.access_until`; `UserPortalToken`; unlock redemption `user_id`; DEFAULT_TG events |
| Modify: `backend/app/database.py` | Column + `user_portal_tokens` table; backfill migration |
| Create: `backend/app/services/user_subscription.py` | get/set user access, cascade sync/expire/unexpire, conflict helpers |
| Modify: `backend/app/services/access_until.py` | Optional thin wrappers if needed; keep client primitives |
| Modify: `backend/app/services/access_expiry_worker.py` | Also run user-subscription expire pass |
| Modify: `backend/app/services/unlock_codes.py` | Redeem extends User when owner exists |
| Modify: `backend/app/services/self_service.py` | `enforce_user_can_create_config` → subscription gate |
| Modify: `backend/app/services/client_portal.py` | User portal token CRUD + multi-client payload |
| Modify: `backend/app/routers/public_portal.py` | Resolve user vs client token |
| Modify: `backend/app/routers/client_portal.py` | Admin endpoints for user portal link |
| Modify: `backend/app/routers/client_access.py` | `confirm_override` on set access_until; sync-from-user |
| Modify: `backend/app/routers/users.py` | PATCH/GET expose `access_until`; set triggers cascade |
| Modify: `backend/app/schemas.py` | User In/Out `access_until`; AccessUntilRequest flags |
| Modify: `backend/app/services/user_reminder_service.py` | Access-expiry reminder type |
| Modify: `backend/app/services/admin_notify.py` | Event labels + formatting for access reminders |
| Modify: `backend/app/config.py` | `self_service_reminder_access_days_threshold` |
| Modify: `frontend/src/types.ts` | User + portal + access request types |
| Modify: `frontend/src/components/settings/UsersTab.tsx` | Edit user `access_until` |
| Modify: dashboard / access UI (existing access-until controls) | Conflict warning + confirm + sync |
| Modify: `frontend/src/pages/SubscriptionPage.tsx` / portal UI | User portal link management |
| Modify: `docs/podpiska.md` | User-level subscription behavior |
| Modify: `CHANGELOG.md` | Unreleased |
| Create: `backend/tests/test_user_subscription.py` | Core cascade / migrate / gate tests |
| Modify: `backend/tests/test_unlock_codes.py` | User-level redeem |
| Modify: `backend/tests/test_client_portal.py` / public portal tests | User portal |
| Modify: `backend/tests/test_user_config_access.py` | Subscription create gate |
| Create/Modify: reminder tests | Access vs cert separation |

---

### Task 1: `User.access_until` model + DB column + pure helpers

**Files:**
- Modify: `backend/app/models.py` (`User` ~65–93)
- Modify: `backend/app/database.py` (`users` migrations list ~1297–1311)
- Create: `backend/app/services/user_subscription.py`
- Test: `backend/tests/test_user_subscription.py`

**Interfaces:**
- Produces:
  - `User.access_until: Mapped[datetime | None]`
  - `def user_subscription_expired(user: User, *, now: datetime | None = None) -> bool`
  - `def get_user_access_until(user: User) -> datetime | None` — aware UTC
  - `def _to_db_datetime` / `_as_utc` — same conventions as `access_until.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_user_subscription.py
from datetime import datetime, timedelta, timezone

from app.models import User, UserRole
from app.services import user_subscription as usub


def test_user_subscription_expired_null_is_unlimited(db):
    user = User(username="u1", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is False


def test_user_subscription_expired_past(db):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    user = User(
        username="u2",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=past.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is True


def test_user_subscription_expired_future(db):
    future = datetime.now(timezone.utc) + timedelta(days=7)
    user = User(
        username="u3",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is False
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_user_subscription.py -v`  
Expected: FAIL (module / attribute missing)

- [ ] **Step 3: Minimal implementation**

Add on `User` in `models.py`:

```python
access_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Add to `database.py` users migration list:

```python
("access_until", "DATETIME"),
```

Create `user_subscription.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from app.models import User


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_db_datetime(dt: datetime | None) -> datetime | None:
    value = _as_utc(dt)
    if value is None:
        return None
    return value.replace(tzinfo=None)


def get_user_access_until(user: User) -> datetime | None:
    return _as_utc(getattr(user, "access_until", None))


def user_subscription_expired(user: User, *, now: datetime | None = None) -> bool:
    deadline = get_user_access_until(user)
    if deadline is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return deadline <= current
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_user_subscription.py -v`  
Expected: PASS

---

### Task 2: Cascade sync / expire / unexpire for owned clients

**Files:**
- Modify: `backend/app/services/user_subscription.py`
- Modify: `backend/tests/test_user_subscription.py`
- Uses: `app.services.access_until.set_access_until`, `VpnConfig`, policy models, existing unblock patterns from `unlock_codes.py`

**Interfaces:**
- Consumes: `set_access_until`, `User`, `VpnConfig`, policy rows
- Produces:
  - `def list_owned_client_targets(db, user_id: int) -> list[tuple[int, str]]`  # (node_id, client_name)
  - `def sync_owned_clients_access_until(db, user: User, *, actor: str, commit: bool = True) -> dict`
  - `def apply_user_subscription_expiry(db, user: User, *, actor: str = "access_expiry_worker", commit: bool = True) -> dict`
  - `def clear_access_expired_for_user(db, user: User, *, actor: str, commit: bool = True) -> dict`
  - `def set_user_access_until(db, user: User, access_until: datetime | None, *, actor: str, sync_clients: bool = True) -> User`

Cascade rules (exact):
1. `sync_owned_clients_access_until` — for every owned `VpnConfig`, set all present protocol policies' deadline to `User.access_until` via `set_access_until(..., commit=False)` then reconcile; **do not** clear permanent/manual blocks.
2. `apply_user_subscription_expiry` — only if `user_subscription_expired`; for each owned client/protocol, if not permanent and not already `access_expired` with another manual reason holding, drive the same path the client worker uses (set deadline claim / reconcile so `block_reason=access_expired`). Skip rows with `is_permanent_blocked` or manual temp block reasons other than `access_expired`.
3. `clear_access_expired_for_user` — clear only `block_reason == "access_expired"` (mirror unlock_codes manual-block skip); set client deadlines to `User.access_until`.

- [ ] **Step 1: Write failing tests**

```python
def test_set_user_access_until_syncs_owned_clients(db, node_factory, make_owned_client):
    # arrange: user owns Alice on node; Alice openvpn policy exists
    # act: set_user_access_until(user, future)
    # assert: openvpn policy access_until == user.access_until


def test_clear_access_expired_skips_permanent_block(db, ...):
    # arrange: client permanent blocked + access_expired sibling protocol
    # act: clear_access_expired_for_user
    # assert: permanent still blocked; access_expired cleared on other


def test_apply_user_subscription_expiry_blocks_owned(db, ...):
    # arrange: user.access_until in the past; owned client not blocked
    # act: apply_user_subscription_expiry
    # assert: policy block_reason == "access_expired"
```

(Reuse fixtures patterns from `tests/test_access_until.py` / `tests/test_unlock_codes.py` for node + policies.)

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/test_user_subscription.py -v`  
Expected: FAIL on missing cascade functions

- [ ] **Step 3: Implement cascade helpers**

Implement the four functions in `user_subscription.py`. For applying expiry, prefer reusing `AccessPolicyService` block APIs already used when deadline is due (same as client path after `set_access_until` + reconcile). Inspect `unlock_codes._is_manual_admin_block` and reuse or import equivalent logic — do not invent a second definition of “manual block”.

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/test_user_subscription.py tests/test_access_until.py -v`  
Expected: PASS (no regressions)

---

### Task 3: Expiry worker pass + create-config gate

**Files:**
- Modify: `backend/app/services/access_expiry_worker.py` (or call from `apply_due_access_blocks` sibling)
- Modify: `backend/app/services/user_subscription.py` — `def apply_due_user_subscription_blocks(db) -> dict[str, int]`
- Modify: `backend/app/services/self_service.py` — `enforce_user_can_create_config`
- Modify: `backend/tests/test_access_expiry_runtime_gate.py` / `test_user_subscription.py` / `test_user_config_access.py`

**Interfaces:**
- Produces: `apply_due_user_subscription_blocks(db) -> {"users_due", "cascaded", "skipped", "errors"}`
- Create gate detail: HTTP 403 with `detail` that includes stable code — prefer FastAPI detail dict `{"code": "subscription_expired", "message": "…"}` **or** plain string containing `subscription_expired` consistently with existing API style in this repo (match whatever `HTTPException` detail shape neighboring endpoints use; if all strings today, use message that starts with identifiable token and document it — prefer structured detail if already used elsewhere).

- [ ] **Step 1: Failing tests**

```python
def test_apply_due_user_subscription_blocks_cascades(db, ...):
    ...


def test_enforce_user_can_create_config_blocks_expired_subscription(db):
    user = User(..., access_until=past, can_create_configs=True, role=UserRole.user)
    with pytest.raises(HTTPException) as exc:
        enforce_user_can_create_config(db, user)
    assert exc.value.status_code == 403
    # assert code/message marks subscription_expired
```

Admins (`UserRole.admin`) remain exempt from the subscription create gate (same as `can_create_configs` today).

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

In `enforce_user_can_create_config`, after admin check:

```python
from app.services.user_subscription import user_subscription_expired

if user_subscription_expired(user):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "subscription_expired", "message": "Срок подписки истёк"},
    )
```

(If repo forbids dict details, use a string and assert substring in tests.)

Wire worker `_run_once` to also call `apply_due_user_subscription_blocks` (still behind `access_expiry` feature flag).

- [ ] **Step 4: Run — PASS**

Run: `python -m pytest tests/test_user_subscription.py tests/test_user_config_access.py tests/test_access_expiry_runtime_gate.py -v`

---

### Task 4: Backfill migration `User.access_until = max(children)`

**Files:**
- Modify: `backend/app/database.py` — `_migrate_user_access_until_backfill()`
- Test: `backend/tests/test_user_subscription.py` (or dedicated migration test)

**Interfaces:**
- Produces: idempotent migration called from existing migrate bootstrap (same place as other `_migrate_*` calls)
- Logic: for each user id that owns vpn_configs, compute max of non-null deadlines across openvpn/awg2 `access_until` and wg `expires_at` for those `client_name`+`node_id` pairs; if user.access_until IS NULL and max exists → set it. Never overwrite non-null user.access_until.

- [ ] **Step 1: Failing test** — insert user + two client policies with different dates; run migrate function; assert user.access_until == max

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement SQL/ORM backfill in `database.py`; register in migrate chain**

- [ ] **Step 4: Run — PASS**; second run does not change already-set users

---

### Task 5: Unlock redeem extends User when owner exists

**Files:**
- Modify: `backend/app/services/unlock_codes.py` (`redeem_unlock_code`)
- Modify: `backend/app/models.py` — `UnlockCodeRedemption.user_id` nullable FK
- Modify: `backend/app/database.py` — add column
- Modify: `backend/tests/test_unlock_codes.py`

**Interfaces:**
- Consumes: `set_user_access_until`, `clear_access_expired_for_user`
- Behavior:
  1. Resolve owner via `VpnConfig.owner_id` for `(node_id, client_name)`.
  2. If owner exists: refuse redeem when **any** owned client has manual admin block on protocols that would be touched? Spec: manual blocks are not cleared — redeem should still extend User and unexpire others; if **the redeeming client** is manually blocked, keep current `_REDEEM_MANUAL_BLOCK_MESSAGE` behavior for that client context.
  3. `User.access_until = max(now, user.access_until or now) + grant_days`
  4. Cascade sync + clear `access_expired` on owned clients
  5. Record redemption with `user_id=owner.id` (and keep `client_name`/`node_id` for audit uniqueness — uniqueness constraint may need revision: one redeem per code per user, not per client). **Decision locked here:** when owner exists, uniqueness is `(code_id, user_id)` (one activation per user per code). When orphan client, keep `(code_id, client_name, node_id)`.

- [ ] **Step 1: Failing tests**

```python
def test_redeem_extends_user_and_all_owned_clients(db, ...):
    # user owns Alice + Bob; redeem on Alice portal context
    # assert user.access_until extended; both clients unexpired / deadlines synced


def test_redeem_does_not_clear_permanent_block_on_sibling(db, ...):
    ...


def test_orphan_client_redeem_stays_client_level(db, ...):
    ...
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement redeem branch + migration for `user_id` + adjust unique constraints carefully (SQLite table rebuild pattern already used in `_migrate_unlock_redemptions_unique_include_node`)

- [ ] **Step 4: Run — PASS**

Run: `python -m pytest tests/test_unlock_codes.py tests/test_user_subscription.py -v`

---

### Task 6: Admin APIs — set user access_until + client conflict guard + sync

**Files:**
- Modify: `backend/app/schemas.py` — `UserUpdate.access_until`, `UserOut.access_until`
- Modify: `backend/app/routers/users.py` — on update, call `set_user_access_until`
- Modify: `backend/app/routers/client_access.py` — `AccessUntilRequest` gains `confirm_override: bool = False`; before set, if owner has `access_until` and new value differs → 409 unless override
- Add endpoint e.g. `POST /api/clients/{client_name}/access-until/sync-from-owner` (or under existing client_access router) calling sync for that client only from owner
- Tests: API tests alongside service tests

**Interfaces:**
- `AccessUntilRequest`: `access_until: datetime | None`, `confirm_override: bool = False`
- 409 body: `{"code": "access_until_conflict", "user_access_until": "...", "client_access_until": "..."}` (ISO)

- [ ] **Step 1: Failing API/service tests for 409 / confirm / sync**

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement router guards + user PATCH wiring**

Helper in `user_subscription.py`:

```python
def client_access_conflicts_with_owner(
    db, *, owner: User | None, client_access_until: datetime | None
) -> bool:
    if owner is None:
        return False
    user_until = get_user_access_until(owner)
    if user_until is None and client_access_until is None:
        return False
    return _as_utc(client_access_until) != user_until
```

- [ ] **Step 4: Run — PASS**

---

### Task 7: User portal tokens + public multi-client payload

**Files:**
- Modify: `backend/app/models.py` — `UserPortalToken`
- Modify: `backend/app/database.py` — create table + partial unique active per user
- Modify: `backend/app/services/client_portal.py` — get_or_create / revoke / `build_user_portal_payload`
- Modify: `backend/app/routers/public_portal.py` — resolve token in either table
- Modify: `backend/app/routers/client_portal.py` — admin manage user link by `user_id`
- Tests: `tests/test_client_portal.py` (+ public portal tests)

**Interfaces:**
- `get_valid_portal_token` becomes a union resolver returning a small dataclass/`Literal` kind: `client` | `user`
- User portal payload: list of clients owned by user (same per-client profile entries as today, nested under clients array)
- Expired user subscription → payload marks blocked/expired; redeem endpoint still works

- [ ] **Step 1: Failing tests** — create user token; public meta returns multiple clients; revoke → 404; expired user → expired flag

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement model, migration, service, routers**

Public path stays `/p/{token}` — token namespace must not collide (generate with same entropy; check both tables on create).

- [ ] **Step 4: Run — PASS**

Run: `python -m pytest tests/test_client_portal.py tests/test_portal_access_path.py -v`

---

### Task 8: Telegram access-expiry reminders (keep cert)

**Files:**
- Modify: `backend/app/models.py` — `DEFAULT_TG_NOTIFY_EVENTS` keys:
  - `access_expiry_reminder` (owner default True or False — mirror cert owner default)
  - `user_access_expiry_reminder` (admin; default False like other `user_*`)
- Modify: `backend/app/config.py` — `self_service_reminder_access_days_threshold: int = 7`
- Modify: `backend/app/services/user_reminder_service.py` — `REMINDER_ACCESS = "access_expiry"`
- Modify: `backend/app/services/admin_notify.py` — labels + card formatting
- Tests: extend reminder tests

**Interfaces:**
- Dedup key: `f"user:{user.id}:access:{access_until.date().isoformat()}"`
- Threshold: `self_service_reminder_access_days_threshold`
- Do not remove or change cert reminder behavior

- [ ] **Step 1: Failing tests** — user within threshold receives access reminder; cert path still independent

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement event maps + scan in reminder loop over Users with non-null access_until**

- [ ] **Step 4: Run — PASS**

---

### Task 9: Frontend — user access_until, conflict UX, user portal link

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/settings/UsersTab.tsx` — datetime field for `access_until`
- Modify: existing client access-until UI (search `access_until` / `AccessUntil` in `frontend/src`) — confirm dialog on 409; “Синхронизировать с юзером” button when owner present
- Modify: `frontend/src/pages/SubscriptionPage.tsx` and/or dashboard portal controls — create/copy/revoke **user** portal link
- Modify: public portal page if it assumes single client — render client list for user tokens

**Interfaces:**
- PATCH user includes `access_until: string | null`
- Access until POST body may include `confirm_override: true`
- Portal API: mirror client portal admin endpoints for `userId`

- [ ] **Step 1: Typecheck / component tests if present; otherwise manual checklist in Step 4**

- [ ] **Step 2: Implement UI wiring against Task 6–7 APIs**

- [ ] **Step 3: `cd frontend && npm test` (or project’s vitest script) for touched units**

- [ ] **Step 4: Manual smoke checklist**
  - Set user access_until → owned clients update
  - Expire → create config blocked for that user
  - Unlock once → all owned unlock
  - Client date edit → warning → confirm
  - User portal shows all clients
  - TG toggles show new events (if settings UI lists them dynamically from API)

---

### Task 10: Docs + CHANGELOG

**Files:**
- Modify: `docs/podpiska.md` — user-level period, cascade, unlock, dual portal, TG
- Modify: `CHANGELOG.md` under `[Unreleased]` Added/Changed
- Optionally update `docs/README.md` one-liner if subscription blurb is stale

- [ ] **Step 1: Draft Russian docs matching shipped behavior (no aspirational features)**

- [ ] **Step 2: CHANGELOG bullets covering: user access_until, cascade, unlock, portal, conflict guard, TG access reminder**

- [ ] **Step 3: Quick proofread against spec goals 1–7**

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| User-level `access_until` | 1 |
| Cascade expire / unexpire | 2–3 |
| Forbid create when expired | 3 |
| Migration max(children) | 4 |
| Unlock at user level | 5 |
| Admin conflict + sync | 6, 9 |
| User + client portal | 7, 9 |
| TG access + keep cert | 8 |
| Manual blocks preserved | 2, 5 |
| Orphan client legacy | 5 |
| Docs / CHANGELOG | 10 |

## Self-review notes

- No TBD placeholders left in task behaviors; redeem uniqueness decision locked in Task 5.
- Types: `access_until` datetime nullable consistently; conflict code `access_until_conflict`; create gate `subscription_expired`.
- Worker remains gated by existing `access_expiry` feature flag.
