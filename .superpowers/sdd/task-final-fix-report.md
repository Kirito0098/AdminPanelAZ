# Task final fix report — OpenVPN Connect URL import

## Changes

### `backend/tests/test_openvpn_connect_url.py`
- Added public endpoint tests via `_public_app`:
  - `test_ovpn_get_unknown_token_404` — unknown token → 404
  - `test_ovpn_get_expired_token_410` — expired `expires_at` → 410, no redeem
  - `test_ovpn_get_exhausted_token_410` — `download_count >= max_downloads` → 410
  - `test_ovpn_get_records_remote_addr_in_audit` — GET audit log has `remote_addr=testclient`
- Extended `test_ovpn_get_redeems_without_pin` to assert `Content-Type` starts with `application/x-openvpn-profile`
- Kept existing `test_ovpn_head_does_not_redeem` unchanged

### `backend/app/routers/public_download.py`
- `openvpn_connect_get` now accepts `Request` and passes `remote_addr=request.client.host if request.client else None` into `_deliver_openvpn_connect`
- `_deliver_openvpn_connect` accepts optional `remote_addr` and forwards it to `redeem_token` on GET redeem only (HEAD unchanged)

## Tests

Command:
```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. pytest tests/test_openvpn_connect_url.py tests/test_file_download.py -q --tb=short
```

Full output:
```
...........................                                              [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /opt/AdminPanelAZ/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_openvpn_connect_url.py: 35 warnings
  /opt/AdminPanelAZ/backend/.venv/lib/python3.12/site-packages/sqlalchemy/sql/schema.py:3623: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    return util.wrap_callable(lambda ctx: fn(), fn)  # type: ignore

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
27 passed, 36 warnings in 1.93s
```

## Commit

SHA: `7613c78`

---

# Task final fix report — resource metrics workers

## Changes

### `backend/app/services/worker_lifecycle.py`
- Changed `should_start_resource_metrics()` and `should_start_panel_resource_metrics()` to always return `True`.
- Kept the runtime gating in the worker loops so the settings can flip without restart.

### `backend/app/services/resource_metrics_worker.py`
- Removed the startup-only early return.
- Added a per-tick `settings.resource_metrics_enabled` check before collecting samples.

### `backend/app/services/panel_resource_metrics_worker.py`
- Removed the startup-only early return.
- Added a per-tick `settings.panel_resource_metrics_enabled` check before collecting samples.

### `backend/tests/test_resource_metrics_runtime_gate.py`
- Updated the loop test to start disabled, flip the setting on the next tick, and confirm collection resumes.
- Added a startup-plan assertion for `should_start_resource_metrics()`.

### `backend/tests/test_panel_resource_metrics_runtime_gate.py`
- Updated the loop test to start disabled, flip the setting on the next tick, and confirm collection resumes.
- Added a startup-plan assertion for `should_start_panel_resource_metrics()`.

## Tests

Command:
```bash
backend/.venv/bin/pytest backend/tests/test_node_health_runtime_gate.py backend/tests/test_cert_sync_runtime_gate.py backend/tests/test_resource_metrics_runtime_gate.py backend/tests/test_panel_resource_metrics_runtime_gate.py
```

Output:
```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /opt/AdminPanelAZ
plugins: anyio-4.14.2
collected 13 items

backend/tests/test_node_health_runtime_gate.py ...                       [ 23%]
backend/tests/test_cert_sync_runtime_gate.py ....                        [ 53%]
backend/tests/test_resource_metrics_runtime_gate.py ...                  [ 76%]
backend/tests/test_panel_resource_metrics_runtime_gate.py ...            [100%]

============================== 13 passed in 0.82s ===============================
```
