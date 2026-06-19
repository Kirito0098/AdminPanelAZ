# Карта проекта AdminPanelAZ

> Справочник для навигации по кодовой базе. Обновлять при значительных архитектурных изменениях.

**AdminPanel AntiZapret** — веб-панель для администрирования VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN): клиенты (OpenVPN / WireGuard / AmneziaWG), маршрутизация CIDR, мониторинг, бэкапы, Telegram-бот и Mini App.

**Пользовательские инструкции** (без жаргона, для админов и клиентов VPN): [`docs/README.md`](README.md).

---

## Общая архитектура

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐
│  Web UI     │  │ TG Mini App  │  │ TG Bot      │
│  (React)    │  │ (React)      │  │ (webhook)   │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘
       │                │                 │
       └────────────────┼─────────────────┘
                        ▼
              ┌─────────────────┐
              │ Nginx / proxy   │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ FastAPI :8000   │
              │ backend/app/    │
              └────────┬────────┘
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   adminpanel.db   cidr.db    Background workers
         │             │             │
         └─────────────┴─────────────┘
                       ▼
         ┌─────────────────────────────┐
         │ VPN-узлы (Node)             │
         │ Local: AntiZapret на месте  │
         │ Remote: node agent :9100    │
         └─────────────────────────────┘
```

| Слой | Стек | Точка входа |
|------|------|-------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic | `backend/app/main.py` |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui | `frontend/src/main.tsx` |
| TG Mini App | Отдельная сборка Vite (`mode=tg-mini`) | `frontend/src/tg-mini/main.tsx` |
| БД | SQLite (основная + отдельная CIDR) | `backend/app/database.py`, `cidr_database.py` |
| Деплой | `install.sh`, `start.sh`, systemd | `/opt/AdminPanelAZ` |

---

## Структура каталогов

```
/opt/AdminPanelAZ/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, роутеры, middleware
│   │   ├── config.py            # Settings (.env)
│   │   ├── models.py            # SQLAlchemy модели (основная БД)
│   │   ├── cidr_models.py       # CIDR-модели (отдельная БД)
│   │   ├── schemas.py           # Pydantic-схемы API
│   │   ├── database.py          # engine, миграции основной БД
│   │   ├── cidr_database.py     # engine CIDR БД
│   │   ├── routers/             # HTTP API (26 роутеров)
│   │   ├── services/            # бизнес-логика (~140 файлов)
│   │   ├── middleware/          # rate limit, security, sessions
│   │   └── static/tg_mini/      # собранный Mini App
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # маршруты веб-панели
│   │   ├── pages/               # страницы
│   │   ├── components/          # UI по доменам
│   │   ├── context/             # Auth, Theme, Nodes, Features…
│   │   ├── api/client.ts        # единый HTTP-клиент (~1200 строк)
│   │   └── tg-mini/             # Mini App (отдельное SPA)
│   └── vite.config.ts           # две сборки: default + tg-mini
├── scripts/                     # firewall, install-wizard, uninstall
├── docs/
│   ├── README.md                # оглавление пользовательских руководств
│   ├── konfiguracii.md          # UI: Конфигурации
│   ├── noc-monitoring.md
│   ├── traffic-monitoring.md
│   ├── routing-cidr.md
│   ├── antizapret-config.md
│   ├── warper.md
│   ├── edit-files.md
│   ├── logs.md
│   ├── server-monitor.md
│   ├── uzly.md
│   ├── nastrojki/               # инструкции по подразделам Настроек
│   │   ├── README.md
│   │   ├── profil.md … diagnostika.md
│   ├── Telegram.md              # Telegram (пользователь + setup)
│   ├── GeoIP.md                 # локальная GeoIP (MaxMind)
│   ├── NodeSync.md              # HA / sync groups (разработчик)
│   └── PROJECT_MAP.md           # этот файл
├── install.sh / start.sh
└── .runtime/                    # логи, PID (dev)
```

---

## Документация

| Аудитория | Точка входа | Содержание |
|-----------|-------------|------------|
| **Пользователь / админ VPN** | [`docs/README.md`](README.md) | Простые инструкции по каждому разделу меню и настройкам |
| **Разработчик** | этот файл | Архитектура, роутеры, сервисы, модели |
| **Безопасность (ops)** | [`SECURITY.md`](../SECURITY.md) | HTTPS, 2FA, rate limit, Redis |
| **Установка** | [`README.md`](../README.md) | install.sh, первый запуск |

### UI ↔ пользовательская инструкция

| Маршрут | Страница | User doc |
|---------|----------|----------|
| `/` | `DashboardPage` | [`konfiguracii.md`](konfiguracii.md) |
| `/monitoring` | `MonitoringPage` | [`noc-monitoring.md`](noc-monitoring.md) |
| `/traffic` | `TrafficPage` | [`traffic-monitoring.md`](traffic-monitoring.md) |
| `/routing` | `RoutingPage` | [`routing-cidr.md`](routing-cidr.md) |
| `/antizapret` | `AntizapretConfigPage` | [`antizapret-config.md`](antizapret-config.md) |
| `/warper` | `WarperPage` | [`warper.md`](warper.md) |
| `/telegram` | `TelegramPage` | [`Telegram.md`](Telegram.md) |
| `/edit-files` | `EditFilesPage` | [`edit-files.md`](edit-files.md) |
| `/logs` | `LogsPage` | [`logs.md`](logs.md) |
| `/server-monitor` | `ServerMonitorPage` | [`server-monitor.md`](server-monitor.md) |
| `/nodes` | `NodesPage` | [`uzly.md`](uzly.md) |
| `/settings` | `SettingsPage` | [`nastrojki/README.md`](nastrojki/README.md) |
| `/login` | `LoginPage` | [`nastrojki/profil.md`](nastrojki/profil.md) (2FA, passkey) |

### Настройки: UI ↔ компонент ↔ user doc

| `SettingsSection` | Компонент | User doc |
|-------------------|-----------|----------|
| `personal` | `PersonalTab`, `TwoFactorTab`, `PasskeysTab` | [`nastrojki/profil.md`](nastrojki/profil.md) |
| `users` | `UsersTab` | [`nastrojki/polzovateli.md`](nastrojki/polzovateli.md) |
| `security` | `SecurityTab`, `SecretsRotationWizard` | [`nastrojki/bezopasnost.md`](nastrojki/bezopasnost.md) |
| `config_delivery` | `ConfigDeliveryTab` | [`nastrojki/razdacha-konfigov.md`](nastrojki/razdacha-konfigov.md) |
| `maintenance` | `MaintenanceTab` | [`nastrojki/obsluzhivanie.md`](nastrojki/obsluzhivanie.md) |
| `vpn_network` | `VpnNetworkTab` | [`nastrojki/set-i-publikaciya.md`](nastrojki/set-i-publikaciya.md) |
| `backup` | `BackupTab` | [`nastrojki/rezervnye-kopii.md`](nastrojki/rezervnye-kopii.md) |
| `monitoring` | `MonitoringTab`, `AlertRulesCard` | [`nastrojki/monitoring-i-alerty.md`](nastrojki/monitoring-i-alerty.md) |
| `modules` | `FeatureTogglesTab` | [`nastrojki/moduli.md`](nastrojki/moduli.md) |
| `updates` | `UpdatesTab` | [`nastrojki/obnovleniya.md`](nastrojki/obnovleniya.md) |
| `tests` | `RunbookTab` | [`nastrojki/diagnostika.md`](nastrojki/diagnostika.md) |

---

## Frontend: страницы ↔ API

| Маршрут | Страница | Feature toggle | User doc | Назначение |
|---------|----------|----------------|----------|------------|
| `/` | `DashboardPage` | — | [konfiguracii](konfiguracii.md) | VPN-клиенты, карточки конфигов |
| `/monitoring` | `MonitoringPage` | `logs_dashboard` | [noc-monitoring](noc-monitoring.md) | NOC: подключения, графики, службы |
| `/traffic` | `TrafficPage` | `traffic_sync` | [traffic-monitoring](traffic-monitoring.md) | Трафик по клиентам, лимиты |
| `/routing` | `RoutingPage` | `routing` | [routing-cidr](routing-cidr.md) | CIDR-провайдеры, pipeline |
| `/antizapret` | `AntizapretConfigPage` | `routing` | [antizapret-config](antizapret-config.md) | Конфиг AntiZapret (admin) |
| `/warper` | `WarperPage` | `warper` | [warper](warper.md) | AZ-WARP / Cloudflare WARP |
| `/telegram` | `TelegramPage` | `telegram` | [Telegram](Telegram.md) | Настройки бота и Mini App |
| `/edit-files` | `EditFilesPage` | `edit_files` | [edit-files](edit-files.md) | Редактор файлов AntiZapret |
| `/logs` | `LogsPage` | `logs_dashboard` / `action_logs` | [logs](logs.md) | Журналы |
| `/server-monitor` | `ServerMonitorPage` | `server_monitor` | [server-monitor](server-monitor.md) | vnStat, нагрузка сервера |
| `/nodes` | `NodesPage` | — (admin) | [uzly](uzly.md) | VPN-узлы, sync groups (HA) |
| `/settings` | `SettingsPage` | — | [nastrojki](nastrojki/README.md) | Пользователи, бэкапы, безопасность… |
| `/login` | `LoginPage` | — | [profil](nastrojki/profil.md) | JWT + 2FA + passkey |

**Ключевые контексты:** `AuthContext`, `NodeContext` (активный узел), `FeatureModulesContext`, `ThemeContext`.

**Навигация:** `frontend/src/components/Layout.tsx` — sidebar, feature guards.

**API-клиент:** `frontend/src/api/client.ts` → базовый URL `/api`, Bearer token + refresh cookie.

---

## Backend: роутеры (`/api/...`)

| Роутер | Домен |
|--------|-------|
| `auth`, `session`, `users` | Аутентификация, 2FA, пользователи, роли |
| `configs`, `client_access` | VPN-клиенты, блокировки, лимиты |
| `nodes` | Управление узлами, health, обновления |
| `monitoring` | NOC: подключения, гео, службы |
| `traffic` | Сбор и отображение трафика |
| `routing`, `cidr_db` | CIDR-провайдеры, pipeline, deploy |
| `warper` | AZ-WARP |
| `edit_files` | Редактор конфигов AntiZapret |
| `backups`, `maintenance`, `system` | Бэкапы, обслуживание, обновления |
| `settings`, `security` | Настройки панели, IP whitelist, firewall |
| `server_monitor` | Мониторинг сервера (vnStat) |
| `logs` | Action logs |
| `feature_toggles` | Включение/выключение модулей |
| `tg_mini`, `telegram_webhook` | Telegram Mini App + бот |
| `public_download` | Публичная выдача конфигов по QR |
| `tasks` | Фоновые задачи (CIDR pipeline и др.) |
| `tests` | Диагностика (feature-gated) |
| `ip_blocked` | Страница блокировки IP (без `/api`) |

Регистрация роутеров: `backend/app/main.py`.

---

## Сервисный слой (где искать логику)

### VPN и узлы
- `node_manager.py` — активный узел, CRUD узлов
- `node_adapter.py` — абстракция **LocalAdapter** / **RemoteAdapter** (HTTP к agent :9100)
- sync groups / HA — UI: `NodeSyncGroupSection.tsx`, API: `nodes` router; см. [`NodeSync.md`](NodeSync.md), user: [`uzly.md`](uzly.md)
- `antizapret.py`, `openvpn_management.py`, `wg_runtime.py` — работа с VPN на узле
- `profile_files.py`, `qr_generator.py` — конфиги и QR

### Мониторинг и трафик
- `monitoring_overview.py`, `ip_geo.py`, `geoip_local.py` — NOC-сводка, GeoIP ([`GeoIP.md`](GeoIP.md))
- `traffic/` — collector, sessions, chart, worker
- `traffic_limit.py`, `traffic_limit_reconcile.py` — лимиты
- `resource_metrics*.py`, `panel_resource_metrics*.py` — CPU/RAM узлов и панели

### CIDR / маршрутизация
- `services/cidr/` — pipeline, scheduler, deploy
- `services/cidr/pipeline/` — orchestrator, db_pipeline, file_pipeline, csv import

### Telegram
- `telegram_bot.py` + `telegram_bot_handlers/` — команды бота
- `telegram_webhook.py`, `telegram_config_send.py`
- `tg_mini.py` (router) — API для Mini App
- Документация: `docs/Telegram.md`

### Безопасность
- `security.py`, `totp_service.py`, `ip_restriction.py`
- `feature_guards.py`, `feature_toggles.py`
- `middleware/` — rate limit, CSP, active sessions

### Прочее
- `backup_manager.py`, `backup_scheduler.py`
- `warper.py` — AZ-WARP
- `background_tasks.py` — long-running задачи с polling
- `admin_notify.py` — уведомления админам в Telegram

---

## Модели данных (основная БД)

| Модель | Назначение |
|--------|------------|
| `User`, `RefreshToken`, `ActiveWebSession` | Пользователи, сессии |
| `VpnConfig` | Привязка клиента к узлу и владельцу |
| `Node` | VPN-узел (local/remote, API key, mTLS) |
| `WgAccessPolicy`, `OpenVpnAccessPolicy` | Блокировки, лимиты трафика |
| `TrafficSessionState`, `UserTrafficStatProtocol`, `UserTrafficSample` | Трафик |
| `NodeResourceSample`, `PanelResourceSample` | Метрики ресурсов |
| `ProviderMeta` | Мета CIDR-провайдеров |
| `AppSetting` | key-value настройки |
| `UserActionLog` | Аудит действий |
| `QrDownloadToken` | Публичные ссылки на конфиги |

**Отдельная БД:** `ProviderCidr` в `cidr_models.py` → `cidr.db`.

---

## Фоновые workers (запуск в `lifespan`)

При старте FastAPI (`backend/app/main.py`) поднимаются asyncio-задачи:

1. `run_traffic_collector_loop` — сбор трафика
2. `run_node_health_loop` — health узлов
3. `run_resource_metrics_loop` / `run_panel_resource_metrics_loop` — метрики
4. `run_backup_scheduler_loop` — бэкапы по расписанию
5. `run_cidr_db_scheduler_loop` — обновление CIDR
6. `run_wg_policy_sync_loop` — синхронизация WG-политик
7. `run_nightly_idle_restart_loop` — ночной рестарт
8. `run_node_key_rotation_loop` — ротация ключей узлов
9. `run_cert_sync_loop` — синхронизация сертификатов (если включено)
10. `admin_notify_service.start_monitor()` — алерты CPU/RAM

---

## Telegram Mini App

- Сборка: `vite build --mode tg-mini` → `backend/app/static/tg_mini/`
- Роуты (`frontend/src/tg-mini/App.tsx`): Dashboard, Configs, Nodes, Settings
- Auth: `TgAuthContext` + initData Telegram
- API: `frontend/src/tg-mini/api.ts` → `/api/tg-mini/...`

---

## Конфигурация и запуск

| Файл | Роль |
|------|------|
| `backend/.env` | Секреты, БД, feature flags, порты |
| `backend/app/config.py` | Pydantic Settings (defaults) |
| `start.sh` | Dev: backend (uvicorn) + frontend (vite) + watchdog |
| `install.sh` | Production: nginx, systemd, certbot, wizard |

**Типичные пути:**
- AntiZapret: `/root/antizapret` (`antizapret_path`)
- Бэкапы: `/var/backups/adminpanelaz`
- БД: `backend/data/adminpanel.db`
- CIDR: `backend/data/cidr/cidr.db`

**Dev-порты:** backend `:8000`, frontend `:5173` (`start.sh`).

---

## Быстрая навигация «хочу изменить X»

| Задача | Куда идти |
|--------|-----------|
| Новый API endpoint | `backend/app/routers/` + `schemas.py` + `frontend/src/api/client.ts` |
| UI страница | `frontend/src/pages/` + `components/` |
| Логика VPN на узле | `node_adapter.py`, `antizapret.py` |
| Блокировка/лимит клиента | `client_access` router, `WgAccessPolicy` / `OpenVpnAccessPolicy` |
| CIDR deploy | `services/cidr/pipeline/` |
| Telegram-команда | `services/telegram_bot_handlers/` |
| Feature flag | `services/feature_toggles.py` + `FeatureGuardRoute` на фронте |
| User doc для UI-раздела | `docs/<module>.md` или `docs/nastrojki/<section>.md` + строка в [`docs/README.md`](README.md) |
| Миграция БД | `database.py` → `run_db_migrations()` |
| Фоновая задача | `background_tasks.py` + `tasks` router |

---

## Роли пользователей

- **admin** — полный доступ, узлы, warper, telegram
- **user** — свои конфиги, ограниченные разделы
- **viewer** — только просмотр (NOC, трафик, логи)

---

## Связанные документы

### Пользовательские руководства

- [`docs/README.md`](README.md) — оглавление всех инструкций
- [`docs/nastrojki/README.md`](nastrojki/README.md) — настройки панели
- [`docs/Telegram.md`](Telegram.md) — Telegram-интеграция
- [`docs/GeoIP.md`](GeoIP.md) — локальная GeoIP (MaxMind)

### Разработка и эксплуатация

- [`README.md`](../README.md) — установка, возможности, ссылки на user docs
- [`SECURITY.md`](../SECURITY.md) — безопасность
- [`CHANGELOG.md`](../CHANGELOG.md) — история изменений
- [`docs/NodeSync.md`](NodeSync.md) — HA / sync groups (API, ограничения)
- [`docs/PROJECT_MAP.md`](PROJECT_MAP.md) — этот файл
