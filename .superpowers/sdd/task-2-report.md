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
