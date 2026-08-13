# Server OS Reboot (Panel + Telegram) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins schedule a 15s-delayed OS reboot of any VPN `Node` from MaintenanceTab and Telegram `/settings` → Обслуживание, with double confirm + phrase `REBOOT` and cancel.

**Architecture:** In-memory pending-reboot service (`threading.Timer`) with `schedule` / `cancel` / `list_pending` / execute callback via `get_adapter_for_node(node).reboot()`. Shared FastAPI endpoints under `/settings/reboot*`; UI and Telegram both call those handlers. Local reboot uses `systemctl reboot --no-wall`; remote uses node-agent `POST /reboot`.

**Tech Stack:** FastAPI, NodeAdapter (local/remote), node_agent, React MaintenanceTab + ConfirmDialog, Telegram settings_fsm, pytest with mocks.

**Spec:** `docs/superpowers/specs/2026-08-13-server-reboot-design.md`

## Global Constraints

- Spec requirements are authoritative
- Confirm phrase is exactly `REBOOT` (case-sensitive)
- Delay is fixed **15** seconds
- Admin-only (`require_admin` / `_require_admin_ctx`)
- One pending reboot per `node_id` at a time
- After panel process restart, pending must **not** auto-execute
- Copy: «перезагрузка ОС сервера» — never confuse with panel service restart or VPN unit restart
- **NEVER** run tests or agent commands that invoke real `systemctl reboot` / `reboot` on the host — always mock subprocess / adapter / agent
- Do not invent commits unless the user explicitly asks; skip commit steps during execution unless told to commit
- User-facing docs in Russian; update CHANGELOG `[Unreleased]`

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/server_reboot.py` | Pending state, Timer, schedule/cancel/list/execute |
| `backend/tests/test_server_reboot.py` | Unit tests with fake clock/callback (no real reboot) |
| `backend/app/services/antizapret.py` | `reboot()` via mocked-friendly `systemctl reboot --no-wall` |
| `backend/app/services/node_adapter.py` | Abstract + Local + Remote `reboot()` |
| `backend/node_agent/main.py` | `POST /reboot` |
| `backend/tests/test_node_adapter_reboot.py` | Mock subprocess / `_request` |
| `backend/app/schemas.py` | Request/response models |
| `backend/app/routers/maintenance.py` | Schedule / cancel / pending endpoints |
| `backend/app/services/admin_notify.py` | Notify keys/titles for reboot events |
| `backend/tests/test_settings_reboot_api.py` | API tests with mocked service/adapter |
| `backend/app/services/telegram_bot_handlers/settings_fsm.py` | Field `mnt_reboot` |
| `backend/app/services/telegram_bot_handlers/settings_maintenance.py` | Reboot UX flow |
| `backend/app/services/telegram_bot_handlers/settings.py` | Route `mnt_reboot` text to maintenance handler |
| `backend/tests/test_telegram_reboot.py` | FSM + callback flow with mocks |
| `frontend/src/components/shared/ConfirmDialog.tsx` | Optional `confirmPhrase` |
| `frontend/src/hooks/useConfirmDialog.ts` | Pass-through (if needed) |
| `frontend/src/api/client.ts` | `scheduleServerReboot`, `cancelServerReboot`, `getPendingServerReboots` |
| `frontend/src/types.ts` | Types for reboot payloads |
| `frontend/src/components/settings/MaintenanceTab.tsx` | OS reboot card + countdown |
| `frontend/src/lib/actionLogLabels.ts` | RU labels |
| `frontend/src/components/telegram/TelegramBotCommandsGuide.tsx` | Mention reboot in maintenance |
| `docs/Telegram.md` | Short note |
| `CHANGELOG.md` | Unreleased entry |

---

### Task 1: Pending reboot service + unit tests

**Files:**
- Create: `backend/app/services/server_reboot.py`
- Create: `backend/tests/test_server_reboot.py`

**Interfaces:**
- Produces:
  - `DELAY_SECONDS: int = 15`
  - `CONFIRM_PHRASE: str = "REBOOT"`
  - `@dataclass PendingReboot`: `reboot_id: str`, `node_id: int`, `node_name: str`, `scheduled_by: str`, `created_at: datetime`, `execute_at: datetime`, `status: str`
  - `schedule_reboot(*, node_id: int, node_name: str, scheduled_by: str, execute_fn: Callable[[PendingReboot], None] | None = None, delay_seconds: float | None = None) -> PendingReboot`
  - `cancel_reboot(reboot_id: str) -> PendingReboot`
  - `list_pending() -> list[PendingReboot]`
  - `get_pending(reboot_id: str) -> PendingReboot | None`
  - `clear_all_for_tests() -> None` (tests only)
  - `RebootError` with `.code` in `{"invalid_confirm", "duplicate_pending", "not_found", "not_cancellable"}`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_server_reboot.py
import time
from unittest.mock import Mock

import pytest

from app.services import server_reboot as sr


@pytest.fixture(autouse=True)
def _clean():
    sr.clear_all_for_tests()
    yield
    sr.clear_all_for_tests()


def test_schedule_requires_exact_confirm_via_wrapper():
    # schedule_reboot itself does not take confirm — API will validate.
    # Here: schedule creates pending and calls execute_fn after delay.
    executed = Mock()
    pending = sr.schedule_reboot(
        node_id=1,
        node_name="local",
        scheduled_by="admin",
        execute_fn=executed,
        delay_seconds=0.05,
    )
    assert pending.status == "pending"
    assert pending.node_id == 1
    time.sleep(0.12)
    executed.assert_called_once()
    assert executed.call_args[0][0].reboot_id == pending.reboot_id
    assert sr.get_pending(pending.reboot_id).status == "executed"


def test_cancel_before_execute():
    executed = Mock()
    pending = sr.schedule_reboot(
        node_id=2,
        node_name="n2",
        scheduled_by="admin",
        execute_fn=executed,
        delay_seconds=1.0,
    )
    cancelled = sr.cancel_reboot(pending.reboot_id)
    assert cancelled.status == "cancelled"
    time.sleep(0.15)
    executed.assert_not_called()


def test_duplicate_pending_same_node_raises():
    sr.schedule_reboot(node_id=3, node_name="n3", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    with pytest.raises(sr.RebootError) as ei:
        sr.schedule_reboot(node_id=3, node_name="n3", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert ei.value.code == "duplicate_pending"


def test_cancel_unknown_raises():
    with pytest.raises(sr.RebootError) as ei:
        sr.cancel_reboot("missing")
    assert ei.value.code == "not_found"


def test_list_pending_only_active():
    p = sr.schedule_reboot(node_id=4, node_name="n4", scheduled_by="a", execute_fn=Mock(), delay_seconds=5.0)
    assert [x.reboot_id for x in sr.list_pending()] == [p.reboot_id]
    sr.cancel_reboot(p.reboot_id)
    assert sr.list_pending() == []


def test_execute_failure_marks_failed():
    def boom(_p):
        raise RuntimeError("nope")

    pending = sr.schedule_reboot(
        node_id=5,
        node_name="n5",
        scheduled_by="a",
        execute_fn=boom,
        delay_seconds=0.05,
    )
    time.sleep(0.12)
    assert sr.get_pending(pending.reboot_id).status == "failed"
```

- [ ] **Step 2: Run tests — expect fail (module missing)**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_server_reboot.py -v`  
Expected: FAIL import / not found  
**Do not** call real reboot anywhere.

- [ ] **Step 3: Implement `server_reboot.py`**

```python
# backend/app/services/server_reboot.py
"""Scheduled OS reboot with cancel window (in-memory; not durable across process restart)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable

DELAY_SECONDS = 15
CONFIRM_PHRASE = "REBOOT"

ExecuteFn = Callable[["PendingReboot"], None]


class RebootError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PendingReboot:
    reboot_id: str
    node_id: int
    node_name: str
    scheduled_by: str
    created_at: datetime
    execute_at: datetime
    status: str  # pending | cancelled | executed | failed


_lock = threading.Lock()
_pending: dict[str, PendingReboot] = {}
_node_index: dict[int, str] = {}
_timers: dict[str, threading.Timer] = {}
_execute_fns: dict[str, ExecuteFn] = {}


def clear_all_for_tests() -> None:
    with _lock:
        for t in _timers.values():
            t.cancel()
        _pending.clear()
        _node_index.clear()
        _timers.clear()
        _execute_fns.clear()


def list_pending() -> list[PendingReboot]:
    with _lock:
        return [replace(p) for p in _pending.values() if p.status == "pending"]


def get_pending(reboot_id: str) -> PendingReboot | None:
    with _lock:
        p = _pending.get(reboot_id)
        return replace(p) if p else None


def schedule_reboot(
    *,
    node_id: int,
    node_name: str,
    scheduled_by: str,
    execute_fn: ExecuteFn | None = None,
    delay_seconds: float | None = None,
) -> PendingReboot:
    delay = float(DELAY_SECONDS if delay_seconds is None else delay_seconds)
    now = datetime.now(timezone.utc)
    reboot_id = str(uuid.uuid4())
    pending = PendingReboot(
        reboot_id=reboot_id,
        node_id=node_id,
        node_name=node_name,
        scheduled_by=scheduled_by,
        created_at=now,
        execute_at=now + timedelta(seconds=delay),
        status="pending",
    )

    def _run() -> None:
        with _lock:
            current = _pending.get(reboot_id)
            if current is None or current.status != "pending":
                return
            fn = _execute_fns.get(reboot_id)
        try:
            if fn is not None:
                fn(current)
            status = "executed"
        except Exception:
            status = "failed"
        with _lock:
            current = _pending.get(reboot_id)
            if current is None or current.status != "pending":
                return
            _pending[reboot_id] = replace(current, status=status)
            _node_index.pop(node_id, None)
            _timers.pop(reboot_id, None)
            _execute_fns.pop(reboot_id, None)

    with _lock:
        if node_id in _node_index:
            raise RebootError("duplicate_pending", "Перезагрузка этого узла уже запланирована")
        _pending[reboot_id] = pending
        _node_index[node_id] = reboot_id
        if execute_fn is not None:
            _execute_fns[reboot_id] = execute_fn
        timer = threading.Timer(delay, _run)
        timer.daemon = True
        _timers[reboot_id] = timer
        timer.start()
    return replace(pending)


def cancel_reboot(reboot_id: str) -> PendingReboot:
    with _lock:
        current = _pending.get(reboot_id)
        if current is None:
            raise RebootError("not_found", "Запланированная перезагрузка не найдена")
        if current.status != "pending":
            raise RebootError("not_cancellable", "Перезагрузку уже нельзя отменить")
        timer = _timers.pop(reboot_id, None)
        if timer is not None:
            timer.cancel()
        updated = replace(current, status="cancelled")
        _pending[reboot_id] = updated
        _node_index.pop(current.node_id, None)
        _execute_fns.pop(reboot_id, None)
        return replace(updated)
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_server_reboot.py -v`  
Expected: PASS

- [ ] **Step 5: Commit** (only if user asked)

```bash
git add backend/app/services/server_reboot.py backend/tests/test_server_reboot.py
git commit -m "$(cat <<'EOF'
feat: add cancellable pending OS reboot scheduler

EOF
)"
```

---

### Task 2: Adapter + antizapret + node agent `reboot()` (mocked tests only)

**Files:**
- Modify: `backend/app/services/antizapret.py` — add `reboot()` next to `restart_service`
- Modify: `backend/app/services/node_adapter.py` — abstract + Local + Remote
- Modify: `backend/node_agent/main.py` — `POST /reboot`
- Create: `backend/tests/test_node_adapter_reboot.py`

**Interfaces:**
- Consumes: existing `subprocess.run` pattern from `AntizapretService.restart_service`
- Produces:
  - `AntizapretService.reboot() -> str`
  - `NodeAdapter.reboot() -> str`
  - `LocalNodeAdapter.reboot()` → `_service.reboot()`
  - `RemoteNodeAdapter.reboot()` → `POST /reboot`
  - Agent route returns `{"message": "...", "detail": "..."}`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_node_adapter_reboot.py
from unittest.mock import MagicMock, patch

from app.services.antizapret import AntizapretService


def test_antizapret_reboot_calls_systemctl_no_wall():
    svc = AntizapretService(base_path="/tmp")
    fake = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch("app.services.antizapret.subprocess.run", return_value=fake) as run:
        out = svc.reboot()
    run.assert_called_once()
    args = run.call_args[0][0]
    assert args[:2] == ["systemctl", "reboot"]
    assert "--no-wall" in args
    assert run.call_args.kwargs.get("shell") in (None, False)
    assert "ok" in out


def test_remote_adapter_reboot_posts_endpoint():
    from app.services.node_adapter import RemoteNodeAdapter

    adapter = RemoteNodeAdapter.__new__(RemoteNodeAdapter)
    adapter._request = MagicMock(return_value={"message": "Узел перезагружается", "detail": "systemctl"})
    result = RemoteNodeAdapter.reboot(adapter)
    assert result == "systemctl"
    adapter._request.assert_called_once_with("POST", "/reboot")
```

- [ ] **Step 2: Run — expect fail**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_node_adapter_reboot.py -v`  
Expected: FAIL (`reboot` missing)

- [ ] **Step 3: Implement**

In `AntizapretService` (after `restart_service`):

```python
def reboot(self) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "reboot", "--no-wall"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # reboot may not return; treat timeout after invoke as likely success path if needed.
        # Prefer: if process started, return "reboot issued (timeout waiting for exit)"
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Таймаут команды reboot",
        ) from exc
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=output or "Ошибка reboot",
        )
    return output or "reboot issued"
```

Note for implementer: on many hosts `systemctl reboot` returns 0 immediately; do **not** require live reboot in tests — only assert argv.

`NodeAdapter` ABC: add `def reboot(self) -> str: ...` next to `restart_service`.

`LocalNodeAdapter.reboot`: `return self._service.reboot()`

`RemoteNodeAdapter.reboot`:

```python
def reboot(self) -> str:
    data = self._request("POST", "/reboot")
    return data.get("detail") or data.get("message", "ok")
```

`node_agent/main.py`:

```python
@app.post("/reboot")
def reboot_host(_: None = Depends(verify_api_key)):
    output = service.reboot()
    return {"message": "Узел перезагружается", "detail": output}
```

- [ ] **Step 4: Run tests — pass**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_node_adapter_reboot.py -v`  
Expected: PASS  
**Never** remove the mock and call real systemctl reboot.

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 3: Schemas + maintenance API + notify keys + API tests

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/maintenance.py`
- Modify: `backend/app/services/admin_notify.py` — add keys to `SETTINGS_TG_KEYS` / `SETTINGS_TG_TITLES`:
  - `settings_reboot_schedule` → «Перезагрузка ОС (план)»
  - `settings_reboot_cancel` → «Перезагрузка ОС (отмена)»
  - `settings_reboot_execute` → «Перезагрузка ОС»
- Create: `backend/tests/test_settings_reboot_api.py`
- Modify: `frontend/src/lib/actionLogLabels.ts` (can be this task or Task 4 — do here)

**Interfaces:**
- Consumes: `server_reboot.schedule_reboot` / `cancel_reboot` / `list_pending` / `CONFIRM_PHRASE` / `RebootError`; `get_adapter_for_node`; `db.query(Node)`
- Produces:
  - `ServerRebootRequest(node_id: int, confirm: str)`
  - `ServerRebootPendingItem` / `ServerRebootScheduleResponse` / `ServerRebootPendingResponse`
  - Routes callable from Telegram like `restart_service` (plain functions with Request/db/admin)

```python
class ServerRebootRequest(BaseModel):
    node_id: int
    confirm: str


class ServerRebootPendingItem(BaseModel):
    reboot_id: str
    node_id: int
    node_name: str
    scheduled_by: str
    created_at: datetime
    execute_at: datetime
    delay_seconds: int
    warning: str | None = None


class ServerRebootScheduleResponse(ServerRebootPendingItem):
    message: str = "Перезагрузка ОС запланирована"


class ServerRebootPendingResponse(BaseModel):
    items: list[ServerRebootPendingItem]
```

- [ ] **Step 1: Write API tests (mocked execute — no real reboot)**

```python
# backend/tests/test_settings_reboot_api.py
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.routers import maintenance as maintenance_router
from app.services import server_reboot as sr


@pytest.fixture(autouse=True)
def _clean():
    sr.clear_all_for_tests()
    yield
    sr.clear_all_for_tests()


def _admin():
    u = MagicMock(spec=User)
    u.username = "admin"
    u.id = 1
    return u


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(maintenance_router.router, prefix="/api")
    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c


def test_schedule_rejects_bad_confirm(client):
    resp = client.post("/api/settings/reboot", json={"node_id": 1, "confirm": "reboot"})
    assert resp.status_code == 400


def test_schedule_and_cancel(client):
    node = MagicMock()
    node.id = 10
    node.name = "vpn-a"
    node.status = "online"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = node

    def override_db():
        return db

    client.app.dependency_overrides[get_db] = override_db

    with patch("app.routers.maintenance.get_adapter_for_node") as get_ad, patch(
        "app.routers.maintenance.admin_notify_service"
    ), patch("app.routers.maintenance.log_action"):
        adapter = MagicMock()
        adapter.reboot = MagicMock(return_value="ok")
        get_ad.return_value = adapter
        # Force delay inside route by patching schedule to use delay_seconds=5 but we cancel immediately
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["node_id"] == 10
        rid = body["reboot_id"]
        cancel = client.post(f"/api/settings/reboot/{rid}/cancel")
        assert cancel.status_code == 200
        adapter.reboot.assert_not_called()


def test_pending_list(client):
    with patch("app.routers.maintenance.admin_notify_service"), patch(
        "app.routers.maintenance.log_action"
    ), patch("app.routers.maintenance.get_adapter_for_node"):
        # manually insert pending via service without adapter execute
        sr.schedule_reboot(node_id=1, node_name="n", scheduled_by="a", execute_fn=MagicMock(), delay_seconds=5)
        resp = client.get("/api/settings/reboot/pending")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
```

Implementer: adjust imports/overrides to match how other maintenance tests are structured if a closer pattern exists (`tests/test_*.py` for settings). Prefer existing TestClient fixtures from the repo when present.

- [ ] **Step 2: Run — expect fail**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_settings_reboot_api.py -v`

- [ ] **Step 3: Implement routes in `maintenance.py`**

Logic sketch:

```python
@router.post("/settings/reboot", response_model=ServerRebootScheduleResponse)
def schedule_server_reboot(payload: ServerRebootRequest, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if payload.confirm != CONFIRM_PHRASE:
        raise HTTPException(400, detail="Введите REBOOT для подтверждения")
    node = db.query(Node).filter(Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(404, detail="Узел не найден")
    warning = None
    # if node.status offline/unknown → warning string
    def _execute(pending: PendingReboot) -> None:
        from app.database import SessionLocal
        worker_db = SessionLocal()
        try:
            n = worker_db.query(Node).filter(Node.id == pending.node_id).first()
            if not n:
                raise RuntimeError("node missing")
            adapter = get_adapter_for_node(n)
            adapter.reboot()
            log_action(...)
            admin_notify_service.send_settings_change(..., settings_key="settings_reboot_execute", subject_name=pending.node_name, ...)
        finally:
            worker_db.close()

    try:
        pending = schedule_reboot(
            node_id=node.id,
            node_name=node.name,
            scheduled_by=admin.username,
            execute_fn=_execute,
        )
    except RebootError as exc:
        code = 409 if exc.code == "duplicate_pending" else 400
        raise HTTPException(code, detail=exc.message) from exc

    log_action(... settings_reboot_schedule ...)
    admin_notify_service.send_settings_change(..., settings_key="settings_reboot_schedule", ...)
    return ServerRebootScheduleResponse(...)
```

Also `cancel_server_reboot` and `list_server_reboots_pending`.

Wire `log_action` with node id/name in details consistently with `restart_service`.

- [ ] **Step 4: Add notify keys + actionLogLabels**

```ts
settings_reboot_schedule: 'Планирование перезагрузки ОС',
settings_reboot_cancel: 'Отмена перезагрузки ОС',
settings_reboot_execute: 'Перезагрузка ОС сервера',
```

- [ ] **Step 5: Run API tests — pass**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_settings_reboot_api.py tests/test_server_reboot.py -v`

- [ ] **Step 6: Commit** (only if user asked)

---

### Task 4: Frontend — ConfirmDialog phrase + MaintenanceTab card

**Files:**
- Modify: `frontend/src/components/shared/ConfirmDialog.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types.ts` (if types live there)
- Modify: `frontend/src/components/settings/MaintenanceTab.tsx`

**Interfaces:**
- Consumes: `/settings/reboot`, `/settings/reboot/{id}/cancel`, `/settings/reboot/pending`, `getNodes()`
- Produces: UI card «Перезагрузка сервера»

- [ ] **Step 1: Extend ConfirmDialog**

Add optional props:

```ts
confirmPhrase?: string
confirmPhraseLabel?: string // default: `Введите ${confirmPhrase} для подтверждения`
```

When `confirmPhrase` set:
- show `<Input>` 
- disable confirm button until `value === confirmPhrase`
- do not change behavior when prop omitted

- [ ] **Step 2: API helpers**

```ts
export async function scheduleServerReboot(nodeId: number, confirm: 'REBOOT') {
  return apiFetch<ServerRebootScheduleResponse>('/settings/reboot', {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId, confirm }),
  })
}

export async function cancelServerReboot(rebootId: string) {
  return apiFetch<{ message: string }>(`/settings/reboot/${rebootId}/cancel`, { method: 'POST' })
}

export async function getPendingServerReboots() {
  return apiFetch<{ items: ServerRebootPendingItem[] }>('/settings/reboot/pending')
}
```

Add matching types in `types.ts`.

- [ ] **Step 3: MaintenanceTab card**

Below VPN service restart card:
- Title: «Перезагрузка сервера»
- Description: перезагрузка **ОС** выбранного VPN-узла; не путать с перезапуском панели
- Node selector from `getNodes()` (mark active)
- Button opens confirm with `confirmPhrase="REBOOT"`, destructive
- On success: store pending, start 1s interval polling `getPendingServerReboots`, show countdown until `execute_at`, Cancel button
- On cancel success: clear banner + toast

Use `useConfirmDialog` + `ConfirmDialogHost` like `PanelRestartCard`.

- [ ] **Step 4: Manual UI check (no real reboot)**  
Open Maintenance tab, open dialog, verify button disabled until `REBOOT`, then **Cancel** dialog without confirming — do not schedule on production host during agent work unless user explicitly wants a dry-run against mocked backend.

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 5: Telegram maintenance reboot flow

**Files:**
- Modify: `backend/app/services/telegram_bot_handlers/settings_fsm.py` — add `"mnt_reboot"` to `FieldKind`
- Modify: `backend/app/services/telegram_bot_handlers/settings_maintenance.py`
- Modify: `backend/app/services/telegram_bot_handlers/settings.py` — dispatch `handle_maintenance_text` for `mnt_reboot`
- Create: `backend/tests/test_telegram_reboot.py`

**Interfaces:**
- Consumes: maintenance route functions `schedule_server_reboot` / `cancel_server_reboot` via `_make_bot_request(ctx)` pattern; `Node` list like `/nodes`
- Callback prefix: `st:mnt:reboot...`

Suggested callback map:
- `st:mnt:reboot` — list nodes
- `st:mnt:reboot:n:{node_id}` — confirm screen
- `st:mnt:reboot:ask:{node_id}` — set FSM `mnt_reboot` with pending value = node_id (store node_id in `PendingInput.value`)
- `st:mnt:reboot:cancel:{reboot_id}` — cancel
- Existing cancel to `st:mnt`

Flow in `handle_maintenance_callback` / new helpers:
1. List nodes buttons
2. Confirm «Точно перезагрузить \<name\>?»
3. On ✅ → `settings_fsm.set_pending(uid, "mnt_reboot"); set_pending_value(uid, str(node_id))` + prompt «Отправьте `REBOOT`»
4. Text handler: if value == `REBOOT`, call schedule API; else error and keep FSM
5. After schedule: message with Cancel button

- [ ] **Step 1: Write bot unit tests with mocks**

```python
# backend/tests/test_telegram_reboot.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers import settings_maintenance as mnt


@pytest.fixture(autouse=True)
def _fsm():
    settings_fsm.clear_all()
    yield
    settings_fsm.clear_all()


@pytest.mark.asyncio
async def test_reboot_phrase_schedules():
    ctx = MagicMock()
    ctx.telegram_user_id = "1"
    ctx.bot_token = "t"
    ctx.chat_id = 1
    ctx.db = MagicMock()
    ctx.user = MagicMock(username="admin")
    settings_fsm.set_pending("1", "mnt_reboot")
    settings_fsm.set_pending_value("1", "42")

    with patch.object(mnt, "_require_admin_ctx", new=AsyncMock(return_value=True)), patch(
        "app.services.telegram_bot_handlers.settings_maintenance.send_message", new=AsyncMock()
    ) as send, patch(
        "app.services.telegram_bot_handlers.settings_maintenance.schedule_server_reboot"
    ) as sched, patch(
        "app.services.telegram_bot_handlers.settings_maintenance._make_bot_request", return_value=MagicMock()
    ), patch(
        "app.services.telegram_bot_handlers.settings_maintenance._log_bot_action"
    ):
        # Import path: implement handle_maintenance_text that calls router
        sched.return_value = MagicMock(
            reboot_id="r1", node_name="n", delay_seconds=15, execute_at=MagicMock(isoformat=lambda: "t")
        )
        # If handler lives in settings_maintenance:
        ok = await mnt.handle_maintenance_text(ctx, "REBOOT")
        assert ok is True
        sched.assert_called_once()
        assert settings_fsm.get_pending("1") is None
```

Implementer: align with how `handle_security_text` is wired from `handle_settings_text`.

- [ ] **Step 2: Add keyboard button to `_maintenance_keyboard`**

```python
[inline_button("🔁 Перезагрузка сервера", callback_data="st:mnt:reboot")],
```

- [ ] **Step 3: Implement callback + text handlers** (admin only; use same API functions; never call adapter.reboot in tests)

- [ ] **Step 4: Run**

Run: `cd /opt/AdminPanelAZ/backend && ../.venv/bin/pytest tests/test_telegram_reboot.py tests/test_settings_reboot_api.py tests/test_server_reboot.py -v`  
Expected: PASS without real reboot

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 6: Docs + CHANGELOG + guide copy

**Files:**
- Modify: `frontend/src/components/telegram/TelegramBotCommandsGuide.tsx` — in admin section note that reboot is under `/settings` → Обслуживание
- Modify: `docs/Telegram.md` — short subsection
- Modify: `CHANGELOG.md` under `[Unreleased]`
- Modify: `docs/superpowers/specs/2026-08-13-server-reboot-design.md` status → `implemented` when done

- [ ] **Step 1: CHANGELOG entry (Russian)**

```markdown
### Added
- Перезагрузка ОС VPN-узла из Настройки → Обслуживание и Telegram `/settings` → Обслуживание (фраза `REBOOT`, задержка 15 с, отмена)
```

- [ ] **Step 2: Telegram.md** — 5–10 lines describing flow and safety

- [ ] **Step 3: Guide** — one line under admin `/settings` description

- [ ] **Step 4: Commit** (only if user asked)

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Any Node, not only active | Task 3 API `node_id`, Task 4 selector, Task 5 node list |
| Double confirm + `REBOOT` | Tasks 3–5 |
| 15s + cancel panel/TG | Tasks 1, 3, 4, 5 |
| Pending service not durable across panel restart | Task 1 (in-memory only) |
| Adapter local/remote + agent | Task 2 |
| Admin only | Tasks 3, 5 |
| Audit + notify keys | Task 3 |
| No real reboot in tests | Global Constraints + all test steps |
| No `/reboot` slash command | Task 5–6 (maintenance only) |
| Distinct from panel restart | Task 4 copy |

No TBD/placeholder steps remain after implementer fills route wiring to match existing test fixtures (API test may need small adjustment to project TestClient style — still concrete).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-13-server-reboot.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
