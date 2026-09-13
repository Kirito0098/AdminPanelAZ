# CIDR / Routing — analysis + P0 fix designs

**Дата:** 2026-09-13  
**Статус:** implemented  
**Ветка:** `feature/client-portal`  
**Подход:** вариант **3** — карта «как есть» + audit + готовые решения **P0** (затем writing-plans); P1 UX точечно после P0

## Контекст

Раздел **Маршрутизация / CIDR** (`/routing`, feature `routing`) — операторский контур списков провайдеров: загрузка в SQLite → сборка `.txt` → выкладка на узел → применение маршрутов.

Недавние инциденты на этой установке:

1. **Akamai −87%** (2026-09-06): `ripe-as20940-geo` → «Пустой результат»; остался только announced (~4k). Anomaly `critical`, но **safe-fallback не сработал**; пул перезаписан.  
2. После ручного recover только Akamai UI показал **«Общий пул CIDR снизился: 32752 против 121539»** — ложный global alert из-за сравнения `total_cidrs` partial-лога с full-логом.  
3. После recover: `anomaly_level=none`, но **`anomaly_reason` всё ещё** «CIDR упали на 87%».

## Цели документа

1. Зафиксировать карту системы (pipeline глубоко; остальные вкладки кратко).  
2. Ranked риски P0–P2.  
3. Спроектировать **P0 фиксы** sufficiently для implementation plan.  
4. Наметить **P1 UX** вокруг тех же мест (не полный redesign).

## Решения brainstorm

| Тема | Выбор |
|------|--------|
| Цель | **C** — карта + audit + backlog |
| Границы | **C** — pipeline глубоко; остальное кратко |
| Приоритет backlog | **C** — сначала корректность данных, затем UX вокруг неё |
| Формат | **3** — analysis + P0 designs в одном spec |

## §1. Карта «как есть»

### UI (`/routing`)

| Вкладка | Роль |
|---------|------|
| Обзор | Сводка, workflow steps, алерты degradation |
| Провайдеры | Enable/disable, custom sources, counts |
| Pipeline | Ingest / compile / deploy / apply tasks |
| Анализ | DPI / проверки |
| Настройки | Schedule, route budget, опции |

Workflow stages (`routingWorkflow.ts`): ingest → compile → deploy → …; флаги `pendingCompile` / `pendingDeploy` сравнивают DB meta vs `compile_artifacts` vs `has_source` на узле.

### Backend pipeline

```
ingest → compile → deploy → apply
```

| Stage | Entry | Effect |
|-------|--------|--------|
| **Ingest** | `run_ingest` → `CidrDbUpdaterService.refresh_all_providers` | Download sources + ASN pool; write `provider_cidr` (`cidr.db`); update `provider_meta` + `cidr_db_refresh_log` (`adminpanel.db`) |
| **Compile** | `run_compile` → `update_cidr_files_from_db` | Geo/RU/antifilter/limits → `data/cidr/list/*.txt` |
| **Deploy** | `run_deploy` / multi-deploy | Push artifacts + `sync_cidr_providers` on node |
| **Apply** | `run_apply` | Wire into routing / OpenVPN hosts |

**Triggers:** cron (`cidr_scheduler`, default ~02:30) or UI `POST /api/routing/cidr-db/refresh` with optional `selected_files` (partial ingest).

**Akamai sources** (`provider_sources.py`):

- `ripe-as20940-geo` (`ripe_geo_json`) — основной объём (~31k)  
- `ripe-as20940-announced` (`ripe_json`) — ~4k  

Healthy merge ≈ unique(geo ∪ announced) ~32–33k.

### Инвариант для оператора

**DB count ≠ file line count ≠ routes on node.**  
Ingest alone does not refresh `list/*.txt`. Compile may shrink further (filters/limits). Deploy/apply are separate.

### Связанные, но кратко

- **Antifilter** — overlap filter at compile.  
- **DPI / Анализ** — separate tab; maps providers for diagnostics.  
- **Route budget** — compile/deploy capacity, not ingest correctness.  
- **Custom providers** — same ingest path via provider registry.

## §2. Риски

### P0 — data / signals

| ID | Issue | Evidence |
|----|--------|----------|
| **P0-1** | Safe-fallback не сохраняет пул при critical drop, если candidate ≥ `CIDR_DB_FALLBACK_MIN_CANDIDATE` (500) и нет ASN-errors | Akamai 32705→3952; geo error не в `asn_errors`; `fallback_applied=false`; `status=ok` |
| **P0-2** | Global degradation alert сравнивает `last_log.total_cidrs` vs `prev_log.total_cidrs` | Partial Akamai-only log `total_cidrs=32752` vs full cron `121539` → false warning; real DB ~150k |
| **P0-3** | `anomaly_reason` не очищается при `anomaly_level=none` | After recover: level none, reason still «CIDR упали на 87%» |

**Side effect of P0-1:** `maybe_notify_ingest_partial` only fires when overall `status=partial`. Provider can stay `ok` while a major direct source failed → weak ops signal.

### P1 — UX around same seams

| ID | Issue |
|----|--------|
| **P1-1** | After ingest-only, easy to confuse «DB restored» with «lists on controller/node updated» |
| **P1-2** | Provider `ok` with failed `source_details` hides partial source failure |
| **P1-3** | Alerts should distinguish DB pool vs controller artifact |

### P2

- Cron vs manual partial interaction / log semantics.  
- Compile shrinking (e.g. ~120 lines on disk) is expected with filters but poorly explained next to DB counts.

## §3. P0 fix designs

### P0-1 — Safe-fallback on critical drop

**File:** `backend/app/services/cidr/pipeline/db_service.py` — `_should_preserve_previous_pool`.

**New rule (in addition to existing):**

If `previous_cidr_count > 0` and

```text
drop_ratio = 1 - candidate/previous  >=  0.5
```

→ **preserve previous pool** (`return True`), **even when** `asn_errors` is empty and `candidate >= CIDR_FALLBACK_MIN_CANDIDATE`.

Rationale: align fallback with existing **critical** anomaly threshold (already 50% in `_compute_provider_anomaly`). A 50%+ shrink is never a «natural small provider» case for large historical pools.

**Optional strengthening (same task if cheap):** treat any direct `source_details` with `status=error` as equivalent to soft failure for provider `status` → prefer `partial` when fallback applied or when a listed source failed while another succeeded.

**When fallback applies:** keep existing behavior (do not replace `provider_cidr`; mark partial/fallback in result; set anomaly accordingly).

**Tests:**

- previous=32705, candidate=3952, asn_errors=[] → fallback **True**.  
- previous=1000, candidate=800 (20% drop) → fallback **False** (unless other rules).  
- previous=400, candidate=350, both &lt; 500, no errors → keep existing small-provider behavior.  
- previous=10000, candidate=0 → True (existing).

### P0-2 — Global alert vs partial logs

**File:** `_build_degradation_alerts`.

**Preferred rule:**

- Compute `current_total` = **sum of `provider_meta.cidr_count`** (already used elsewhere for status overview ~line 795), **not** `last_log.total_cidrs`.  
- Compute `previous_total` for comparison as either:
  - previous full-run baseline stored on meta/log, **or**
  - sum of meta **before** last refresh if available, **or**
  - last log where `providers_updated` equals full catalog size / `triggered_by` cron / no `selected_files` marker.

**Minimal fix (acceptable for P0):**

Skip global drop alert when last log is **partial**:

- `providers_updated <` number of known providers in `PROVIDER_SOURCES`, **or**  
- details indicate subset refresh.

Then global compare only for full refreshes, still using log totals **or** meta sum (meta sum preferred).

**Tests:**

- last log updated 1/12 providers, total_cidrs small, prev log large → **no** global alert if meta sum healthy.  
- full refresh meta/log total drops ≥30% → alert remains.

### P0-3 — Clear anomaly_reason

**File:** `_upsert_provider_meta` / call sites after successful anomaly compute.

When writing `anomaly_level` in `("none", "info")` with empty/new none reason → set `anomaly_reason` to **NULL** (explicit clear), not leave previous string.

**Tests:** meta with stale reason + refresh to healthy counts → reason is NULL.

## §4. P1 UX (after P0)

1. Overview / alerts: if `pendingCompileCount > 0` after recent ingest, show info (not warning): «В SQLite обновлено · N ждут сборки».  
2. Provider row: if any `source_details.status=error` → show warning chip even when merged status ok/partial.  
3. Degradation copy: prefix scope «DB» vs «файл контроллера» where counts are shown.

Out of scope for P1: full tab redesign, DPI, antifilter rewrite.

## Вне скоупа (этот проход)

- New provider sources / RIPE API alternatives.  
- Changing compile route limits or geo filter policy.  
- HA replication of cidr.db.  
- Auto-compile after every ingest (product decision; not required for P0).

## Порядок реализации (высокоуровнево)

1. P0-1 fallback + unit tests.  
2. P0-3 clear reason (tiny, same area).  
3. P0-2 global alert.  
4. Changelog.  
5. Optional follow-up plan for P1 UX.

## Критерии готовности P0

1. Synthetic/regression: ≥50% drop without ASN errors → previous pool preserved + partial/fallback visible.  
2. Partial refresh does not emit false global «пул снизился» when overall meta sum is healthy.  
3. Healthy refresh clears stale `anomaly_reason`.  
4. Existing small-provider / Cloudflare-style pools do not get spurious fallback on tiny absolute sizes without large drop ratio.  
5. Targeted pytest green.

## Testing notes

- Prefer unit tests on `_should_preserve_previous_pool` and `_build_degradation_alerts` (pure / with lightweight meta+log fixtures).  
- Optional integration: dry_run refresh fixture with mocked source_details.
