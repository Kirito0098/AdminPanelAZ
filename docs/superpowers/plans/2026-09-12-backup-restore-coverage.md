# Backup Restore Coverage Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three UX coverage gaps from the A→B→C backup matrix (Push full hint on API restore, upload+restore detail hints, docs/UI clarity that full AntiZapret is a separate archive) without packing nginx/certs/systemd into the panel tar.

**Architecture:** Reuse `_restore_response` as the single hint builder. Extend `BackupEntry` with optional restore fields so `POST /backups/upload?restore=true` can return the same detail shape as `POST /backups/restore`. Docs and BackupTab copy make the separate AZ archive explicit. No machine-image backup.

**Tech Stack:** FastAPI, Pydantic `BackupEntry`/`MessageResponse`, pytest, React BackupTab, Markdown user docs.

**Spec:** `docs/superpowers/specs/2026-09-12-backup-restore-coverage-design.md`

## Global Constraints

- Do **not** pack nginx, Let’s Encrypt, self-signed certs, systemd, or `frontend/dist` into `adminpanelaz_*.tar.gz`.
- Do **not** auto-run `task_portal_publish`, certbot, Применение, or Push full.
- Keep portal post-restore sync (`sync_portal_domain_after_restore`) as already shipped.
- Hints in Russian, matching existing `RESTORE_APPLY_HINT` / CLI stdout tone.
- Prefer extending existing helpers over new modules.
- Commit after each task; use `git add -f` only for paths under `docs/superpowers/` (gitignored).

## File map

| File | Role |
|------|------|
| `backend/app/routers/backups.py` | `RESTORE_PUSH_FULL_HINT`, `_restore_response`, upload+restore return |
| `backend/app/schemas.py` | Optional `restore_message` / `restore_detail` on `BackupEntry` |
| `backend/tests/test_backups_restore_order.py` | Push full hint + upload detail tests |
| `frontend/src/types.ts` | Mirror optional restore fields |
| `frontend/src/api/maintenance.ts` | `uploadBackup` return typing |
| `frontend/src/components/settings/BackupTab.tsx` | Show hints after upload+restore; AZ clarity copy |
| `docs/nastrojki/rezervnye-kopii.md` | A/B/C checklist + separate AZ archive |
| `CHANGELOG.md` | Unreleased note |
| `docs/superpowers/specs/2026-09-12-backup-restore-coverage-design.md` | Status → approved / implemented |

---

### Task 1: API Push full hint in `_restore_response`

**Files:**
- Modify: `backend/app/routers/backups.py` (constants + `_restore_response`)
- Modify: `backend/tests/test_backups_restore_order.py`
- Test: `backend/tests/test_backups_restore_order.py`

**Interfaces:**
- Consumes: `restore_result["restored"]` list may include `"configs"` and/or `"awg2"` (from `BackupManager.load_restore_payload`)
- Produces: `RESTORE_PUSH_FULL_HINT: str`; `_restore_response` may append Push full text to `detail["hint"]`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_backups_restore_order.py`:

```python
def test_restore_response_includes_push_full_hint_for_configs():
    response = backups_mod._restore_response(
        {"restored": ["db", "configs"], "file_name": "panel.tar.gz"}
    )
    assert "Push full" in response.detail["hint"]
    assert "Примен" in response.detail["hint"]


def test_restore_response_includes_push_full_hint_for_awg2_only():
    response = backups_mod._restore_response(
        {"restored": ["db", "awg2"], "file_name": "panel.tar.gz"}
    )
    assert "Push full" in response.detail["hint"]
    assert "Примен" not in response.detail.get("hint", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /opt/AdminPanelAZ && .venv/bin/python -m pytest \
  backend/tests/test_backups_restore_order.py::test_restore_response_includes_push_full_hint_for_configs \
  backend/tests/test_backups_restore_order.py::test_restore_response_includes_push_full_hint_for_awg2_only \
  -v
```

Expected: FAIL (assertion — hint missing Push full / wrong content)

- [ ] **Step 3: Implement Push full hint**

In `backend/app/routers/backups.py`, after `RESTORE_APPLY_HINT`, add:

```python
RESTORE_PUSH_FULL_HINT = (
    "Если есть HA-реплики, выполните Push full "
    "(списки AntiZapret и/или слой AZ-AWG2 восстановлены на активном узле)."
)
```

Update `_restore_response`:

```python
def _restore_response(restore_result: dict) -> MessageResponse:
    from app.services.client_portal import PORTAL_RESTORE_HINT

    detail = {**restore_result, "restart_scheduled": True}
    restored = list(restore_result.get("restored") or [])
    hints: list[str] = []
    if "configs" in restored:
        hints.append(RESTORE_APPLY_HINT)
    if "configs" in restored or "awg2" in restored:
        hints.append(RESTORE_PUSH_FULL_HINT)
    if restore_result.get("portal_reprovision_needed"):
        hints.append(str(restore_result.get("portal_hint") or PORTAL_RESTORE_HINT))
    if hints:
        detail["hint"] = " ".join(hints)
    return MessageResponse(
        message=RESTORE_RESTART_MESSAGE,
        detail=detail,
    )
```

Keep existing portal/apply behavior; do not remove `portal_reprovision_needed` handling.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /opt/AdminPanelAZ && .venv/bin/python -m pytest backend/tests/test_backups_restore_order.py -q --tb=short
```

Expected: all tests in that file PASS (including existing dispose-order and portal hint tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/backups.py backend/tests/test_backups_restore_order.py
git commit -m "$(cat <<'EOF'
Add Push full restore hint when configs or AWG2 were restored.

Match CLI guidance so HA admins see the next step after API restore.
EOF
)"
```

---

### Task 2: upload+restore returns restore detail

**Files:**
- Modify: `backend/app/schemas.py` (`BackupEntry`)
- Modify: `backend/app/routers/backups.py` (`upload_backup` when `restore=True`)
- Modify: `backend/tests/test_backups_restore_order.py` (or new focused tests in same file)
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/maintenance.ts` (only if return type needs widening — keep `BackupEntry`)
- Modify: `frontend/src/components/settings/BackupTab.tsx` (`handleUploadFileSelected`)

**Interfaces:**
- Consumes: `_restore_panel_and_restart(...) -> dict`, `_restore_response(dict) -> MessageResponse`
- Produces: `BackupEntry.restore_message: str | None`, `BackupEntry.restore_detail: dict[str, Any] | None` (populated only when upload restores)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_backups_restore_order.py`:

```python
def test_backup_entry_schema_accepts_restore_detail():
    from app.schemas import BackupEntry

    entry = BackupEntry(
        file_name="adminpanelaz_x.tar.gz",
        size_bytes=10,
        created_at="2026-09-12T00:00:00Z",
        components=["db"],
        summary="db",
        restore_message="Восстановление выполнено. Панель будет перезапущена через несколько секунд.",
        restore_detail={"restart_scheduled": True, "hint": "Push full"},
    )
    assert entry.restore_detail["hint"] == "Push full"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /opt/AdminPanelAZ && .venv/bin/python -m pytest \
  backend/tests/test_backups_restore_order.py::test_backup_entry_schema_accepts_restore_detail -v
```

Expected: FAIL (`restore_message` / `restore_detail` unexpected / validation error)

- [ ] **Step 3: Extend schema and wire upload restore**

In `backend/app/schemas.py` on `BackupEntry` (need `Any` already imported in schemas):

```python
class BackupEntry(BaseModel):
    file_name: str
    size_bytes: int
    created_at: str
    components: list[str] = []
    summary: str = ""
    restore_message: str | None = None
    restore_detail: dict[str, Any] | None = None
```

In `upload_backup`, replace the restore return branch:

```python
    if restore:
        # ... existing audit + notify unchanged ...
        restore_result = _restore_panel_and_restart(manager, result["file_name"], db)
        restore_result.pop("configs", None)
        msg = _restore_response(restore_result)
        return BackupEntry(
            **{k: result[k] for k in ("file_name", "size_bytes", "created_at", "components", "summary") if k in result},
            restore_message=msg.message,
            restore_detail=msg.detail if isinstance(msg.detail, dict) else {"value": msg.detail},
        )
```

If `result` already has exact BackupEntry keys, prefer:

```python
        return BackupEntry(
            file_name=result["file_name"],
            size_bytes=result["size_bytes"],
            created_at=result["created_at"],
            components=result.get("components") or [],
            summary=result.get("summary") or "",
            restore_message=msg.message,
            restore_detail=msg.detail if isinstance(msg.detail, dict) else None,
        )
```

- [ ] **Step 4: Frontend — types + show hint after upload+restore**

`frontend/src/types.ts`:

```typescript
export interface BackupEntry {
  file_name: string
  size_bytes: number
  created_at: string
  components: string[]
  summary: string
  restore_message?: string | null
  restore_detail?: Record<string, unknown> | null
}
```

In `BackupTab.tsx` `handleUploadFileSelected`, when `restoreAfterUpload`:

```typescript
        const uploaded = await withInline(async () => {
          const entry = await uploadBackup(file, restoreAfterUpload)
          await load()
          return entry
        }, restoreAfterUpload ? 'Загрузка, восстановление и перезапуск...' : 'Загрузка архива...')
        if (restoreAfterUpload) {
          const hint =
            typeof uploaded.restore_detail?.hint === 'string' && uploaded.restore_detail.hint.trim()
              ? ` ${uploaded.restore_detail.hint.trim()}`
              : ''
          success(`${uploaded.restore_message || RESTORE_SUCCESS_MESSAGE}${hint}`)
        } else {
          success('Архив загружен и добавлен в список')
        }
```

- [ ] **Step 5: Run backend tests + frontend typecheck**

Run:

```bash
cd /opt/AdminPanelAZ && .venv/bin/python -m pytest backend/tests/test_backups_restore_order.py backend/tests/test_backup_portal_restore.py -q --tb=short
cd /opt/AdminPanelAZ/frontend && npx tsc --noEmit
```

Expected: pytest PASS; `tsc` exit 0

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/backups.py \
  backend/tests/test_backups_restore_order.py \
  frontend/src/types.ts frontend/src/components/settings/BackupTab.tsx
git commit -m "$(cat <<'EOF'
Return restore hints on upload-and-restore backup uploads.

Surface the same apply/Push full/portal detail the restore endpoint already builds.
EOF
)"
```

---

### Task 3: Docs + BackupTab clarity for separate AntiZapret archive + A/B/C checklist

**Files:**
- Modify: `docs/nastrojki/rezervnye-kopii.md`
- Modify: `frontend/src/components/settings/BackupTab.tsx` (AntiZapret scope subtitle / description)
- Modify: `CHANGELOG.md` (Unreleased)
- Modify: `docs/superpowers/specs/2026-09-12-backup-restore-coverage-design.md` (status line → implemented after this task)

**Interfaces:**
- Consumes: matrix from coverage design (scenarios A/B/C)
- Produces: user-facing checklist; UI copy that full VPN is not a panel-list component

- [ ] **Step 1: Update user docs**

In `docs/nastrojki/rezervnye-kopii.md`, after the existing «Клиентский портал после restore» FAQ (or equivalent), add:

```markdown
**Что входит в архив AdminPanel (`adminpanelaz_*.tar.gz`)?**  
База панели (включая даты доступа, unlock и токены портала), CIDR, `.env`. По желанию — списки маршрутизации AntiZapret и узкий слой AZ-AWG2. Полный бэкап VPN (`client.sh 8`, OpenVPN/WireGuard/сертификаты) — **отдельный** файл `backup-*.tar.gz` на VPN-сервере; в списке «Архивы» панели его нет.

### После восстановления (чеклист)

1. **A — панель на том же сервере:** дождаться перезапуска → войти → проверить клиентов и сроки доступа.
2. **B — портал HTTPS:** шаг A → **Подписка** → «Настроить под текущую публикацию» (+ DNS A на хост портала).
3. **C — полный DR:** шаг B → при потере VPN-диска восстановить отдельный AntiZapret-архив на VPN-хосте → при необходимости AWG2-слой → **Применение** для списков → **Push full** при HA → проверить node-agent на репликах.
```

Also fix the create-backup bullet list if it still says «конфиги клиентов» ambiguously — prefer «списки маршрутизации AntiZapret (в тот же архив)» and «полный архив AntiZapret (отдельный файл)».

- [ ] **Step 2: Clarify BackupTab AntiZapret block copy**

In the AntiZapret `BackupScopeBlock` / OptionCard description, ensure text states the full VPN archive is **separate** and does **not** appear in the panel archives list. Example description string:

```text
Отдельный файл backup-*.tar.gz на VPN-узле (не в списке «Архивы» панели). Восстановление — на VPN-сервере, не через «Восстановить» panel-архива.
```

Keep the existing AdminPanel always-included + portal link paragraph from prior work.

- [ ] **Step 3: CHANGELOG + mark spec implemented**

Add under Unreleased Fixed or Changed:

```markdown
- **Бэкап restore hints** — API/upload+restore подсказывают Push full при configs/AWG2; docs чеклист A/B/C и явное разделение полного AntiZapret-архива.
```

Set spec header status to `implemented` (or `approved + implemented`).

- [ ] **Step 4: Commit**

```bash
git add docs/nastrojki/rezervnye-kopii.md \
  frontend/src/components/settings/BackupTab.tsx \
  CHANGELOG.md
git add -f docs/superpowers/specs/2026-09-12-backup-restore-coverage-design.md
git commit -m "$(cat <<'EOF'
Document A/B/C restore checklist and separate AntiZapret archives.

Clarify that full VPN backups are not panel-list entries and mark the coverage spec implemented.
EOF
)"
```

---

### Task 4: Regression verification

**Files:** none (run only)

- [ ] **Step 1: Run backup + portal regression suite**

```bash
cd /opt/AdminPanelAZ && .venv/bin/python -m pytest \
  backend/tests/test_backup_manager.py \
  backend/tests/test_backup_overlays.py \
  backend/tests/test_backup_scheduler.py \
  backend/tests/test_backup_cli.py \
  backend/tests/test_backups_restore_order.py \
  backend/tests/test_backup_portal_restore.py \
  backend/tests/test_awg2_backup.py \
  backend/tests/test_portal_access_path.py \
  backend/tests/test_portal_publish.py \
  backend/tests/test_client_portal.py \
  -q --tb=line
```

Expected: all PASS (0 failed)

- [ ] **Step 2: Frontend typecheck**

```bash
cd /opt/AdminPanelAZ/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Spec coverage self-check**

Confirm against `2026-09-12-backup-restore-coverage-design.md`:
- Gap #1 → Task 1
- Gap #2 → Task 2
- Gap #3 → Task 3
- Out of scope (nginx in tar, auto publish) untouched

If any gap missing, fix before claiming done. No commit unless a fix was needed.

---

## Plan self-review

| Spec item | Task |
|-----------|------|
| Gap #1 Push full API hint | Task 1 |
| Gap #2 upload+restore detail | Task 2 |
| Gap #3 AZ separate + docs A/B/C | Task 3 |
| Verification / tests green | Task 4 |
| No machine-image / no auto publish | Global Constraints |

No TBD/placeholder steps. `BackupEntry.restore_*` names consistent across backend schema, frontend types, and upload handler.
