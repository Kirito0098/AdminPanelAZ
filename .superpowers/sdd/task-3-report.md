Status: completed
Branch: `feat/user-level-subscription`
Implementation: added `apply_due_user_subscription_blocks(db)` in `backend/app/services/user_subscription.py`; wired the subscription pass into `backend/app/services/access_expiry_worker.py` behind the existing `access_expiry` runtime gate; updated `backend/app/services/self_service.py` so non-admin users with expired subscriptions get HTTP 403 with `detail` containing `subscription_expired`.
Tests: `backend/.venv/bin/python -m pytest backend/tests/test_user_subscription.py backend/tests/test_user_config_access.py backend/tests/test_access_expiry_runtime_gate.py -v`
Test Result: passed (`22 passed`)
Concerns: `skipped` in the new worker pass aggregates both manual-admin blocks and atomic-claim misses/already-not-expired rows; if downstream reporting needs those separated later, the return shape will need to expand.
Commits: `e2d4f03` - `Add subscription expiry worker pass`
Report Path: `/opt/AdminPanelAZ/.superpowers/sdd/task-3-report.md`
# Task 3 Report: Settings origin_lock + dual-file refresh

**Status:** DONE (landed as fe484a6)

## Commit
- `fe484a6` — Add cloudflare origin lock settings

## Files
- backend/app/config.py — cloudflare_origin_lock default False
- backend/app/services/cloudflare_proxy_settings.py — origin_lock flag, snippet path/validity, dual-file refresh
- backend/tests/test_cloudflare_proxy_pipeline.py — persist/clear/refresh tests

## Tests
Controller will verify; implementer commit includes pipeline tests for origin_lock persist, clear on proxy off, dual-file refresh.
