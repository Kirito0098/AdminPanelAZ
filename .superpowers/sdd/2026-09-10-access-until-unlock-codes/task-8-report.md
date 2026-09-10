## Task 8 Report

### Done
- Updated `CHANGELOG.md` with an Unreleased note covering `access_until`, unlock codes, portal redeem, and TG/Mini generation.
- Strengthened `backend/tests/test_client_portal.py` so portal status tests assert the exact `access_until` value and keep certificate expiry secondary.

### Hardening
- Confirmed public portal redeem already uses `public_download_rate_limit_service`, so the public download limiter remains the guard for this surface.

### Verification
- `PYTHONPATH=backend /opt/AdminPanelAZ/.venv/bin/pytest backend/tests/test_client_portal.py backend/tests/test_unlock_codes.py -q`
- `npm run build:all` in `frontend/` succeeded

