# Промпты и режимы запуска по этапам

> Готовые промпты для Cursor / AI-агента при реализации [Idei.md](Idei.md).  
> Перед стартом прочитай [PROJECT_MAP.md](PROJECT_MAP.md).

---

## Статус реализации (2026-06-16)

Сверка с кодовой базой. Легенда: **✅** готово · **◐** частично · **⬜** не начато.

| Этап | Название | Статус | Комментарий |
|------|----------|--------|-------------|
| **1** | Prod foundation | ✅ | Все 1.1–1.8; промпты — для доработок/regression |
| **2** | Admin productivity | ✅ | Теги, шаблоны, bulk, AWG tab, сессии |
| **3** | Multi-node обзор | ✅ | 3.4 per-node wizard — ✅ |
| **4** | CIDR безопасность | ✅ | dry-run, rollback, custom provider |
| **5** | Node Sync / HA | ✅ | MVP + v2 + NOC HA-агрегация |
| **6** | Self-service | ✅ | web + TG + reminders |
| **7** | Мониторинг и алерты | ✅ | GeoIP onboarding, alert rules, PDF weekly |
| **8** | Ops и интеграции | ✅ | runbook, CSV, rolling update, OpenAPI, webhooks, mini app |
| **9** | Security / enterprise | ✅ | passkeys, audit, CSP, secrets rotation |
| **10** | Масштаб | ◐ | i18n бота ◐; PG ⬜; plugin + inline ✅ |

**Что делать дальше (по приоритету backlog):** см. **[Backlog-otkryto.md](Backlog-otkryto.md)** — 10.1 · 10.2

---

## Как пользоваться

1. Выбери **этап** в [Idei.md § Этапы](Idei.md#этапы-реализации-roadmap).
2. Проверь **зависимости** (предыдущий этап закрыт по DoD).
3. Запусти **режим подготовки** (Ask / Plan) — промпт «Подготовка».
4. Переключись в **Agent** — промпт «Реализация» (или по подзадачам).
5. Выполни **проверку** — блок «Запуск и проверка».
6. Отметь DoD в Idei.md.

---

## Режимы Cursor

| Режим | Когда | Что просить |
|-------|--------|-------------|
| **Ask** | Перед этапом | Изучить код, зависимости, риски; без правок |
| **Plan** | Этапы 5, 10, большие фичи | Архитектура, файлы, API, порядок PR |
| **Agent** | Основная реализация | Код, тесты, минимальный diff |
| **Debug** | Падают тесты / CI | Только фикс конкретной ошибки |

**Правила для Agent (добавляй в конец любого промпта):**

```
Контекст: проект AdminPanelAZ (/opt/AdminPanelAZ).
Стек: FastAPI + SQLAlchemy (backend), React + Vite + TS (frontend).
Следуй conventions из PROJECT_MAP.md и существующему коду.
Минимальный diff; не рефактори unrelated.
Добавь pytest для backend; при UI — vitest если этап требует.
Не коммить без явной просьбы.
```

---

## Общий запуск dev-окружения

```bash
cd /opt/AdminPanelAZ
./start.sh                    # backend :8000 + frontend :5173
# или только backend:
cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Тесты:**

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/pytest tests/ -q
cd /opt/AdminPanelAZ/frontend && npm run lint && npm run build
```

**CI локально:** см. `.github/workflows/ci.yml`

---

# Этап 1 — Prod foundation · ✅ **реализовано**

**Зависимости:** нет  
**Режим:** Ask → Agent (подзадачи можно параллелить)  
**DoD:** [Idei.md § Этап 1](Idei.md#этап-1--prod-foundation) — закрыт  

> Промпты ниже — для повторной реализации, регрессии или расширения. Ключевые файлы: `retention_worker.py`, `prometheus_metrics.py`, `health_checks.py`, `FeatureTogglesTab`, `test_feature_profiles.py`, Vitest в CI.

### Подготовка (Ask)

```
Изучи AdminPanelAZ для Этапа 1 (Prod foundation):
- background workers в backend/app/main.py lifespan
- GET /api/health
- background_tasks, traffic worker, panel_resource_metrics
- frontend MonitoringPage, TrafficPage, RoutingPage (route budget metadata)
- install.sh health check, config.py (redis, retention-related settings)
- feature_toggles.py, FeatureTogglesTab — что уже можно выключить
- какие asyncio-task в lifespan стартуют **без** проверки toggles (gap для 1.8)

Верни: что уже есть для задач 1.1–1.8, чего не хватает, рекомендуемый порядок файлов.
Без изменений кода.
```

### Реализация — весь этап (Agent)

```
Реализуй Этап 1 Prod foundation для AdminPanelAZ (см. docs/Idei.md):

1.1 Retention policies — worker + настройки (env/UI): purge UserTrafficSample, 
    action logs, node/panel resource samples старше N дней; batch DELETE.
1.2 Prometheus GET /metrics — gauges: traffic_collector_lag, node_health, 
    без high-cardinality labels (без имён клиентов).
1.3 Redis в prod — документация в README/install + проверка api/auth rate limit 
    при REDIS_URL; комментарий для UVICORN_WORKERS>1.
1.4 Extended health — GET /api/health (лёгкий) + GET /api/health/deep 
    (БД, cidr db, optional active node ping); install.sh может использовать deep.
1.5 Route budget dashboard UI на Routing/CIDR — данные из последнего pipeline estimate.
1.6 NOC → Traffic — клик по клиенту в MonitoringConnectionsList → /traffic?client=...
1.7 Vitest baseline — configCardUtils, buildLightDiff; npm test в CI.
1.8 Resource profiles — пресеты Minimal / Standard / Full; lifespan стартует workers
    только если feature включён; UI impact + «нужен restart»; install wizard для 1 GB panel-only.
    См. docs/Idei.md §2 Resource profiles и §11 VDS.

Тесты pytest для 1.1, 1.2, 1.4, 1.8. DoD из Idei.md.
```

### Подзадачи (Agent, по одной)

| ID | Промпт |
|----|--------|
| **1.1** | `Добавь retention policies: фоновый worker, settings в config.py, опционально UI в Settings → Maintenance. Batch delete для traffic samples и user_action_logs. pytest test_retention_policies.py` |
| **1.2** | `Добавь prometheus_client и GET /metrics (или /api/metrics) с базовыми метриками панели. pytest.` |
| **1.3** | `Обнови install.sh и docs: Redis для prod при workers>1; AUTH_RATE_LIMIT_BACKEND=redis.` |
| **1.4** | `Расширь /api/health: deep check SQLite, cidr db, last traffic sync timestamp.` |
| **1.5** | `UI route budget на странице маршрутизации — осталось N из M маршрутов OpenVPN.` |
| **1.6** | `Ссылка из NOC monitoring list на TrafficPage с query client=` |
| **1.7** | `Настрой Vitest во frontend, 2–3 теста utils, script test в package.json, CI step.` |
| **1.8** | `Resource profiles: Minimal/Standard/Full в feature_toggles + API apply-profile; main.py lifespan — не стартовать task если модуль off; FeatureTogglesTab — пресеты и impact; install.sh — выбор «1 GB panel-only». pytest test_feature_profiles.py. См. Idei.md §2, §11.` |

### Resource profiles — отдельно (Plan → Agent)

**Когда:** VDS 1 GB только под панель, или нужно снизить фоновую нагрузку без отказа от Full на других инсталляциях.

**Plan (перед 1.8):**

```
Спланируй задачу 1.8 Resource profiles для AdminPanelAZ:
- прочитай feature_toggles.py, main.py lifespan, workers (traffic, cidr, backup, health…)
- таблица: worker → env/toggle → включается в Minimal / Standard / Full
- API: POST apply-profile, GET current profile + requires_restart
- UI: блок в FeatureTogglesTab, честный impact (RAM vs CPU/disk)
- install.sh: шаг «тип VDS» → preset

Верни: список файлов, порядок PR, риски (забытый worker, partial apply без restart).
Без кода.
```

**Agent (реализация 1.8):**

```
Реализуй 1.8 Resource profiles (docs/Idei.md §2, §11):
1. PROFILE_PRESETS в feature_toggles — minimal отключает traffic_sync, resource_metrics,
   panel metrics, CIDR scheduler, TG webhook (если не нужен), опрос всех узлов каждые 60s.
2. lifespan: каждый background task обёрнут в проверку toggle/env.
3. POST /api/feature-toggles/apply-profile?profile=minimal|standard|full
4. UI: кнопки пресетов, summary savings, banner «перезапустите панель».
5. README/install: таблица VDS 1 GB panel-only vs 2 GB Full; combo panel+VPN на 1 GB — не рекомендуется.

pytest: apply minimal → toggles off; mock lifespan не создаёт traffic task.
```

### Запуск и проверка

```bash
curl -s http://127.0.0.1:8000/api/health | jq .
curl -s http://127.0.0.1:8000/api/health/deep | jq .
curl -s http://127.0.0.1:8000/metrics | head   # или /api/metrics — как реализовано
cd backend && .venv/bin/pytest tests/ -q -k "retention or health or metrics or feature_profile"
cd frontend && npm test -- --run
# 1.8: после apply minimal + restart панели
curl -s -X POST "http://127.0.0.1:8000/api/feature-toggles/apply-profile?profile=minimal" -H "Authorization: Bearer <token>" | jq .
curl -s http://127.0.0.1:8000/api/feature-toggles | jq '.[] | select(.enabled==false) | .key' | head
```

---

# Этап 2 — Admin productivity · ✅ **реализовано**

**Зависимости:** Этап 1  
**Режим:** Plan (теги + mass ops) → Agent  
**DoD:** [Idei.md § Этап 2](Idei.md#этап-2--admin-productivity) — закрыт  

> Файлы: `config-tags` router, `client_templates`, `bulk_config_ops.py`, `ConfigCardsSection` (AWG tab), `SecurityTab` (sessions). Тесты: `test_stage2_admin_productivity.py`.

### Подготовка (Plan)

```
Спланируй Этап 2 Admin productivity для AdminPanelAZ:
- модель тегов для VpnConfig (или отдельная таблица)
- шаблоны клиентов (AppSetting vs новая модель)
- mass ops через background_tasks (как CIDR pipeline)
- ActiveWebSession API + UI
- AmneziaWG tab на Dashboard (feature toggle amneziawg)

Выдай: модели, роутеры, frontend страницы, порядок PR 2.1→2.3.
```

### Реализация (Agent)

```
Реализуй Этап 2 Admin productivity:

2.1 Теги/группы на VpnConfig — CRUD, фильтр на Dashboard.
2.2 Шаблоны клиентов — пресеты OVPN/WG (cert days, traffic limit) — one-click create.
2.3 Mass ops — выбор по тегу/чекбоксам: block, delete, renew cert; 
    background task + BackgroundTaskProgress UI; лимит параллелизма к node agent.
2.4 Отдельная вкладка AmneziaWG в ConfigCardsSection.
2.5 UI управления ActiveWebSession — list + revoke для admin.

Reuse: background_tasks.py, ProgressContext, client_access routers.
pytest + минимальные frontend изменения.
```

### Запуск и проверка

```bash
cd backend && .venv/bin/pytest tests/ -q -k "tag or template or session or bulk"
# UI: Dashboard → теги, mass select, AmneziaWG tab
# Settings или Security → активные сессии
```

---

# Этап 3 — Multi-node обзор · ✅ **реализовано**

**Зависимости:** Этап 1; желательно Этап 2  
**Режим:** Ask → Agent  
**DoD:** [Idei.md § Этап 3](Idei.md#этап-3--multi-node-обзор) — закрыт  

> ✅ **3.4:** `NodePolicyWizard`, `NodePolicySummarySection` — per-node policy edit wizard.

### Подготовка (Ask)

```
Как в AdminPanelAZ работает multi-node сегодня?
- monitoring overview scope=all
- node_remote_cache, get_cached_monitoring_overview
- NodesPage, NodeContext

Что нужно для Global dashboard (3.1) без N+1 запросов с фронта?
```

### Реализация (Agent)

```
Этап 3 Multi-node обзор:

3.1 Global dashboard — новая страница или секция на Dashboard/Monitoring:
    сводка online OVPN/WG, health, CPU по всем узлам; backend aggregate endpoint;
    кэш 30–60с (node_remote_cache).
3.2 (optional) Compare nodes — таблица side-by-side метрик.
3.3 (optional) Geo-routing hint при выдаче конфига — ip_geo + список nodes.
3.4 (optional) Per-node policy overrides в WgAccessPolicy/OpenVpnAccessPolicy.

Приоритет: 3.1 полностью, остальное если время.
```

### Запуск и проверка

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/monitoring/overview?scope=all' | jq .
# UI: 2+ узла в Nodes → global view без switch active node
cd backend && .venv/bin/pytest tests/ -q -k "monitoring_overview or node"
```

---

# Этап 4 — CIDR безопасность · ✅ **реализовано**

**Зависимости:** Этап 1 (route budget)  
**Режим:** Agent  
**DoD:** [Idei.md § Этап 4](Idei.md#этап-4--cidr-безопасность) — закрыт  

> Файлы: `deploy_preview.py`, rollback API, `CustomProviderWizardDialog`, `test_cidr_stage4.py`.

### Реализация (Agent)

```
Этап 4 CIDR безопасность для AdminPanelAZ:

4.1 Dry-run diff перед deploy — API + UI preview: файлы, route count, 
    diff vs текущее на узле; без apply.
4.2 Rollback CIDR deploy из runtime_backups — one-click с ConfirmDialog;
    background task; action_log + admin_notify при fail.
4.3 (optional) Custom provider wizard — UI добавления ASN/CIDR в cidr db.

Опирайся на services/cidr/pipeline/, usePipelineTaskPoll, file_pipeline rollback.
pytest test_cidr_* patterns.
```

### Запуск и проверка

```bash
cd backend && .venv/bin/pytest tests/ -q -k "cidr_pipeline or cidr_db_deploy"
# UI: Routing → pipeline → dry-run → deploy → rollback test на staging node
```

---

# Этап 5 — Node Sync / HA · ✅ **реализовано**

**Зависимости:** Этап 1; желательно Этап 3  
**Режим:** Plan (обязательно) → Agent по подзадачам 5.1→5.3  
**DoD MVP:** закрыт · **DoD v2:** закрыт (включая NOC HA-агрегацию)  

> ✅ MVP + v2 + 5.6: [`NodeSync.md`](NodeSync.md), `services/node_sync/*`, `NodeSyncGroupSection`, federated NOC по sync group.

### Подготовка (Plan)

```
Спланируй Node Sync / HA для AdminPanelAZ (AntiZapret failover):

Сценарий: один домен, 2 IP, client.sh 8 backup на primary, restore на replica.
Уже есть: create_antizapret_backup, node_adapter, background_tasks.

Нужно: NodeSyncGroup model, API, node agent restore endpoint, 
verify parity, UI на NodesPage.

AntiZapret: /root/antizapret, easyrsa3, wireguard keys must match.

Выдай: схема БД, API endpoints, sequence diagram push-full, риски split-brain.
```

### Реализация MVP (Agent)

```
Этап 5 MVP (5.1–5.3) Node Sync HA:

5.1 Модель NodeSyncGroup (primary_node_id, replica_node_ids JSON, shared_domain, 
    sync_mode). CRUD API /api/nodes/sync-groups. UI на NodesPage.
5.2 POST .../push-full: create_antizapret_backup на primary → upload/stream → 
    restore на replica(s); background_tasks + progress; node agent POST restore.
5.3 POST .../verify: compare list_openvpn_clients, list_wireguard_clients, 
    checksums PKI/wg; отчёт ready | mismatches[].

Не делай 5.4–5.6 в этом PR. pytest test_node_sync*.py. Документ docs/NodeSync.md кратко.
```

### Промпт — доработка 5.6 (NOC HA)

```
AdminPanelAZ: NOC federated overview должен агрегировать online клиентов по NodeSyncGroup
(одна строка на HA logical client, badge domain + node count).
Опирайся на ha_primary_config_id / sync_group_id. pytest + минимальный UI diff.
```

### Реализация v2 (Agent, отдельный PR) — ✅ уже в коде

```
Этап 5 v2 реализован: client_sync, reconcile_worker, HA badge на ConfigCard.
Пропусти, если не нужны доработки. См. docs/NodeSync.md § v2.
```

### Запуск и проверка

```bash
# 2 тестовых узла или local + remote agent
cd backend && .venv/bin/pytest tests/ -q -k "node_sync or antizapret_backup"
# UI: Nodes → Create Sync Group → Push full → Verify → статус synced
```

---

# Этап 6 — Self-service · ✅ **реализовано**

**Зависимости:** Этап 2  
**Режим:** Agent  
**DoD:** [Idei.md § Этап 6](Idei.md#этап-6--self-service) — закрыт  

> `self_service.py`, TG `/myconfigs` `/traffic`, `user_reminder_worker.py`, `test_self_service.py`.

### Реализация (Agent)

```
Этап 6 Self-service:

6.1 role=user: create config (quota N), download own profiles, view own traffic;
    guards в configs router; UI limits on Dashboard.
6.2 Telegram bot: /myconfigs, /traffic для linked user (не admin-only handlers).
6.3 Worker напоминаний: cert expiry, traffic limit, temp block → AdminNotify/TG user;
    dedup 1 раз в 24ч на event.

Согласуй с tg_mini и FeatureModules. pytest.
```

### Запуск и проверка

```bash
cd backend && .venv/bin/pytest tests/ -q -k "telegram or tg_mini or traffic_limit"
# Login as user role → create config → limit enforced
# Bot: /myconfigs от привязанного telegram_id
```

---

# Этап 7 — Мониторинг и алерты · ✅ **реализовано**

**Зависимости:** Этап 1  
**Режим:** Agent  
**DoD:** [Idei.md § Этап 7](Idei.md#этап-7--мониторинг-и-алерты) — закрыт  

> ✅ **7.1** GeoIP onboarding · **7.2** `noc_report_scheduler.py` · **7.3** alert rules · **7.4** PDF weekly reports

### Промпт — доработка 7.1 (MMDB onboarding)

```
Добавь в README/docs инструкцию загрузки GeoLite2 City+ASN в data/geoip/;
опционально — кнопка/статус в Settings → Maintenance «GeoIP: loaded / fallback ip-api».
Не меняй логику lookup, только UX и документацию.
```

### Промпт — реализация 7.3 (alert rules)

```
Реализуй правила алертов AdminPanelAZ (Idei.md 7.3):
- модель AlertRule (порог, метрика/агрегат, cooldown)
- worker поверх prometheus_metrics / DB aggregates
- AdminNotify при срабатывании
- UI в Settings → Monitoring (admin only)
pytest test_alert_rules.py
```

### Реализация (Agent)

```
Этап 7 Мониторинг и алерты:

7.1 Локальная GeoIP — MaxMind MMDB или аналог; заменить/fallback ip_geo.py; 
    без внешних запросов если db loaded.
7.2 Scheduled TG reports — cron worker: daily/weekly NOC summary для admin telegram_id.
7.3 (optional) Alert rules engine — пороги поверх metrics/DB; AdminNotify.
7.4 (optional) PDF/weekly report.

Приоритет 7.1 + 7.2. pytest test_ip_geo extended.
```

### Запуск и проверка

```bash
# Отключить интернет или mock ip-api → NOC всё ещё показывает geo
cd backend && .venv/bin/pytest tests/ -q -k "ip_geo or admin_notify"
```

---

# Этап 8 — Ops и интеграции · ✅ **реализовано**

**Зависимости:** Этапы 1–4  
**Режим:** Agent (задачи независимы — отдельные PR)  
**DoD:** [Idei.md § Этап 8](Idei.md#этап-8--ops-и-интеграции) — закрыт  

> Runbook, CSV, rolling update, OpenAPI gate, webhooks, tg-mini Warper/CIDR — в коде и тестах.

### Промпты по задачам

| ID | Промпт |
|----|--------|
| **8.1** | `Runbook UI: обёртка site-diagnostics-cli в Settings → guided steps с результатами JSON.` |
| **8.2** | `Import/export CSV клиентов — background import, export GET; admin only.` |
| **8.3** | `Rolling node update — очередь node_update на нескольких узлах, progress.` |
| **8.4** | `OpenAPI /docs за admin auth или IP whitelist; SECURITY.md update.` |
| **8.5** | `Event webhooks: config on UserActionLog events, async POST retry queue.` |
| **8.6** | `TG Mini App read-only pages: warper status + cidr deploy status.` |

### Запуск и проверка

```bash
cd backend && .venv/bin/pytest tests/ -q -k "site_diagnostics or backup or webhook"
./scripts/site-diagnostics.sh
```

---

# Этап 9 — Security / enterprise · ✅ **реализовано**

**Зависимости:** Этап 1; перед публичным prod  
**Режим:** Plan (CSP) → Agent  
**DoD:** [Idei.md § Этап 9](Idei.md#этап-9--security--enterprise) — закрыт  

> ✅ passkeys, audit SIEM, CSP hardening, secrets rotation wizard

### Промпт — доработка 9.1 (CSP styles)

```
Убери style-src 'unsafe-inline' где возможно (AdminPanelAZ):
- audit inline styles в frontend
- CSS modules / Tailwind без runtime inline где feasible
- сохрани nonce для scripts
pytest test_http_security.py
```

### Реализация (Agent)

```
Этап 9 Security enterprise (по частям):

9.1 CSP nonce — HttpSecurityMiddleware + Vite inject nonce; убрать unsafe-inline где возможно.
9.2 WebAuthn passkeys — register/login flow alongside TOTP; schemas + router.
9.3 Audit SIEM — optional syslog/HTTP stream from UserActionLog.
9.4 (optional) Secrets rotation wizard UI.

Security review mindset; pytest test_security test_http_security.
```

### Запуск и проверка

```bash
cd backend && .venv/bin/pytest tests/ -q -k "security or http_security"
# curl -I https://panel/ → Content-Security-Policy header
# Login passkey flow manual
```

---

# Этап 10 — Масштаб · ◐ **частично** (i18n бота ◐, PG ⬜)

**Зависимости:** метрики SQLite bottleneck  
**Режим:** Plan (обязательно для 10.1) → Agent  
**DoD:** [Idei.md § Этап 10](Idei.md#этап-10--масштаб-и-экосистема) — частично  

> ⬜ PostgreSQL · ◐ `telegram_bot_i18n.py` без веб-locale · ✅ plugin registry · ✅ inline bot

### Подготовка (Plan)

```
Спланируй миграцию AdminPanelAZ SQLite → PostgreSQL:
- database_url, cidr_database отдельно?
- sqlalchemy migrations, docker-compose optional
- backward compat dev on sqlite

И i18n strategy: react-i18next + telegram_bot_i18n structure.
```

### Реализация (Agent)

```
Этап 10 (выбери подзадачу явно):

10.1 PostgreSQL support — config, docs, test job; keep sqlite default dev.
10.2 i18n RU+EN — frontend keys + bot dictionary switch by user locale.
10.3 Plugin hooks — minimal registry for notify backends (не over-engineer).
10.4 Telegram inline mode — inline query handler для config links.

Одна подзадача за PR.
```

### Запуск и проверка

```bash
# PG: DATABASE_URL=postgresql://... pytest
# i18n: npm run build && toggle locale in UI
```

---

## Альтернативные треки — стартовые промпты

### Трек «1 GB panel only» (много VDS 1/1)

```
Инфраструктура: панель AdminPanelAZ на VDS 1 GB (panel-only), VPN-узлы AntiZapret — отдельные VDS 1/1.
Реализуй Этап 1 с фокусом на 1.8 Resource profiles (Minimal) + минимум 1.1–1.4 для prod.
Пропусти или отложи 1.5–1.7 если сроки жмут; Full profile — только на 2 GB при росте.
См. docs/Idei.md §11 и docs/Etapy-prompty.md «Resource profiles».
После Этапа 1 → Этап 2 (admin productivity); этапы 3, 5 — когда узлов >3 или нужен HA.
```

### Трек «HA first» (2 IP, один домен)

```
Пропусти этапы 2–4. Реализуй только Этап 5 MVP (Node Sync HA) для AdminPanelAZ 
после минимального Этапа 1 (background_tasks + health). 
См. docs/Idei.md §10 и docs/Etapy-prompty.md Этап 5.
```

### Трек «Один сервер»

```
Реализуй Этапы 1 → 2 → 4 → 6 по docs/Idei.md. 
Пропусти этапы 3 и 5 (multi-node HA не нужен).
```

### Трек «Публичный prod»

```
После Этапа 1 сразу Этап 9.1 CSP + 9.2 WebAuthn. 
Затем Этап 2. SECURITY.md и README обновить.
```

---

## Промпт для code review после этапа

**Режим:** Ask или Agent (review-only)

```
Review изменений Этапа N AdminPanelAZ:
- соответствие DoD из docs/Idei.md
- perf: фоновые задачи для тяжёлых ops, нет N+1, нет high-cardinality metrics
- security: admin-only, rate limits, action_log
- tests: pytest покрывает happy path + одну ошибку

Список блокеров и minor suggestions. Без новых фич.
```

---

## Промпт для фикса CI (Debug)

```
CI упал после Этапа N. Лог: <вставь вывод>.
Исправь минимальным diff. Запусти локально:
cd backend && .venv/bin/pytest tests/ -q
cd frontend && npm run lint && npm run build
```

---

## Связанные файлы

| Файл | Назначение |
|------|------------|
| [Idei.md](Idei.md) | Этапы, DoD, детали идей, [§11 VDS](Idei.md#11-vds-и-размещение) |
| [Backlog-otkryto.md](Backlog-otkryto.md) | **Открытый backlog** — только ◐ и ⬜ |
| [PROJECT_MAP.md](PROJECT_MAP.md) | Архитектура, пути к коду |
| [Telegram.md](Telegram.md) | Этапы 6, 7, 8.6 |
| [SECURITY.md](../SECURITY.md) | Этап 9 |

---

*Обновляй промпты после реализации этапа: статус в [Idei.md](Idei.md) и таблице «Статус реализации» выше.*
