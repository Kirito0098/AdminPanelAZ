# Access until + Unlock codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Серверный срок доступа (без порчи длинного сертификата), авто-блок по дате, универсальные unlock-коды с вводом на портале и генерацией из панели / TG / mini app.

**Architecture:** Расширяем access policy (`access_until` / WG `expires_at`), воркер `access_expired` блокировок, сервис `unlock_codes` + admin/public API; портал redeem; UI в ClientActions / TG bot / tg-mini.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite migrations in `database.py`, React (panel + PortalPage + tg-mini), pytest, existing Telegram bot handlers.

**Spec:** `docs/superpowers/specs/2026-09-10-access-until-unlock-codes-design.md`

## Global Constraints

- User-facing copy in Russian
- Do not commit unless the user explicitly asks
- Unlock codes are universal; one redemption per `(code_id, client_name)`
- Redeem grant: `access_until = max(now, current_access_until) + grant_days` + unblock for protocols on the code
- Do not use temp `block_until` auto-unblock for access expiry
- WG: treat existing `WgAccessPolicy.expires_at` as access-until (API field name `access_until` aliases it); OpenVPN + AWG2 policy get new `access_until` column
- AWG2 `VpnConfig.expires_at` (hard TTL delete via `awg2_expire_worker`) stays separate from soft access block
- Feature toggle `unlock_codes` (default true)
- Public redeem only on portal Host + valid portal token
- CHANGELOG `[Unreleased]` → Added (Russian)

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/models.py` | `access_until` on OVPN/AWG2 policies; `UnlockCode`, `UnlockCodeRedemption` |
| `backend/app/database.py` | SQLite migrate columns + new tables |
| `backend/app/services/access_until.py` | get/set effective access_until; apply access_expired block |
| `backend/app/services/access_expiry_worker.py` | poll policies → block |
| `backend/app/services/unlock_codes.py` | create/list/revoke/redeem |
| `backend/app/routers/unlock_codes.py` | admin CRUD |
| `backend/app/routers/client_access.py` | PATCH access-until endpoints |
| `backend/app/routers/public_portal.py` | POST redeem |
| `backend/app/services/client_portal.py` | status prefers access_until; expose redeem helper |
| `backend/app/services/feature_toggles.py` | `unlock_codes` |
| `backend/app/services/lifespan_workers.py` | start access_expiry worker |
| `backend/app/services/telegram_bot_handlers/unlock_codes.py` | bot create-code flow |
| `frontend/src/api/unlockCodes.ts` | panel API client |
| `frontend/src/api/portal.ts` | redeemPublicPortalCode |
| `frontend/src/pages/PortalPage.tsx` | access label + redeem form |
| `frontend/src/components/dashboard/ClientActionsDialog.tsx` | set access + create key shortcuts |
| `frontend/src/components/.../UnlockCodesPanel.tsx` | list/create/revoke (settings or dialog) |
| `frontend/src/tg-mini/...` | generate unlock code screen/API |
| `backend/tests/test_access_until.py` | worker + set/get |
| `backend/tests/test_unlock_codes.py` | redeem rules |
| `CHANGELOG.md` | Unreleased |

---

### Task 1: Models + migration + feature toggle

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/services/feature_toggles.py`
- Test: `backend/tests/test_unlock_codes.py` (model import / table ensure smoke)

**Interfaces:**
- Produces: `UnlockCode`, `UnlockCodeRedemption`; `OpenVpnAccessPolicy.access_until`; `AmneziaWg2AccessPolicy.access_until`; feature key `unlock_codes`

- [ ] **Step 1: Write failing test that UnlockCode model is importable and table migrates**

```python
def test_unlock_code_tables_exist(tmp_path, monkeypatch):
    # boot migrate against temp sqlite — follow patterns in test_awg2_access.py / database ensure
    from app.models import UnlockCode, UnlockCodeRedemption
    assert UnlockCode.__tablename__ == "unlock_codes"
```

- [ ] **Step 2: Add models**

`UnlockCode`: `code` (unique, 8–32 chars), `grant_days`, `protocols` (JSON text list), `mode` (`single`|`multi`), `max_redemptions`, `code_expires_at`, `created_by_user_id`, `created_at`, `revoked_at`.

`UnlockCodeRedemption`: `code_id`, `client_name`, `node_id`, `redeemed_at`; UniqueConstraint(`code_id`, `client_name`).

Add nullable `access_until` DateTime to `OpenVpnAccessPolicy` and `AmneziaWg2AccessPolicy` only (WG keeps `expires_at`).

- [ ] **Step 3: Migration in `database.py`**

Follow `_migrate_awg2_access_policy_table` style: `ALTER TABLE ... ADD COLUMN access_until DATETIME`; `CREATE TABLE unlock_codes` / `unlock_code_redemptions` if missing. Wire into existing migrate runner.

- [ ] **Step 4: Feature toggle `unlock_codes`**

`FEATURE_UNLOCK_CODES_ENABLED`, group `app_module`, default `True`, label «Unlock-коды доступа».

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=. /opt/AdminPanelAZ/.venv/bin/pytest backend/tests/test_unlock_codes.py -q`  
Expected: PASS for smoke; expand in later tasks.

- [ ] **Step 6: Commit only if user asked**

---

### Task 2: access_until service + expiry worker

**Files:**
- Create: `backend/app/services/access_until.py`
- Create: `backend/app/services/access_expiry_worker.py`
- Modify: `backend/app/services/access_policy.py` (OVPN/AWG2 state include access_until; expired → block_mode access path)
- Modify: `backend/app/services/lifespan_workers.py`
- Modify: `backend/app/routers/client_access.py`
- Test: `backend/tests/test_access_until.py`

**Interfaces:**
- Produces:
  - `get_access_until(db, protocol, node_id, client_name) -> datetime | None`
  - `set_access_until(db, protocol, node_id, client_name, access_until: datetime | None, *, actor: str) -> dict`
  - `effective_access_until_for_client(db, node_id, client_name) -> datetime | None` (min across protocols)
  - `apply_due_access_blocks(db) -> dict[str, int]` counts
  - `run_access_expiry_loop()` async
- Consumes: existing `openvpn_permanent_block` / WG expired sync / AWG2 block helpers

**WG alias rule:** for protocol `wireguard`, read/write `WgAccessPolicy.expires_at` as access_until.

- [ ] **Step 1: Failing tests**

```python
def test_set_access_until_openvpn_and_effective_min():
    ...

def test_apply_due_access_blocks_sets_access_expired():
    # policy access_until in the past → is_permanent_blocked + block_reason access_expired
    ...

def test_wg_access_until_aliases_expires_at():
    ...
```

- [ ] **Step 2: Implement `access_until.py`**

- [ ] **Step 3: Implement worker** (~60s interval like `awg2_expire_worker`), call node block APIs via existing access_policy methods so HA stays consistent.

- [ ] **Step 4: PATCH routes**

`PATCH /api/client-access/openvpn/{client}/access-until`  
`PATCH /api/client-access/wireguard/{client}/access-until`  
`PATCH /api/client-access/amneziawg2/{client}/access-until`  
Body: `{ "access_until": "2026-10-01T00:00:00Z" | null }`

- [ ] **Step 5: Register worker in lifespan**

- [ ] **Step 6: pytest `test_access_until.py` PASS**

---

### Task 3: Unlock codes service + admin API

**Files:**
- Create: `backend/app/services/unlock_codes.py`
- Create: `backend/app/routers/unlock_codes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_unlock_codes.py`

**Interfaces:**
- Produces:
  - `generate_code_value() -> str` (e.g. `XXXX-XXXX-XXXX`, url-safe)
  - `create_unlock_code(db, *, grant_days, protocols, mode, max_redemptions, code_expires_at, creator, code=None) -> UnlockCode`
  - `revoke_unlock_code(db, code_id) -> None`
  - `list_unlock_codes(db, *, include_revoked=False) -> list`
  - `redeem_unlock_code(db, *, code: str, client_name: str, node_id: int) -> dict`  
    Returns `{ grant_days, protocols_applied, access_until_by_protocol }`

**Redeem rules (must match tests):**
1. Feature on; code exists; `revoked_at is None`; `code_expires_at` null or > now  
2. `redemption_count < max_redemptions`  
3. No existing redemption for `(code_id, client_name)`  
4. `protocols_applied = intersection(code.protocols, client_configs)` non-empty  
5. For each applied protocol: unblock + set_access_until(max(now, current)+days)  
6. Insert redemption row  

- [ ] **Step 1: Write failing redeem tests** (single, multi second client OK, same client twice FAIL, revoked FAIL, no protocol overlap FAIL)

- [ ] **Step 2: Implement service**

- [ ] **Step 3: Admin router**

`GET /api/unlock-codes`  
`POST /api/unlock-codes` `{ grant_days, protocols, mode, max_redemptions?, code_expires_at?, code? }`  
`POST /api/unlock-codes/{id}/revoke`  
Guard: `unlock_codes` feature + auth role that can manage client-access.

- [ ] **Step 4: pytest PASS**

---

### Task 4: Public portal redeem + status prefers access_until

**Files:**
- Modify: `backend/app/routers/public_portal.py`
- Modify: `backend/app/services/client_portal.py` (`build_portal_status`)
- Modify: `frontend/src/api/portal.ts`
- Modify: `frontend/src/pages/PortalPage.tsx`
- Test: `backend/tests/test_client_portal.py`, `backend/tests/test_unlock_codes.py`

**Interfaces:**
- Produces: `POST /api/public/portal/{token}/redeem` `{ code }`  
- Status: prefer policy `access_until` (and WG `expires_at`) over cert for primary «Истекает»; if access expired → status blocked/expired even if cert valid

- [ ] **Step 1: Backend redeem endpoint** — Host check + rate limit + feature + `get_valid_portal_token` → `redeem_unlock_code`

- [ ] **Step 2: Update `build_portal_status`**

Priority for expiry candidates: policy access_until / WG expires_at first; cert_expires_at secondary for label only if no access_until set (spec: portal must not show Бессрочно when access_until set).

- [ ] **Step 3: Portal UI** — input + button «Активировать ключ»; toast success with new date; show errors from `detail`

- [ ] **Step 4: Tests PASS; `npm run build` for frontend**

---

### Task 5: Panel UI — set access + manage codes

**Files:**
- Create: `frontend/src/api/unlockCodes.ts`
- Create: `frontend/src/components/dashboard/UnlockCodeCreateDialog.tsx` (or settings subsection)
- Modify: `frontend/src/components/dashboard/ClientActionsDialog.tsx`
- Modify: types for policy `access_until`
- Optional: Settings nav entry if list UI is large — prefer dialog from client actions + small «Коды» list under Config Delivery / Security

- [ ] **Step 1: API client** create/list/revoke + patch access-until

- [ ] **Step 2: ClientActionsDialog** — «Доступ до…» date picker/null; «Создать unlock-ключ» opens create dialog with protocol checkboxes prefilled from client’s protocols

- [ ] **Step 3: Create dialog fields** — grant_days, protocols[], mode single/multi, max_redemptions (if multi), optional code_expires_at, show generated code + copy

- [ ] **Step 4: Manual smoke on panel; typecheck**

---

### Task 6: Telegram bot generate code

**Files:**
- Create: `backend/app/services/telegram_bot_handlers/unlock_codes.py`
- Modify: bot router/registry to register command or admin menu button
- Test: handler unit test with mocked db (optional thin)

- [ ] **Step 1: Admin-only flow** — ask grant_days → protocols (multiselect text) → single/multi → create via `create_unlock_code` → reply with code monospace

- [ ] **Step 2: Pirates presets optional** — buttons `30д OVPN`, `30д все`

- [ ] **Step 3: Manual / unit coverage for permission denied non-admin**

---

### Task 7: Mini app generate code

**Files:**
- Modify: `frontend/src/tg-mini/api` (+ backend tg panel routes if mini uses dedicated prefix — mirror panel `/api/unlock-codes` with existing tg auth)
- Create: `frontend/src/tg-mini/pages/UnlockCodes.tsx`
- Modify: `frontend/src/tg-mini/App.tsx`, nav

- [ ] **Step 1: Reuse admin API** if tg-mini already calls panel JWT APIs; else add thin wrappers like other tg client-access calls

- [ ] **Step 2: Page** — form create + list recent codes + revoke (admin only)

- [ ] **Step 3: Build tg-mini** `npm run build:tg-mini`

---

### Task 8: CHANGELOG + hardening

**Files:**
- Modify: `CHANGELOG.md`
- Modify: portal status tests for access_until priority
- Rate limit: ensure redeem uses `public_download_rate_limit_service` or dedicated bucket

- [ ] **Step 1: CHANGELOG Unreleased Added** — access_until + unlock codes + portal redeem + TG/mini generation

- [ ] **Step 2: Full pytest for new tests + portal regression**

- [ ] **Step 3: `frontend` build:all; restart service for manual QA checklist**

**QA checklist:**
1. Set access_until yesterday on OVPN → worker blocks; cert still valid; portal shows expired/blocked  
2. Create multi code OVPN+AWG2 → client A redeems OK; client A again FAIL; client B OK  
3. Single code second redeem FAIL  
4. TG + mini create code works for admin  
5. Feature off → redeem 403 / UI hidden  

---

## Spec coverage self-check

| Spec item | Task |
|-----------|------|
| access_until OVPN/AWG2; WG alias expires_at | 1–2 |
| Worker access_expired block | 2 |
| Unlock tables + create/list/revoke | 1, 3 |
| Redeem D-formula + unique client | 3–4 |
| Portal UI redeem + status | 4 |
| Panel UI | 5 |
| TG bot | 6 |
| Mini app | 7 |
| Feature toggle + CHANGELOG + tests | 1, 8 |
| Out of scope billing/cert renew | — omitted |

## Placeholder / consistency notes

- API JSON always exposes `access_until` even when stored as WG `expires_at`.
- Do not delete AWG2 clients on soft access expiry (that remains `VpnConfig.expires_at` + awg2_expire_worker).
