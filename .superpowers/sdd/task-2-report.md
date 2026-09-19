# Task 2 Report: Cascade sync / expire / unexpire for owned clients

## Status
Complete. Implemented with TDD on `feat/user-level-subscription`.

## Changes
- Extended `backend/app/services/user_subscription.py` with:
  - `list_owned_client_targets`
  - `sync_owned_clients_access_until`
  - `apply_user_subscription_expiry`
  - `clear_access_expired_for_user`
  - `set_user_access_until`
- Reused `app.services.access_until` helpers for deadline writes and reconcile.
- Reused `unlock_codes._is_manual_admin_block` so manual/permanent skips match existing behavior.
- Scoped owned-client traversal to primary `VpnConfig` rows only (`ha_primary_config_id IS NULL`).

## Tests
- Added focused coverage in `backend/tests/test_user_subscription.py` for:
  - syncing a user deadline to owned client policies
  - clearing `access_expired` while skipping permanent/manual rows
  - expiring owned clients across OpenVPN, WireGuard, and AmneziaWG2
- Verified with:
  - `backend/.venv/bin/python -m pytest backend/tests/test_user_subscription.py -v`
  - `backend/.venv/bin/python -m pytest backend/tests/test_user_subscription.py backend/tests/test_access_until.py backend/tests/test_unlock_codes.py -v`

## Self-review
- No blocking issues found in review.
- Manual/permanent blocks stay intact in both sync and clear paths.
- Expiry and unexpiry now flow through the same deadline + reconcile logic already used for client policy handling.

## Concerns
- `clear_access_expired_for_user` intentionally skips manual/permanent rows entirely, prioritizing "never clear manual blocks" over forcing deadline sync on those rows.

## Task 2 Review Fix
- Updated `apply_user_subscription_expiry` to seed only missing policy rows, release the initial read snapshot, and then use `set_access_until(..., require_deadline_lte=user.access_until)` so concurrent unlock/extend wins instead of being clobbered.
- Added a regression test in `backend/tests/test_user_subscription.py` that mirrors the client-worker race and proves a concurrent extension is skipped rather than overwritten.

### Test Command
- `backend/.venv/bin/python -m pytest backend/tests/test_user_subscription.py backend/tests/test_access_until.py -v`

### Test Output
```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- /opt/AdminPanelAZ/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /opt/AdminPanelAZ
plugins: anyio-4.14.2
collecting ... collected 15 items

backend/tests/test_user_subscription.py::test_user_subscription_expired_null_is_unlimited PASSED [  6%]
backend/tests/test_user_subscription.py::test_user_subscription_expired_past PASSED [ 13%]
backend/tests/test_user_subscription.py::test_user_subscription_expired_future PASSED [ 20%]
backend/tests/test_user_subscription.py::test_set_user_access_until_syncs_owned_clients PASSED [ 26%]
backend/tests/test_user_subscription.py::test_clear_access_expired_skips_permanent_block PASSED [ 33%]
backend/tests/test_user_subscription.py::test_apply_user_subscription_expiry_blocks_owned PASSED [ 40%]
backend/tests/test_user_subscription.py::test_apply_user_subscription_expiry_does_not_clobber_concurrent_extension PASSED [ 46%]
backend/tests/test_access_until.py::test_set_access_until_openvpn_and_effective_min PASSED [ 53%]
backend/tests/test_access_until.py::test_apply_due_access_blocks_sets_access_expired PASSED [ 60%]
backend/tests/test_access_until.py::test_wg_access_until_aliases_expires_at PASSED [ 66%]
backend/tests/test_access_until.py::test_openvpn_access_until_route_wires_replication PASSED [ 73%]
backend/tests/test_access_until.py::test_wg_access_renew_preserves_manual_permanent_block PASSED [ 80%]
backend/tests/test_access_until.py::test_manual_unblock_while_access_expired_defers_reblock_to_worker PASSED [ 86%]
backend/tests/test_access_until.py::test_set_access_until_require_deadline_skips_when_extended PASSED [ 93%]
backend/tests/test_access_until.py::test_apply_due_access_blocks_does_not_clobber_concurrent_extension PASSED [100%]

=============================== warnings summary ===============================
backend/tests/test_user_subscription.py: 59 warnings
backend/tests/test_access_until.py: 59 warnings
  /opt/AdminPanelAZ/backend/.venv/lib/python3.12/site-packages/sqlalchemy/sql/schema.py:3623: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    return util.wrap_callable(lambda ctx: fn(), fn)  # type: ignore

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 15 passed, 118 warnings in 3.00s =======================
```
