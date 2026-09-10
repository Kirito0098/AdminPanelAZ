Fixed the Task 3 review findings.

Changes:
- Validated custom unlock codes before insert, including length and character set, so bad caller-supplied codes now fail with a clean `ValueError` / 400 response.
- Added a feature-toggle guard to `redeem_unlock_code()`.
- Made redeem atomic by deferring commits until all protocol updates and the redemption row are ready, then reconciling after the transaction commits.
- Removed the unused `Node` import cleanup was already covered by the refactor path.

Verification:
- `PYTHONPATH=. /opt/AdminPanelAZ/.venv/bin/pytest tests/test_unlock_codes.py tests/test_access_until.py -q`
- `app.main` imports successfully.
