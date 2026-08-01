# NOC Personal Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each admin set personal daily/weekly NOC Telegram report times in their profile timezone, replacing the single UTC env-cron blast.

**Architecture:** Store `noc_daily_time`, `noc_weekly_dow`, `noc_weekly_time` on `users`. Scheduler ticks every ~60s, evaluates each eligible admin in `effective_user_timezone(user)`, and sends text (and weekly PNG) to that user only. Empty personal fields fall back to env UTC cron. Matching helpers live in a small `noc_schedule.py` module.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, existing `noc_report_scheduler` loop, React Personal settings UI, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-01-noc-personal-schedule-design.md`
- Time interpreted via `effective_user_timezone` (`timezone` → `last_client_timezone` → UTC)
- Weekly personal schedule requires **both** dow and time non-empty
- Admin-only fields; role `user` must not write them
- Empty personal fields → env `NOC_REPORT_DAILY_CRON` / `NOC_REPORT_WEEKLY_CRON` (UTC)
- Do not invent commits unless the user explicitly asks; skip commit steps during execution unless told to commit
- Docs in Russian for user-facing pages; map UI in `docs/PROJECT_MAP.md`

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/noc_schedule.py` | Parse HH:MM / dow; local-now match; build personal vs env decision |
| `backend/app/models.py` | New user columns |
| `backend/app/database.py` | SQLite column migration entries |
| `backend/app/services/noc_report.py` | `recipients=` on send paths; single-user weekly image |
| `backend/app/services/noc_report_scheduler.py` | Per-user tick + per-user last_run keys |
| `backend/app/schemas.py` | Expose fields on AppSettings + UserResponse |
| `backend/app/routers/settings.py` | GET/PATCH personal NOC schedule |
| `backend/tests/test_noc_schedule.py` | Unit tests for match/parse/scheduler decision |
| `frontend/src/types.ts` | Types |
| `frontend/src/components/settings/NocScheduleCard.tsx` | New UI card |
| `frontend/src/components/settings/PersonalTab.tsx` | Mount card for admin |
| `docs/Telegram.md`, `docs/noc-monitoring.md`, `docs/PROJECT_MAP.md`, `CHANGELOG.md` | Docs |

---

### Task 1: Schedule helpers (`noc_schedule.py`) + unit tests

**Files:**
- Create: `backend/app/services/noc_schedule.py`
- Create: `backend/tests/test_noc_schedule.py`

**Interfaces:**
- Produces:
  - `parse_hhmm(raw: str | None) -> tuple[int, int] | None`
  - `parse_cron_dow(raw: str | None) -> int | None`  # 0=Sun … 6=Sat
  - `local_now_for_user(user, now_utc: datetime) -> datetime`
  - `should_run_daily(user, *, now_utc: datetime, env_daily_cron: str) -> bool`
  - `should_run_weekly(user, *, now_utc: datetime, env_weekly_cron: str) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_noc_schedule.py
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.noc_schedule import (
    parse_hhmm,
    parse_cron_dow,
    should_run_daily,
    should_run_weekly,
)


def test_parse_hhmm_valid_and_invalid():
    assert parse_hhmm("11:00") == (11, 0)
    assert parse_hhmm(" 9:05 ") == (9, 5)
    assert parse_hhmm("") is None
    assert parse_hhmm("25:00") is None
    assert parse_hhmm("ab:cd") is None


def test_parse_cron_dow():
    assert parse_cron_dow("1") == 1
    assert parse_cron_dow("0") == 0
    assert parse_cron_dow("7") is None
    assert parse_cron_dow("") is None


def test_daily_personal_matches_moscow_not_utc():
    # 08:00 UTC == 11:00 Europe/Moscow
    user = SimpleNamespace(
        timezone="",
        last_client_timezone="Europe/Moscow",
        noc_daily_time="11:00",
        noc_weekly_dow="",
        noc_weekly_time="",
    )
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=now, env_daily_cron="0 8 * * *") is True
    earlier = datetime(2026, 8, 1, 7, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=earlier, env_daily_cron="0 8 * * *") is False


def test_daily_empty_falls_back_to_env_utc_cron():
    user = SimpleNamespace(
        timezone="Europe/Moscow",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="",
        noc_weekly_time="",
    )
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=now, env_daily_cron="0 8 * * *") is True
    # 11:00 MSK would be wrong for empty personal + env 08:00 UTC only
    at_msk_11_as_utc = datetime(2026, 8, 1, 11, 0, tzinfo=timezone.utc)
    assert should_run_daily(user, now_utc=at_msk_11_as_utc, env_daily_cron="0 8 * * *") is False


def test_weekly_requires_both_fields_else_env():
    user = SimpleNamespace(
        timezone="Europe/Moscow",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="1",  # Monday
        noc_weekly_time="",  # incomplete → env
    )
    # Monday 09:00 UTC
    now = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)  # 2026-08-03 is Monday
    assert should_run_weekly(user, now_utc=now, env_weekly_cron="0 9 * * 1") is True

    user2 = SimpleNamespace(
        timezone="Europe/Moscow",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="1",
        noc_weekly_time="12:00",
    )
    # Monday 09:00 UTC = 12:00 MSK
    assert should_run_weekly(user2, now_utc=now, env_weekly_cron="0 9 * * 1") is True
    assert should_run_weekly(
        user2,
        now_utc=datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc),
        env_weekly_cron="0 9 * * 1",
    ) is False
```

- [ ] **Step 2: Run tests — expect FAIL (import error)**

Run: `cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_noc_schedule.py -q`

Expected: collection/import error for `app.services.noc_schedule`

- [ ] **Step 3: Implement helpers**

```python
# backend/app/services/noc_schedule.py
"""Per-admin NOC report schedule matching (local HH:MM + optional env cron fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services.cron_schedule import cron_matches_now, cron_weekday_value
from app.services.notify_time import effective_user_timezone


def parse_hhmm(raw: str | None) -> tuple[int, int] | None:
    text = str(raw or "").strip()
    if not text or ":" not in text:
        return None
    left, _, right = text.partition(":")
    if not left.isdigit() or not right.isdigit():
        return None
    hour, minute = int(left), int(right)
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_cron_dow(raw: str | None) -> int | None:
    text = str(raw or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    if value < 0 or value > 6:
        return None
    return value


def local_now_for_user(user: Any, now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    tz_name = effective_user_timezone(user) or "UTC"
    return now_utc.astimezone(ZoneInfo(tz_name))


def should_run_daily(user: Any, *, now_utc: datetime, env_daily_cron: str) -> bool:
    parsed = parse_hhmm(getattr(user, "noc_daily_time", None))
    if parsed is not None:
        local = local_now_for_user(user, now_utc)
        hour, minute = parsed
        return local.hour == hour and local.minute == minute
    return cron_matches_now(env_daily_cron, now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc))


def should_run_weekly(user: Any, *, now_utc: datetime, env_weekly_cron: str) -> bool:
    dow = parse_cron_dow(getattr(user, "noc_weekly_dow", None))
    parsed = parse_hhmm(getattr(user, "noc_weekly_time", None))
    if dow is not None and parsed is not None:
        local = local_now_for_user(user, now_utc)
        hour, minute = parsed
        return cron_weekday_value(local) == dow and local.hour == hour and local.minute == minute
    return cron_matches_now(env_weekly_cron, now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc))
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_noc_schedule.py -q`

Expected: all passed

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 2: User model + DB migration columns

**Files:**
- Modify: `backend/app/models.py` (`User` class, after `last_client_timezone`)
- Modify: `backend/app/database.py` (`users` migration list near `last_client_timezone`)

**Interfaces:**
- Produces: `User.noc_daily_time: str`, `User.noc_weekly_dow: str`, `User.noc_weekly_time: str` (default `""`)

- [ ] **Step 1: Add columns to model**

```python
noc_daily_time: Mapped[str] = mapped_column(String(5), default="")
noc_weekly_dow: Mapped[str] = mapped_column(String(1), default="")
noc_weekly_time: Mapped[str] = mapped_column(String(5), default="")
```

- [ ] **Step 2: Add migration tuples in `run_db_migrations` users list**

```python
("noc_daily_time", "VARCHAR(5) DEFAULT ''"),
("noc_weekly_dow", "VARCHAR(1) DEFAULT ''"),
("noc_weekly_time", "VARCHAR(5) DEFAULT ''"),
```

- [ ] **Step 3: Apply migration on running DB**

Run:

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -c "
from app.database import run_db_migrations, engine
from sqlalchemy import inspect
run_db_migrations()
cols = {c['name'] for c in inspect(engine).get_columns('users')}
assert {'noc_daily_time','noc_weekly_dow','noc_weekly_time'} <= cols
print('ok')
"
```

Expected: `ok`

- [ ] **Step 4: Commit** (only if user asked)

---

### Task 3: Per-recipient send APIs in `noc_report.py`

**Files:**
- Modify: `backend/app/services/noc_report.py` — `send_noc_report`, `send_weekly_image_report`
- Test: extend `backend/tests/test_noc_schedule.py` or add `backend/tests/test_noc_report_recipients.py` with mocks

**Interfaces:**
- Consumes: existing `_notify_recipients`, `format_noc_report_message`, `resolve_notify_timezone`
- Produces:
  - `send_noc_report(db, *, period: str, recipients: list[User] | None = None) -> dict`
  - `send_weekly_image_report(db, *, recipients: list[User] | None = None, ...) -> dict`
  When `recipients` is passed, skip `_notify_recipients()` and use the list as-is (still require bot token / feature flags).

- [ ] **Step 1: Write failing test** that monkeypatches send and asserts only one telegram_id is used when `recipients=[one_user]`

```python
def test_send_noc_report_honors_explicit_recipients(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from app.services import noc_report

    user = SimpleNamespace(id=1, telegram_id="111", timezone="Europe/Moscow", last_client_timezone="")
    sent: list[str] = []
    monkeypatch.setattr(noc_report, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda k: True))
    monkeypatch.setattr(noc_report, "_get_setting", lambda db, k, d="": "true" if "enabled" in k else "token")
    monkeypatch.setattr(noc_report, "build_noc_report_data", lambda db, period="daily": {"period": period, "summary": {
        "nodes_online": 1, "nodes_total": 1, "total_openvpn": 0, "total_wireguard": 0,
        "total_openvpn_peak": 0, "total_wireguard_peak": 0,
    }})
    monkeypatch.setattr(noc_report, "format_noc_report_message", lambda data, client_timezone=None: "TEXT")
    monkeypatch.setattr(noc_report, "send_tg_message", lambda token, chat_id, text, **kw: sent.append(chat_id) or True)
    monkeypatch.setattr(noc_report, "_notify_recipients", lambda db: (_ for _ in ()).throw(AssertionError("should not call")))

    db = MagicMock()
    result = noc_report.send_noc_report(db, period="daily", recipients=[user])
    assert result["status"] == "sent"
    assert sent == ["111"]
```

- [ ] **Step 2: Run test — expect FAIL** (unexpected keyword `recipients`)

- [ ] **Step 3: Implement `recipients` parameter**

In `send_noc_report`:

```python
def send_noc_report(db: Session, *, period: str, recipients: list[User] | None = None) -> dict:
    ...
    target_users = recipients if recipients is not None else _notify_recipients(db)
    if not target_users:
        return {"status": "skipped", "reason": "no_recipients"}
    report_data = build_noc_report_data(db, period=period)
    text = format_noc_report_message(
        report_data,
        client_timezone=resolve_notify_timezone(users=target_users),
    )
    ...
```

Same pattern for `send_weekly_image_report(..., recipients: list[User] | None = None)` — use `resolve_notify_timezone(users=target_users)` for caption.

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 4: Rewrite `noc_report_scheduler.py` for per-user delivery

**Files:**
- Modify: `backend/app/services/noc_report_scheduler.py`
- Test: `backend/tests/test_noc_schedule.py` (scheduler tick tests with mocks)

**Interfaces:**
- Consumes: `should_run_daily`, `should_run_weekly`, `send_noc_report(..., recipients=[u])`, `send_weekly_image_report(..., recipients=[u])`, `_notify_recipients`
- Produces: `run_noc_report_scheduler_tick` returns list of per-user results; last_run keys `noc_report_daily_last_run:{user_id}` / `noc_report_weekly_last_run:{user_id}`
- Dedup compares **local** year/month/day/hour/minute via `local_now_for_user`

- [ ] **Step 1: Write failing scheduler tests**

```python
def test_scheduler_sends_only_matching_user(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from app.services import noc_report_scheduler as sched

    u_match = SimpleNamespace(
        id=1, telegram_id="1", role="admin",
        timezone="Europe/Moscow", last_client_timezone="",
        noc_daily_time="11:00", noc_weekly_dow="", noc_weekly_time="",
        has_tg_notify_event=lambda k: True,
    )
    u_other = SimpleNamespace(
        id=2, telegram_id="2", role="admin",
        timezone="Europe/Moscow", last_client_timezone="",
        noc_daily_time="15:00", noc_weekly_dow="", noc_weekly_time="",
        has_tg_notify_event=lambda k: True,
    )
    sent: list[int] = []

    monkeypatch.setattr(sched, "get_settings", lambda: SimpleNamespace(
        noc_report_enabled=True,
        noc_report_daily_cron="0 8 * * *",
        noc_report_weekly_cron="0 9 * * 1",
        noc_report_weekly_image_enabled=False,
    ))
    monkeypatch.setattr(sched, "SessionLocal", lambda: MagicMock())
    # Patch internals used by tick — prefer extracting run_for_users(now, users) for testability

    # After refactor, call the pure function:
    from app.services.noc_report_scheduler import process_user_noc_tick

    monkeypatch.setattr(
        "app.services.noc_report_scheduler.send_noc_report",
        lambda db, period, recipients=None: sent.append(recipients[0].id) or {"status": "sent", "sent": 1, "recipients": 1},
    )
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    db = MagicMock()
    monkeypatch.setattr(sched, "_already_ran_local_minute", lambda *a, **k: False)
    monkeypatch.setattr(sched, "_set_setting", lambda *a, **k: None)

    process_user_noc_tick(db, u_match, now=now, settings=sched.get_settings())
    process_user_noc_tick(db, u_other, now=now, settings=sched.get_settings())
    assert sent == [1]
```

Implement `process_user_noc_tick` as the unit under test; `run_noc_report_scheduler_tick` loads recipients and loops.

- [ ] **Step 2: Run — expect FAIL (missing process_user_noc_tick)**

- [ ] **Step 3: Implement scheduler rewrite**

Sketch:

```python
def _last_run_key(period: str, user_id: int) -> str:
    return f"noc_report_{period}_last_run:{user_id}"


def _already_ran_local_minute(db, key: str, local_now: datetime) -> bool:
    # parse ISO last run → convert to same tz → compare y/m/d/h/mi
    ...


def process_user_noc_tick(db, user, *, now: datetime, settings) -> list[dict]:
    results = []
    local = local_now_for_user(user, now)
    if should_run_daily(user, now_utc=now, env_daily_cron=settings.noc_report_daily_cron):
        key = _last_run_key("daily", user.id)
        if not _already_ran_local_minute(db, key, local):
            result = send_noc_report(db, period="daily", recipients=[user])
            if result.get("status") in ("sent", "skipped"):
                _set_setting(db, key, now.isoformat())
            results.append({"user_id": user.id, "period": "daily", **result})
    if should_run_weekly(user, now_utc=now, env_weekly_cron=settings.noc_report_weekly_cron):
        key = _last_run_key("weekly", user.id)
        if not _already_ran_local_minute(db, key, local):
            result = send_noc_report(db, period="weekly", recipients=[user])
            if settings.noc_report_weekly_image_enabled:
                img = send_weekly_image_report(db, recipients=[user])
                result["image"] = img
            if result.get("status") in ("sent", "skipped"):
                _set_setting(db, key, now.isoformat())
            results.append({"user_id": user.id, "period": "weekly", **result})
    return results


def run_noc_report_scheduler_tick(now=None) -> list[dict]:
    settings = get_settings()
    if not settings.noc_report_enabled:
        return [{"status": "disabled"}]
    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        from app.services.noc_report import _notify_recipients
        results = []
        for user in _notify_recipients(db):
            results.extend(process_user_noc_tick(db, user, now=now, settings=settings))
        return results
    finally:
        db.close()
```

Remove old global `_LAST_RUN_KEYS` single-key path (or keep reading once for migration — not required).

- [ ] **Step 4: Run tests — expect PASS**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_noc_schedule.py -q`

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 5: API schemas + settings router + auth UserResponse

**Files:**
- Modify: `backend/app/schemas.py` — `AppSettingsResponse`, `AppSettingsUpdate`, `UserResponse`
- Modify: `backend/app/routers/settings.py` — GET/PATCH
- Modify: `backend/app/routers/auth.py` if `/me` builds UserResponse manually (prefer model attributes)
- Test: small API validation unit test for HH:MM rejection (pure function or TestClient if available)

**Interfaces:**
- Produces JSON fields: `noc_daily_time`, `noc_weekly_dow`, `noc_weekly_time` (strings)
- PATCH validation: use `parse_hhmm` / `parse_cron_dow`; empty string clears to fallback; invalid → 400
- Non-admin PATCH of these fields → ignore or 403 (prefer **ignore** for non-admin to match theme file fields pattern, but **reject** if non-admin explicitly sends them with 403)

- [ ] **Step 1: Extend schemas**

```python
# AppSettingsResponse / UserResponse
noc_daily_time: str = ""
noc_weekly_dow: str = ""
noc_weekly_time: str = ""

# AppSettingsUpdate
noc_daily_time: str | None = None
noc_weekly_dow: str | None = None
noc_weekly_time: str | None = None
```

- [ ] **Step 2: Wire GET/PATCH in settings.py**

On GET include fields from `current_user` (empty for non-admin is fine).

On PATCH when admin:

```python
from app.services.noc_schedule import parse_hhmm, parse_cron_dow

if current_user.role.value == "admin":
    if payload.noc_daily_time is not None:
        raw = payload.noc_daily_time.strip()
        if raw and parse_hhmm(raw) is None:
            raise HTTPException(400, detail="Некорректное время ежедневной NOC-сводки")
        current_user.noc_daily_time = raw
    if payload.noc_weekly_time is not None:
        raw = payload.noc_weekly_time.strip()
        if raw and parse_hhmm(raw) is None:
            raise HTTPException(400, detail="Некорректное время еженедельной NOC-сводки")
        current_user.noc_weekly_time = raw
    if payload.noc_weekly_dow is not None:
        raw = payload.noc_weekly_dow.strip()
        if raw and parse_cron_dow(raw) is None:
            raise HTTPException(400, detail="Некорректный день недели для NOC-сводки")
        current_user.noc_weekly_dow = raw
    db.add(current_user)
```

- [ ] **Step 3: Manual smoke** (optional): restart not required for unit tests; run a tiny test importing schemas

- [ ] **Step 4: Commit** (only if user asked)

---

### Task 6: Frontend Personal NOC schedule card

**Files:**
- Create: `frontend/src/components/settings/NocScheduleCard.tsx`
- Modify: `frontend/src/components/settings/PersonalTab.tsx` — render for admin
- Modify: `frontend/src/types.ts` — User + AppSettings fields
- Modify: `frontend/src/api/client.ts` if `updateSettings` typing needs fields (likely already `Partial`)

**Interfaces:**
- Consumes: `updateSettings`, `useAuth().user`, `useTimezone().effectiveTimeZone`
- Saves via `updateSettings({ noc_daily_time, noc_weekly_dow, noc_weekly_time })` then `refreshUser()`
- UI defaults when empty (display only until save): daily `11:00`, weekly dow `1`, time `12:00`

- [ ] **Step 1: Add types**

```typescript
noc_daily_time?: string
noc_weekly_dow?: string
noc_weekly_time?: string
```

on `User` and settings types that carry timezone.

- [ ] **Step 2: Implement `NocScheduleCard`**

Admin-only card:

- Title: «NOC сводка — расписание»
- Description: время по `effectiveTimeZone`
- Inputs: `<input type="time">` for daily; select Mon–Sun mapped to cron dow 1…0; weekly time
- Save button or auto-save on change (match timezone pattern: save immediately on change)
- Warning if no effective timezone beyond UTC and profile empty

Dow labels (ru): `[{v:'1',l:'Понедельник'}, … {v:'0',l:'Воскресенье'}]`

- [ ] **Step 3: Mount in PersonalTab after timezone card / near PersonalTelegramCard** when `user.role === 'admin'`

- [ ] **Step 4: Build frontend**

Run: `cd /opt/AdminPanelAZ/frontend && npm run build`

Expected: success

- [ ] **Step 5: Commit** (only if user asked)

---

### Task 7: Docs + CHANGELOG + seed Claymore defaults + restart

**Files:**
- Modify: `docs/Telegram.md` — short subsection under AdminNotify / NOC
- Modify: `docs/noc-monitoring.md` — link to personal schedule
- Modify: `docs/PROJECT_MAP.md` — personal settings fields
- Modify: `CHANGELOG.md` — Added/Fixed entry
- Update spec status to approved/implemented

- [ ] **Step 1: Docs text (Russian, no jargon)**

Example for Telegram.md:

```markdown
### Расписание NOC-сводок

Каждый администратор задаёт своё время в **Настройки → Личные → NOC сводка — расписание**.
Время считается по часовому поясу профиля. Пока время не задано, используется системное расписание (UTC).
```

- [ ] **Step 2: Optionally seed admin Claymore** to `noc_daily_time=11:00`, `noc_weekly_dow=1`, `noc_weekly_time=12:00` so next run is 11:00 MSK without waiting for UI save

- [ ] **Step 3: Restart `adminpanelaz` and verify columns + helper**

```bash
systemctl restart adminpanelaz
# wait healthy
cd /opt/AdminPanelAZ/backend && .venv/bin/python -c "
from app.database import SessionLocal
from app.models import User
from app.services.noc_schedule import should_run_daily
from datetime import datetime, timezone
db=SessionLocal(); u=db.query(User).filter_by(username='Claymore').first()
print(u.noc_daily_time, u.noc_weekly_dow, u.noc_weekly_time)
print(should_run_daily(u, now_utc=datetime(2026,8,1,8,0,tzinfo=timezone.utc), env_daily_cron='0 8 * * *'))
"
```

- [ ] **Step 4: Full pytest for new tests**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_noc_schedule.py tests/test_notify_time.py -q`

Expected: all pass

- [ ] **Step 5: Commit** (only if user asked)

---

## Spec coverage self-review

| Spec requirement | Task |
|------------------|------|
| Personal daily HH:MM | 1, 2, 5, 6 |
| Personal weekly dow+time | 1, 2, 5, 6 |
| Profile timezone | 1 (`effective_user_timezone`) |
| Per-user send | 3, 4 |
| Weekly PNG to same user | 4 |
| Env fallback when empty | 1, 4 |
| Dedup per user local minute | 4 |
| Admin-only UI/API | 5, 6 |
| Docs | 7 |
| Acceptance 11:00 MSK | 1 tests + 7 seed |

## Placeholder scan

No TBD/TODO left in steps.

## Type consistency

- Field names: `noc_daily_time`, `noc_weekly_dow`, `noc_weekly_time` everywhere
- Helpers: `should_run_daily` / `should_run_weekly` / `parse_hhmm` / `parse_cron_dow` / `local_now_for_user`
- Send API: `recipients: list[User] | None = None`
- Scheduler: `process_user_noc_tick`, last_run `noc_report_{period}_last_run:{user_id}`
