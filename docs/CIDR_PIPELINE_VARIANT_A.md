# CIDR Pipeline — Вариант A (Controller-centric)

Архитектура, при которой **тяжёлая работа выполняется на контроллере (панели)**, а **ноды только принимают артефакты и применяют AntiZapret**.

## Целевая схема

```
INGEST (панель)     → SQLite: провайдеры, ASN, antifilter
COMPILE (панель)    → backend/data/cidr/list/*.txt
DEPLOY (панель→нода)→ PUT /routing/providers/{file} на node agent
APPLY (нода)        → sync + doall.sh локально
```

### Состояние pipeline

| Этап | API / код | Статус |
|------|-----------|--------|
| INGEST | `POST /api/routing/cidr-db/refresh` | ✅ WAL + retry; алерт `cidr_ingest_partial` |
| COMPILE | `POST /api/routing/cidr-db/generate` | ✅ На контроллере; `artifact_stamp` в result |
| DEPLOY | `POST /api/routing/cidr-db/deploy` | ✅ Push на ноду / мульти-нода / all_online |
| APPLY | `sync_after` / `apply_after` | ✅ На выбранной / active / нескольких нодах |

### Требования (выполнены)

- [x] Один refresh на весь кластер.
- [x] Generate всегда на контроллере.
- [x] Явный deploy: push файлов на выбранную ноду / все online-ноды.
- [x] Apply (doall) — на ноде, где живёт AntiZapret (active / выбранные / all_online).
- [x] UI: три понятных этапа вместо одной неочевидной кнопки.

---

## Фаза 0 — Стабилизация SQLite на контроллере

**Цель:** убрать `database is locked` при создании фоновых задач (блокер для «Обновить из интернета»).

**Файлы:**
- `backend/app/database.py`
- `backend/app/services/background_tasks.py`
- `frontend/src/components/routing/useRoutingPage.ts`

**Реализация:**
- SQLite: `PRAGMA journal_mode=WAL`, `busy_timeout=30000`, connect timeout 30 с.
- Retry commit при `OperationalError "database is locked"` — до 5 попыток.
- В UI показывать `err.message` для `Error`, не только `ApiError`.

**Проверка:**
- [x] Кнопка «Обновить из интернета» не даёт 500.
- [x] В логе нет `database is locked` при refresh.
- [x] `sqlite3 data/adminpanel.db "PRAGMA journal_mode"` → `wal`.

**Статус:** ✅ выполнено

---

## Фаза 1 — Выделение слоёв в коде

**Цель:** формализовать ingest / compile / deploy / apply как отдельные сервисные функции без изменения контрактов API.

**Модули:**
- `backend/app/services/cidr/pipeline/orchestrator.py` — координация этапов
- `backend/app/services/cidr/pipeline/deploy.py` — push артефактов на ноду

**Функции orchestrator:**
- `run_ingest` — обёртка над `refresh_all_providers`
- `run_compile` — обёртка над `update_cidr_files_from_db`
- `run_deploy` — local: sync list→config; remote: push + sync
- `run_apply` — sync + optional doall

**Рефакторинг:**
- `cidr_db.py` — тонкий роутер, вызывает orchestrator
- `update_cidr_files_from_db` остаётся compile
- `CidrDbUpdaterService.refresh_all_providers` остаётся ingest

**Проверка:**
- [x] Все существующие тесты `test_cidr_db_*` проходят.
- [x] Поведение UI не изменилось.

**Статус:** ✅ выполнено

---

## Фаза 2 — Deploy: push артефактов на ноду

**Цель:** после compile файлы с контроллера попадают на `list_dir` целевой ноды.

**Логика deploy (`deploy.py`):**
1. Прочитать сгенерированные файлы из `LIST_DIR` (изменённые или все `.txt`).
2. Для каждого файла: `adapter.save_provider_content(filename, content)`.
3. Вернуть отчёт: `{ pushed, failed, skipped }`.

**Изменения API:**
- `CidrDbGenerateRequest`: `deploy_after`, `target_node_id` (null = active node).
- В `_generate_runner`: после compile → `run_deploy` → `sync_after` / `apply_after`.

**Файлы:**
- `backend/app/services/cidr/pipeline/deploy.py`
- `backend/app/services/cidr/pipeline/orchestrator.py`
- `backend/app/routers/cidr_db.py`
- `frontend/src/types.ts`, `frontend/src/api/client.ts`

**Транспорт:** `RemoteNodeAdapter.save_provider_content` → `PUT /routing/providers/{filename}` (node agent без изменений).

**Проверка:**
- [x] Панель без локального AntiZapret (`LOCAL_ANTIZAPRET_ENABLED=false`), активна удалённая нода.
- [x] Generate + deploy → файлы появляются на ноде в `list_dir`.
- [x] Sync/doall на ноде отрабатывает без «missing_sources».

**Статус:** ✅ выполнено

---

## Фаза 3 — Отдельный endpoint Deploy и UI (три этапа)

**Цель:** разделить операции в интерфейсе: **Обновить БД** | **Собрать файлы** | **Развернуть на ноду**.

**API:**
- `POST /api/routing/cidr-db/deploy` — только deploy (+ опционально sync/apply)
  - body: `{ target_node_id?, sync_after?, apply_after?, selected_files? }`

**UI (`CidrPipelineTab.tsx`):**
- Кнопка 1: «Обновить из интернета» → refresh
- Кнопка 2: «Сгенерировать из БД» → generate с `deploy_after=false`
- Кнопка 3: «Развернуть на ноду» → deploy
- «Сгенерировать + doall» → generate с `deploy_after=true, apply_after=true`

`PipelineStatusBar` показывает последний deploy. Подписи и подсказки — на русском.

**Проверка:**
- [x] Можно обновить БД без генерации.
- [x] Можно сгенерировать без деплоя.
- [x] Можно задеплоить ранее сгенерированные файлы.

**Статус:** ✅ выполнено

---

## Фаза 4 — Мульти-нода и очередь деплоя

**Цель:** деплой не только на active node, а на выбранный набор / все online.

**Модель данных:**
- Поля в `background_task.result`:
  - `artifact_stamp` — hash списка файлов compile
  - `per_node`: `{ node_id, status, pushed_files, error }`

**API:**
- `POST /api/routing/cidr-db/deploy` → `target_node_ids` или `all_online`
- `GET /api/routing/cidr-db/deploy/status` — последний деплой по нодам

**UI:**
- `CidrPipelineTab`: мультиселект нод или «Все online»
- `PipelineTaskProgress`: статус по нодам (успех / ошибка / пропущен)

**Поведение:** итерация по нодам в orchestrator; offline — skip + запись в log; retry для offline — только лог (v1, без фонового воркера).

**Проверка:**
- [x] Деплой на 2+ online-ноды из одной операции.
- [x] Offline-нода в отчёте как skipped/failed, не ломает остальных.

**Статус:** ✅ выполнено

---

## Фаза 5 — Версионирование артефактов и ночной cron

**Цель:** связать ingest → compile → deploy в расписании; хранить «какой compile задеплоен на какую ноду».

**Конфиг (`.env`):**
```env
CIDR_DB_REFRESH_ENABLED=true          # только ingest
CIDR_DB_COMPILE_AFTER_REFRESH=false   # опционально auto-compile
CIDR_DB_DEPLOY_AFTER_COMPILE=false    # опционально auto-deploy
CIDR_DB_DEPLOY_TARGET=active          # active | all_online | node_ids
# CIDR_DB_DEPLOY_TARGET_NODE_IDS=1,2  # при target=node_ids
```

**Файлы:**
- `backend/app/services/cidr/cidr_scheduler.py`
- `backend/app/config.py`
- `backend/.env.example`

**Поведение:** после успешного refresh — опционально compile + deploy; `artifact_stamp` и сводка pipeline в `CidrDbRefreshLog.details_json`.

**Проверка:**
- [x] Ночной cron только refresh при всех флагах false.
- [x] При `COMPILE_AFTER_REFRESH=true` — файлы появляются на контроллере без UI.

**Статус:** ✅ выполнено

---

## Фаза 6 — Наблюдаемость и алерты

**Цель:** админ видит состояние pipeline на дашборде и в Telegram.

**Реализовано:**
- `GET /api/routing/cidr-db/status` — `last_compile_at`, `last_deploy` (per node summary)
- `GET /api/routing/cidr-db/deploy/status` — последний деплой по нодам
- `PipelineStatusBar` — ingest / compile / deploy (время, статус, ноды)
- Telegram: `cidr_deploy_failed`, `cidr_ingest_partial`
- Audit log: `settings_cidr_deploy` при deploy

**Проверка:**
- [x] `GET /api/routing/cidr-db/status`: поля `last_compile_at`, `last_deploy`.
- [x] `GET /api/routing/cidr-db/deploy/status` — последний деплой по нодам.
- [x] `PipelineStatusBar`: ingest / compile / deploy.
- [x] Admin notify: `cidr_deploy_failed`, `cidr_ingest_partial`.
- [x] Audit log: `settings_cidr_deploy` в deploy endpoint.

**Статус:** ✅ выполнено

---

## Сводная таблица фаз

| Фаза | Приоритет | Сложность | Зависимости | Статус |
|------|-----------|-----------|-------------|--------|
| 0 SQLite WAL | P0 | S | — | ✅ |
| 1 Orchestrator | P0 | M | 0 | ✅ |
| 2 Deploy push | P0 | M | 1 | ✅ |
| 3 UI три этапа | P1 | M | 2 | ✅ |
| 4 Мульти-нода | P1 | L | 2, 3 | ✅ |
| 5 Cron | P2 | M | 2 | ✅ |
| 6 Observability | P2 | M | 3–4 | ✅ |

---

## Регрессия и интеграция

**Backend-тесты:**
```bash
cd backend && .venv/bin/pytest \
  tests/test_cidr_db_updater_service.py \
  tests/test_background_tasks_service.py \
  tests/test_cidr_pipeline_orchestrator.py \
  tests/test_cidr_pipeline_deploy.py \
  tests/test_cidr_db_deploy.py \
  tests/test_cidr_multi_deploy.py \
  tests/test_cidr_scheduler.py \
  tests/test_cidr_notify.py \
  -q
```

**Сценарий на стенде** (панель без локального AntiZapret, одна remote node):
1. `refresh` — обновить БД
2. `generate` с `deploy_after=false` — собрать файлы на контроллере
3. `deploy` с `apply_after=true` — развернуть и применить на ноде

Убедиться, что CIDR в routing overview на ноде обновились.

---

## Риски и ограничения

| Риск | Митигация |
|------|-----------|
| Большие файлы при push на медленный канал | Сжатие gzip в node agent (отдельная задача, не v1) |
| Расхождение preset enabled на нодах | Deploy пушит только list; enable/sync — отдельный шаг или sync_after |
| Долгий compile блокирует API | Background task — сохранено |
| Конфликт ручного редактирования provider на ноде | Deploy перезаписывает list_dir; предупреждение в UI |
| «Сгенерировать + doall» | Деплой на active node, без учёта выбора нод в UI deploy |

---

## Связанные файлы

| Компонент | Путь |
|-----------|------|
| Ingest service | `backend/app/services/cidr/pipeline/db_service.py` |
| Compile pipeline | `backend/app/services/cidr/pipeline/db_pipeline.py` |
| Orchestrator | `backend/app/services/cidr/pipeline/orchestrator.py` |
| Deploy push | `backend/app/services/cidr/pipeline/deploy.py` |
| API роутер | `backend/app/routers/cidr_db.py` |
| Node adapter | `backend/app/services/node_adapter.py` |
| Node agent routing | `backend/node_agent/main.py` |
| Scheduler | `backend/app/services/cidr/cidr_scheduler.py` |
| Уведомления | `backend/app/services/cidr/cidr_notify.py` |
| UI pipeline | `frontend/src/components/routing/CidrPipelineTab.tsx` |
| Status bar | `frontend/src/components/routing/PipelineStatusBar.tsx` |
| Hook | `frontend/src/components/routing/useRoutingPage.ts` |
| LIST_DIR | `backend/app/services/cidr/pipeline/constants.py` |

---

*Вариант A — Controller-centric CIDR pipeline. Фазы 0–6 выполнены (июнь 2026).*
