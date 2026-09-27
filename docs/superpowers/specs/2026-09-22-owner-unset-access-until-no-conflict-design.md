# Design: free client access_until when owner has none

Date: 2026-09-22  
Branch: `release/2.26.0`  
Status: approved for planning

## Problem

Saving a client/profile access deadline when the owning user has no `access_until` currently counts as a conflict (`409 access_until_conflict`). That blocked legitimate per-config deadlines (e.g. TopTinker under Novikov) and, before a defensive fix, could 500 when building the conflict payload (`None.isoformat()`).

## Goal

If the owner has **no** subscription deadline, admins may set, change, or clear any client access deadline **without** conflict confirmation.

If the owner **has** a deadline, keep today’s behavior: any divergence still returns `409` and the dashboard override / sync-from-owner flow (choice **A**).

## Non-goals

- No new user setting or “free deadlines” flag.
- No frontend redesign of the conflict dialog.
- No change to cascade when an owner deadline is later set (`set_user_access_until` / sync-from-owner).
- No relaxation of conflict when the owner deadline is set (including shorter client deadlines).

## Rule

Single source of truth: `client_access_conflicts_with_owner` in `backend/app/services/user_subscription.py`.

| Owner `access_until` | Client requested deadline | Conflict? |
|---|---|---|
| `None` | any (`None` or a date) | **No** |
| set | equal (normalized UTC) | No |
| set | different or `None` | **Yes** → 409 |

Call sites already go through `_maybe_access_until_conflict` (OpenVPN / WireGuard / AmneziaWG2 `PATCH …/access-until`, WireGuard `set-expiry`). No router API shape change.

## Implementation sketch

1. Change conflict helper:

```python
def client_access_conflicts_with_owner(...):
    if owner is None:
        return False
    user_until = get_user_access_until(owner)
    if user_until is None:
        return False
    return _as_utc(client_access_until) != user_until
```

2. Keep safe 409 payload construction (`user_until.isoformat() if user_until else None`) so a future conflict path cannot 500 on `None`.

3. Tests (TDD):
   - Unit: owner without deadline + client date → `False`.
   - Endpoint: PATCH client date when owner has no deadline → **200** (not 409); rewrite any test that expected 409 in that case.
   - Existing tests with owner deadline set remain green.

4. Docs: clarify `docs/podpiska.md`; add CHANGELOG `[Unreleased]` note.

## Frontend

No required UI change. Conflict dialog still appears only when the owner has a deadline and the client diverges. Toast improvements that surface `Error.message` are optional polish, out of core scope unless already present on the branch.

## Success criteria

- Admin can save `31.12.2026` on TopTinker while Novikov has no user `access_until` → success, no override dialog.
- Same save when Novikov has a different user deadline → 409 + confirm override as today.
- Unit + access_until endpoint tests cover both cases.
