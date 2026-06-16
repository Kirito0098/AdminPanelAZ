# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where applicable.

## [Unreleased]

### Added

- **Пользовательская документация** — простые инструкции по разделам веб-панели: [`docs/README.md`](docs/README.md), модули меню (`konfiguracii.md`, `noc-monitoring.md`, …), подразделы настроек [`docs/nastrojki/`](docs/nastrojki/README.md).

### Changed

- [`README.md`](README.md) — длинные блоки NOC/трафик/узлы заменены ссылками на user docs.
- [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) — карта UI ↔ user doc, актуальное дерево `docs/`.

### Removed

- **Roadmap-документы** — `docs/Idei.md`, `docs/Etapy-prompty.md`, `docs/Backlog-otkryto.md` (задача **10.1 PostgreSQL** снята с плана: для типичного деплоя SQLite достаточен).
## [2.1.0] - 2026-06-16

### Added

#### Backlog 2026-06-16 (этапы 3, 5, 7, 9, 10)

- **Правила алертов (7.3)** — модель `AlertRule` (метрика, оператор, порог, cooldown, optional `node_id`); worker `alert_rule_worker.py` на DB aggregates (`ovpn_online_total`, `wg_online_total`, `nodes_offline`, `node_offline_seconds`, `traffic_collector_lag_seconds`); AdminNotify при срабатывании (`event_type=alert_rule`); UI **Настройки → Мониторинг и алерты** (`AlertRulesCard`); API `/api/alert-rules` (admin CRUD + `/metrics` + `/evaluate`).
- **HA в NOC (5.6)** — federated overview (`scope=all`) дедуплицирует online-клиентов по `NodeSyncGroup` / `ha_primary_config_id`: одна строка на logical HA client, badge `HA: {domain} ({N} узл.)`; сводные totals — deduped, per-node summary — raw.
- **GeoIP onboarding (7.1)** — [`docs/GeoIP.md`](docs/GeoIP.md): инструкция загрузки GeoLite2 City+ASN в `data/geoip/`; `GET /api/maintenance/geoip-status`; карточка статуса в **Настройки → Обслуживание** («GeoIP: loaded / fallback ip-api»).
- **Weekly PDF-отчёты NOC (7.4)** — `noc_report_pdf.py` (reportlab): top clients (7д), инциденты из `AlertRule`, CIDR failures; cron на weekly tick; опциональная доставка PDF в TG (`send_tg_document`); env `NOC_REPORT_WEEKLY_PDF_*`.
- **Wizard политик per-node (3.4)** — дефолтные лимиты/маршруты EU vs RU через `OpenVpnAccessPolicy` / `WgAccessPolicy` (sentinel `__node_default__`); API `GET/PUT /api/client-access/node-defaults/{node_id}`; `NodeDefaultPolicyWizard` на странице **Узлы**.
- **Secrets rotation wizard (9.4)** — guided flow preview → confirm (`ROTATE`) → write для `SECRET_KEY`, `NODE_AGENT_API_KEY`, `telegram_bot_token`; re-login warning после смены JWT secret; re-encrypt node keys/TOTP; UI **Настройки → Безопасность** (`SecretsRotationWizard`); обновлены `SECURITY.md`, `README.md`.
- **Plugin / hook registry (10.3)** — `plugin_registry.py`, `notify_backends.py`: `register_notify_backend`, `dispatch_admin_notify`; AdminNotify через registry (default: `telegram`); пример `notify_backend_example.py`.
- **Telegram inline mode (10.4)** — `@bot query` → Mini App link / config file (`InlineQueryResultDocument`); TTL-кэш 60 с; webhook `inline_query` + `chosen_inline_result`; строки в `telegram_bot_i18n.py`.

#### Установка и CI

- **Простая установка (`install-easy.sh`)** — отдельный установщик для начинающих: понятные вопросы с пояснениями, минимум технических терминов. Мастер [`scripts/install-easy-wizard.sh`](scripts/install-easy-wizard.sh): тип установки (панель / панель+VPN / node agent), доступ в браузере (свой домен / DuckDNS / только локально), логин и пароль, размер сервера (1 GB / 2 GB+), автозапуск systemd и firewall. Меню: установка, удаление, переход к полному `install.sh`, справка. Флаг `--easy` в [`install.sh`](install.sh) вызывает тот же мастер.
- **CI — install smoke** — job `install-smoke` в GitHub Actions: non-interactive установка через systemd, проверка `/api/health`, `/api/health/deep` и статики frontend; скрипт [`scripts/install-smoke-test.sh`](scripts/install-smoke-test.sh).

#### Frontend (CSP-safe)

- **`PercentBar`** — SVG progress fill без inline `style` (CSP-safe).
- **`ChartResponsive`** — sizing Recharts через ResizeObserver без inline width/height.

#### Тесты

- `test_alert_rules.py`, `test_monitoring_overview_ha.py`, `test_node_default_policy.py`, `test_secrets_rotation.py`, `test_plugin_registry.py`, `test_telegram_inline.py`; расширены `test_ip_geo.py`, `test_http_security.py`, `test_noc_report.py`.

### Changed

#### Backlog 2026-06-16

- **CSP hardening (9.1)** — `style-src 'self'` (убран `'unsafe-inline'`); inline styles во frontend заменены на Tailwind/CSS/`PercentBar`/`ChartResponsive`; nonce для `script-src` без изменений.
- **NOC federated overview** — HA aggregation в `build_federated_monitoring_overview`; поиск на `MonitoringPage` включает HA domain.
- **AdminNotify** — доставка через hook registry (`dispatch_admin_notify`) вместо прямого цикла `send_tg_message`.
- **Документация roadmap** — этапы 5, 7, 9 закрыты; обновлены [`docs/Backlog-otkryto.md`](docs/Backlog-otkryto.md), [`docs/Idei.md`](docs/Idei.md), [`docs/Etapy-prompty.md`](docs/Etapy-prompty.md). Открыто: **10.1** PostgreSQL, **10.2** i18n веб-панели.

#### Установка

- **README — установка** — простой установщик (`install-easy.sh`) указан первым в «Быстром старте»; полный `install.sh` — для расширенных настроек.
- **Установка — non-interactive** — автогенерация пароля администратора, профиль **Minimal**, отключение локального AntiZapret, синхронизация admin в БД без интерактивного мастера; `--with-systemd` / `--with-daemon` переопределяют режим запуска из CLI.
- **Мастер установки — defaults** — при `WIZ_ACCEPT_DEFAULTS`: Nginx пропускается (localhost), systemd, 1 uvicorn worker.
- **Удалённая установка** — автоматическая установка `git` через apt при bootstrap, если пакет отсутствует.

### Fixed
- **Node Sync reconcile worker** — восстановлен импорт `run_node_sync_reconcile_loop` в `lifespan_workers.py` (воркер не стартовал).
- **Установка — Let's Encrypt** — при недоступном DNS/порте 80 установка продолжается без HTTPS (`NGINX_FAIL_SOFT`); подсказка про `./scripts/nginx-setup.sh`.
- **Мастер установки** — безопасные значения по умолчанию для `WIZ_TELEGRAM_*` / `WIZ_AUTO_BACKUP_*` при seed в БД.

### Security
- **CSP** — `style-src 'self'` на основных страницах; scripts — nonce (без изменений).
- **Secrets rotation** — guided wizard с явным подтверждением `ROTATE`; без silent overwrite `.env`.

### Dependencies
- **reportlab** — 4.2.5 (weekly NOC PDF).
- **cryptography** — 44.0.0 → 46.0.3.

## [2.0.0] - 2026-06-16

Major release: roadmap этапы 1–8 (и большая часть 9) — prod foundation, admin productivity, multi-node, CIDR safety, Node Sync HA, self-service, ops/security. Открытые пункты roadmap — см. [docs/Backlog-otkryto.md](docs/Backlog-otkryto.md).

### Added

#### Prod foundation (этап 1)
- **Retention policies** — фоновый `retention_worker`, batch purge traffic samples / action logs / resource metrics; настройки в **Настройки → Обслуживание** и `.env`.
- **Prometheus** — `GET /metrics` (`traffic_collector_lag_seconds`, `node_health_*`, без high-cardinality labels).
- **Health** — `GET /api/health/deep` (SQLite, CIDR DB, traffic lag); установщик проверяет deep health после старта.
- **Resource profiles** — пресеты **Minimal / Standard / Full**: `POST /api/feature-toggles/apply-profile`, `worker_lifecycle.py`, wizard в `install-wizard.sh`, UI impact + banner «нужен restart».
- **Route budget** — `GET /api/routing/cidr-db/route-budget`, виджет на странице маршрутизации.
- **Vitest** — baseline-тесты (`configCardUtils`, `buildLightDiff`), шаг `npm test` в CI.
- **Redis в prod** — документация README/SECURITY; wizard подсказывает Redis при `UVICORN_WORKERS > 1`.

#### Admin productivity (этап 2)
- **Теги клиентов** — CRUD `/api/config-tags`, назначение на конфиг, фильтр на Dashboard и в mass ops.
- **Шаблоны клиентов** — `ClientTemplate`, one-click create с пресетами cert/traffic.
- **Массовые операции** — `POST /api/configs/bulk` (block / delete / renew), фоновая задача + progress, лимит параллелизма.
- **AmneziaWG** — отдельная вкладка на Dashboard (`ConfigCardsSection`).
- **Активные сессии** — список и revoke в **Настройки → Безопасность** (`ActiveWebSession`).

#### Multi-node (этап 3)
- **Global dashboard** — сводка online/health по всем узлам (`GlobalDashboardSection`, кэш `node_remote_cache` 30–60 с).
- **Сравнение узлов** — `NodesCompareSection`, `GET /api/monitoring/nodes-compare`.
- **Geo-routing hint** — баннер «ближайший узел» (`GeoRoutingHintBanner`, `/api/nodes/geo-routing-hint`).
- **Политики per-node** — сводка лимитов/блокировок по узлам (`NodePolicySummarySection`).

#### CIDR безопасность (этап 4)
- **Dry-run deploy** — preview файлов и route count (`deploy_preview.py`, `DeployPreviewPanel`).
- **Rollback CIDR** — one-click откат из `runtime_backups`, background task, AdminNotify при ошибке.
- **Custom provider wizard** — UI добавления ASN/CIDR без правки файлов.

#### Node Sync / HA (этап 5)
- **Sync Group** — модель `NodeSyncGroup`, CRUD `/api/nodes/sync-groups`, UI на странице **Узлы**.
- **Push full** — backup primary → restore replica(s), progress bar (`push_full.py`).
- **Verify parity** — сравнение OVPN/WG клиентов и checksums PKI/peers.
- **Auto-sync** — create/delete на primary реплицирует на replica (`client_sync.py`, linked `VpnConfig`).
- **Reconcile worker** — периодическая сверка, алерт при drift (`reconcile_worker.py`).
- **HA на Dashboard** — badge «HA: domain (N узл.)», dedup shadow configs.
- **Node agent** — `POST /backups/antizapret/restore`, fingerprints; документация [`docs/NodeSync.md`](docs/NodeSync.md).

#### Self-service (этап 6)
- **User role** — create/download/traffic в квотах (`self_service.py`).
- **Telegram** — команды `/myconfigs`, `/traffic` для привязанных пользователей.
- **Напоминания** — expiry cert, traffic limit, temp block → TG; dedup 1×/сутки (`user_reminder_worker`).

#### Мониторинг и алерты (этап 7)
- **Локальная GeoIP** — `geoip_local.py` (MaxMind MMDB в `data/geoip/`, fallback ip-api).
- **Scheduled NOC reports** — ежедневная/еженедельная сводка в TG admin (`noc_report_scheduler.py`).

#### Ops и интеграции (этап 8)
- **Runbook UI** — guided diagnostics в **Настройки** (`RunbookTab`, `site_diagnostics` API).
- **Import / export CSV** — массовый импорт через background task, export GET.
- **Rolling node update** — очередь обновлений agent на нескольких узлах (`node_update_roll.py`).
- **OpenAPI** — `/docs` за admin auth или IP whitelist (`openapi_docs_gate.py`).
- **Event webhooks** — HTTP POST на события action log, retry queue (`webhook_delivery_worker`).
- **Mini App** — read-only страницы Warper и CIDR status.

#### Security / enterprise (этап 9)
- **WebAuthn passkeys** — регистрация и вход для admin (вместе с TOTP), `PasskeysTab`.
- **Audit SIEM** — stream `UserActionLog` в syslog/HTTP (`audit_stream.py`, Settings).
- **CSP nonce** — inject nonce в HTML/scripts (`html_csp.py`, Vite `%CSP_NONCE%`).

#### UI и прочее (после 1.9.0)
- **Конфиги — ссылка на трафик** — кнопка «Статистика трафика» на карточке конфига → `/traffic?client=…`.
- **NOC → Traffic** — клик по клиенту в `MonitoringConnectionsList` открывает график трафика.
- **UI — полное обновление панели** — `system_update.py`: git pull + pip + npm + build + отложенный restart; прогресс `update_system`.
- **NOC — гео по провайдерам** — нормализация ISP (Tele2, MegaFon, MTS…), сегмент «Прочие» с раскрытием.

#### Документация
- **Roadmap** — [`docs/Idei.md`](docs/Idei.md), промпты [`docs/Etapy-prompty.md`](docs/Etapy-prompty.md), открытый backlog [`docs/Backlog-otkryto.md`](docs/Backlog-otkryto.md), [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).

#### Тесты
- Новые pytest-модули: retention, metrics, health, feature profiles, stage2/3/4, node_sync*, self_service, noc_report, config CSV, event webhooks, audit stream, openapi gate, site diagnostics API, antizapret restore, node update roll и др.

### Changed
- **NOC — federated overview** — aggregate endpoint с кэшем; режим «Все узлы» без N+1 с фронта.
- **Lifespan** — фоновые workers стартуют через `lifespan_workers.py` с учётом feature toggles и resource profile.
- **Установка** — Node.js **20+**; deep health check до 90 с; resource profile в wizard; создание `backend/data/cidr/` до миграций.
- **Prod start** — `start.sh` пропускает `npm run build:all`, если dist/tg_mini уже собраны (`ADMINPANELAZ_FORCE_FRONTEND_BUILD=1` для принудительной пересборки).
- **Frontend — Vite 6.4.2** — `build.target: es2022`; overrides `esbuild ^0.28.1`.
- **Трафик** — убран дублирующий bar-chart «Топ клиентов (7д)»; фокус на выбранном клиенте.
- **README / SECURITY** — таблица VDS → profile, Redis для multi-worker, passkeys, health/metrics endpoints.
- **Git** — `.gitignore`: `backend/app/static/tg_mini/`, кэш Vite.
- **Обновления UI** — «Настройки → Обновления» отражает полный цикл deps + build + restart.

### Fixed
- **Установка — CIDR БД** — `unable to open database file` на чистой установке (каталоги до `create_all`).
- **Prod start** — лишняя пересборка frontend при каждом systemd restart (~25 с без listening port).
- **npm audit** — Vite 6.4.2 + esbuild override без перехода на Vite 8.
- **UI — git pull only** — «Применить обновление» раньше не ставило deps и не пересобирало UI.

### Security
- Passkeys optional alongside TOTP; audit stream для compliance; CSP nonce для scripts; OpenAPI и webhooks — admin-only.

## [1.9.0] - 2026-06-15

### Added
- **NOC — сводка мониторинга** — `GET /api/monitoring/overview?scope=node|all`: активные OpenVPN/WireGuard, службы, геолокация IP (город · провайдер), режим «Активный узел» / «Все узлы» с таблицей узлов.
- **NOC — геолокация** — сервис `ip_geo.py`: нормализация endpoint (`udp4:` и т.п.), batch lookup ip-api.com, кэш 24 ч; поля `display_address`, `city`, `isp`, `geo_label` в схемах мониторинга и трафика.
- **NOC — UI** — единый список VPN-клиентов (`MonitoringConnectionsList`): карточки на узких экранах, широкая таблица на `xl+`; donut-сводки по городам и провайдерам (`MonitoringGeoSummary`); общая тема графиков (`monitoringChartTheme`, `MonitoringChartCard`).
- **NOC — фильтр «Только онлайн»** — переключатель в блоке VPN-клиентов (включён по умолчанию): скрывает офлайн-пиры WireGuard; сводки и список следуют фильтру.
- **Трафик — мониторинг клиента** — панель `TrafficClientFocusPanel`: выбор пользователя, метрики, график VPN/AntiZapret, лимит, URL `?client=`; переключатель «Только выбранный».
- **Трафик — сессии по адресам** — `GET /api/traffic/client-sessions`: разбивка подключений клиента по IP; активные адреса по умолчанию, история неактивных по кнопке «Показать историю».
- **Трафик — гео в сессиях** — город и ISP под IP клиента в таблице подключений.
- **Мониторинг панели** — расширенные графики ресурсов хоста и процессов панели (`PanelResourceHistoryCharts`): live-снимок, CPU/RAM/диск хоста, backend/nginx/watchdog/vite.
- **Telegram — главное меню бота** — Reply Keyboard и inline-навигация (`menu.py`): Статус, Конфиги, Узлы (admin), CIDR, AZ-WARP, Настройки; маршрутизация текста и callback.
- **Telegram — отправка конфигов** — общий модуль `telegram_config_send.py`, подписи файлов `telegram_profile_ui.py`; улучшенный UX выбора и отправки профилей в боте и Mini App.
- **Тесты** — `test_ip_geo.py`, `test_monitoring_overview.py`, `test_traffic_sessions.py`, `test_telegram_bot_menu.py`, `test_telegram_bot_ui.py`, `test_telegram_config_send.py`, `test_telegram_nodes.py`, `test_telegram_profile_ui.py`.

### Changed
- **NOC — UI** — убраны неинформативные графики «Статус служб» и «Трафик сессий»; все аналитические карточки (линия, столбцы, geo) в едином блоке над вкладками; согласованные цвета протоколов (OpenVPN / WireGuard).
- **NOC — вкладка VPN-клиенты** — выровнен заголовок и панель фильтров (поиск, протокол, «Только онлайн» в одну линию).
- **NOC — вкладка VPN-узел** — убран бейдж с числом сырых снимков метрик (`sample_count`) на табе; счётчик остаётся в подписи графика внутри вкладки.
- **Трафик** — страница переработана вокруг фокуса на выбранном клиенте; улучшена читаемость таблиц и адресов.
- **Recharts** — глобальные стили тултипов для тёмной темы: читаемый текст на фоне `popover`.
- **Telegram** — обработчики бота делегируют в меню/UI-модули; обновлены `docs/Telegram.md` и i18n.

### Fixed
- **NOC — overview 500** — исправлена ошибка Pydantic при обогащении клиентов гео (`model_copy(update=...)` вместо `**model_dump()` + дублирующие поля).
- **Recharts** — нечитаемый текст в тултипах при наведении на графики (тёмный текст на тёмном фоне).
- **Журналы — подключения** — исправлен подсчёт WireGuard-пиров и общего числа на вкладке «Подключения»: учитываются только онлайн-пиры с handshake (как в NOC-мониторинге); OpenVPN подписан как «сессии».

## [1.8.0] - 2026-06-14

### Removed
- **Игровые фильтры** — полное удаление функциональности include/exclude для игровых доменов и IP (~75 игр из каталога AdminAntizapret):
  - **UI** — вкладка «Игровые фильтры» на странице маршрутизации (`GameFiltersTab`, deep link `?tab=games`).
  - **API** — `GET/POST /api/routing/game-filters`, сохранение режимов в `app_settings.game_filter_modes`.
  - **Node agent** — `POST /routing/game-filters/sync`.
  - **Backend** — модули `game_catalog.py`, `game_server_data.py`, `game_filters.py`, `game_filter_sync.py`, `pipeline/games.py`, `pipeline/games_catalog.py`, router `game_filters.py`; метод `NodeAdapter.sync_game_routes_filter`.
  - **CIDR pipeline** — синхронизация `AZ-Game-include-*` / `AZ-Game-exclude-*` при generate/deploy; поле `include_game_hosts` в `CidrDbGenerateRequest`.
  - **Константы/env** — `CIDR_AZ_GAME_*`, `CIDR_GAME_LEGACY_*`, `AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT` и связанные маркеры managed-блоков.
  - **Тесты** — `test_game_filters_sync.py`, `test_game_catalog_coverage.py`; game-related кейсы в `test_cidr_list_updater.py`.

### Changed
- **CIDR pipeline** — generate/estimate/deploy больше не трогают игровые конфиги AntiZapret; лимит маршрутов OpenVPN всегда enforced (без env-обхода через game filter).
- **README** — убраны упоминания game filters из матрицы возможностей и чеклиста.
- **Telegram — Mini App** — inline HTML в `tg_mini.py` заменён на static React-сборку; deprecated `POST /api/tg-mini/send-config`.

### Fixed
- **Тесты** — стабильный прогон на машинах с production `.env` (`ENFORCE_HTTPS`, `BEHIND_NGINX`): autouse-изоляция env в `conftest.py`, патч `http_security.get_settings` в `api_test_env`; исправлены ожидания в `test_profile_files`, `test_warper_service`, `test_api_rate_limit` (patch middleware import path).
- **Telegram webhook** — IP-allowlist использует `X-Real-IP` / `request.client`, без доверия к подменённому `X-Forwarded-For`.
- **Telegram Mini App** — проверка `auth_date` в `init_data`; запрет смены `telegram_id` через `PATCH /admin-notify`.
- **Telegram Mini App** — `PATCH /telegram-settings` делегирует в `maintenance.update_telegram_settings` (interactive + webhook lifecycle).
- **Telegram bot /settings** — webhook регистрируется с публичным URL из `mini_app_url`, не `panel.local`.
- **Debug** — удалена временная agent-log инструментация из `auth.py` и `LoginPage.tsx`.

### Added
- **Telegram — интерактивный бот (фазы 0–4)** — webhook `POST /api/telegram/webhook/{secret}`, IP-allowlist Telegram, rate limit; команды `/start`, `/link`, `/status`, `/configs`, `/config`, `/help`, `/settings` (admin, inline-меню настроек панели).
- **Telegram — /settings в боте** — разделы Telegram, AdminNotify, бэкапы, мониторинг, безопасность, обслуживание; FSM-ввод чисел/токена; confirm для опасных действий; `action_logs` с `source=telegram_bot`.
- **Telegram — Mini App v2** — React entry `frontend/src/tg-mini/` (Dashboard, Configs, Settings, TelegramSettings); Vite build → `backend/app/static/tg_mini/`; API: files, send (`self`|`chat`), QR-link, admin-notify и telegram-settings proxy.
- **Telegram — фаза 0** — `TelegramTab`: username, max auth age, Mini App URL, interactive bot + webhook UI, notify_on_backup; `UsersTab`: Telegram ID; Login Widget — причина отключения; send-config на `user.telegram_id`; AdminNotify при PATCH telegram settings; `GET /api/telegram/link-code`.
- **Telegram — фаза 4** — единый словарь RU `telegram_bot_i18n.py`; команды `/cidr` (статус pipeline) и `/warper` (статус AZ-WARP, если модуль включён).
- **Документация** — обновлены `docs/Telegram.md` и чеклист регрессии Telegram в `README.md`.
- **Тесты** — `test_telegram_settings.py`, `test_telegram_webhook.py` (callback_query, inline keyboard), `test_telegram_bot_settings.py`, `test_tg_mini_routes.py`, `test_tg_mini_send_config.py`.

### Migration notes
- **`app_settings.game_filter_modes`** — orphan-записи в БД можно оставить или удалить вручную; на работу панели не влияют.
- **`AZ-Game-*` на узлах** — существующие файлы в `config/` AntiZapret больше не обновляются кодом; при необходимости очистите вручную или перезапишите через AntiZapret.

## [1.7.0] - 2026-06-14

### Added
- **QR-коды** — для OpenVPN-профилей, не помещающихся в QR (~4.5 КБ), автоматический fallback на одноразовую ссылку скачивания; заголовки ответа `X-Qr-Content` (`profile` / `download-link`) и `X-Qr-Download-Url`.
- **UI — QR-код** — кнопка «Скопировать ссылку» в диалоге QR при режиме download-link; подсказка, что конфигурация слишком большая для прямого QR.
- **Тесты** — `test_qr_generator.py` (лимит размера, fallback на ссылку, заголовки API).
- **AZ-WARP (WARPER)** — интеграция точечной маршрутизации доменов и IPv4-подсетей через Cloudflare WARP на VPN-узлах: `WarperService` → `warper_api`, API `/api/warper/*`, endpoints node agent `/warper/*`, feature toggle `FEATURE_WARPER_ENABLED`.
- **UI — AZ-WARP** — страница `/warper` (пункт меню «AZ-WARP»): домены (добавление, импорт, синхронизация), встроенные списки Gemini/ChatGPT, IP-подсети, мониторинг (статус, трафик, логи sing-box, диагностика `doctor`), настройки (MTU, уровень логов, sing-box).
- **UI — AZ-WARP** — шапка со статусом узла и быстрым вкл/выкл; сводные карточки с переходом на вкладки; переключатели встроенных списков вместо пар кнопок «вкл/выкл».
- **Документация** — `docs/AZ_WARP_INTEGRATION_PLAN.md`, `docs/VPN_FEATURES_BACKLOG.md`.
- **Тесты** — `test_warper_service.py`, `test_warper_api.py`; parity `get_warper_*` в `test_node_adapter_parity.py`; `test_git_pull_resets_after_diverged_history` в `test_node_update.py`.

### Fixed
- **QR-коды** — исправлена ошибка «Ошибка генерации QR» для OpenVPN/AntiZapret `.ovpn` (встроенные сертификаты превышают ёмкость QR); WireGuard/короткие профили по-прежнему кодируются целиком.
- **API client** — `fetchQrBlob`: разбор `detail` из ответа бэкенда, `credentials: 'include'`, обновление токена при 401, заголовок `X-Web-Session-Id`.
- **AZ-WARP — health** — установка определяется по `warper.sh` и `warper_api`, не только по симлинку `/usr/local/bin/warper`; в алертах — `missing_components` и подсказка переключить активный узел.
- **AZ-WARP — doctor** — при ошибках проверок API возвращает полный список результатов, а не 502 с обрезанным текстом; UI показывает сводку OK/ошибок и каждую проверку отдельной строкой.
- **AZ-WARP — настройки / IP-подсети** — `get_mode()` и fallback чтения `ip-ranges.txt` / `domains.txt` при сбое CLI; корректный парсинг встроенных списков по маркерам в `domains.txt`.
- **AZ-WARP — UI** — если WARPER не установлен на активном узле, вкладки управления скрыты; блок «Управление недоступно» с командой установки и ссылкой на узлы (без лишних API-запросов).
- **Обновление узла** — после squash/force push на `main` git pull на ноде выполняет `reset --hard origin/main` при чистом working tree; в диалоге обновления — признак расходящейся истории.
- **API client** — исправлена ошибка `body stream already read` при разборе HTTP-ошибок (однократное чтение тела ответа).

### Changed
- **UI — AZ-WARP** — вкладки «Трафик», «Статус», «Логи» и «Диагностика» объединены в одну «Мониторинг»; улучшены таблица доменов, настройки и карточки сводки.

## [1.6.0] - 2026-06-11

### Added
- **CIDR — отдельная БД `cidr.db`** — таблица `provider_cidr` вынесена из `adminpanel.db` в `data/cidr/cidr.db` (`CIDR_DATABASE_URL`); при старте одноразовая миграция через ATTACH + DROP в основной БД.
- **CIDR — быстрая запись ingest** — CSV-staging и нативный bulk-import в SQLite (`cidr_csv_import.py`); каталог staging `data/cidr/staging`.
- **CIDR — частичное обновление провайдеров** — `selected_files` в `POST /api/routing/cidr-db/refresh`, `generate` и `deploy`; режим `retry_failed_mode` (`last` / `selected`) для повторной загрузки только ошибочных.
- **UI — выбор провайдеров** — компонент `ProviderFileSelection`: поиск, фильтры по категории (CDN / Облако / Хостинг), компактная сетка 4–6 колонок, итог «выбрано N · ~X CIDR»; кнопка быстрой загрузки одного провайдера на этапе 1 и во вкладке «Провайдеры».
- **vnStat на удалённых узлах** — `scripts/setup-vnstat.sh`; подсказки в мониторинге, если на активной VPN-ноде нет vnstat.
- **VPN-профили** — понятные имена файлов при скачивании (`AZ-client.ovpn`, `VPN-client.ovpn` и т.п.) для OpenVPN, WG, AWG, одноразовых ссылок и Telegram.
- **Uninstall** — симметричная очистка iptables/ufw; `--purge-all` и `--remove-backups` в меню установщика.

### Fixed
- **CIDR ingest** — тяжёлая запись CIDR больше не блокирует основную SQLite-панель; прогресс масштабируется по числу выбранных провайдеров (не «застревает» на 5–75 % при полном refresh).
- **CIDR pipeline UI** — polling фоновых задач: таймаут, счётчик ошибок, корректное завершение при сбоях сети.
- **AWG/WG профили** — скачивание и бейджи учитывают активную вкладку; batch-загрузка различает OpenVPN и WireGuard с одним именем; точнее сопоставление файлов на узле.
- **mTLS** — включение per-node без обрыва HTTP: синхронный restart не рвёт provision-ответ; настройки пишутся в `backend/node_agent.env`; ожидание подъёма агента по HTTPS.
- **ConfigCard** — исправления отображения и работы карточек конфигурации VPN-клиентов.
- **UI** — глобальный прогресс-бар фоновых задач закреплён внизу экрана.

### Changed
- **Бэкапы** — `BackupManager` и restore включают `data/cidr/cidr.db` (`components: cidr_db`).
- **UI — CIDR Pipeline (этап 1)** — перед «Обновить из интернета» выбираются провайдеры; динамическая подпись кнопки («1 провайдер» / «N провайдеров» / «все»); кнопка «Повторить ошибочные».
- **UI — вкладка «Провайдеры»** — скрыты технические `*-ips.txt`; категории на русском; компактный формат чисел CIDR (`32k`); кнопка «Загрузить» вместо «Ingest».
- **`.env.example`** — `CIDR_DATABASE_URL`, `CIDR_DB_STAGING_DIR`.
- **Тесты** — `test_cidr_database_migration.py`, `test_cidr_csv_import.py`; обновлены `test_backup_manager.py`, `test_cidr_db_updater_service.py`.

## [1.5.0] - 2026-06-10

### Added
- **CIDR Pipeline (вариант A, controller-centric)** — полный цикл ingest → compile → deploy → apply: тяжёлая работа на панели, ноды принимают артефакты через `PUT /routing/providers/{file}`.
- **Orchestrator** — `run_ingest`, `run_compile`, `run_deploy`, `run_apply`, `run_multi_deploy`; модули `orchestrator.py`, `deploy.py`, `cidr_notify.py`.
- **API** — `POST /api/routing/cidr-db/deploy` (фоновая задача `cidr_deploy`); `GET /api/routing/cidr-db/deploy/status`; в `generate` — `deploy_after`, `target_node_id`; в `deploy` — `target_node_ids`, `all_online`, `selected_files`.
- **Мульти-нода deploy** — push на выбранные online-узлы или все online; offline пропускаются; `per_node` в result задачи; audit log `settings_cidr_deploy`.
- **Ночной cron** — опционально compile/deploy после refresh (`CIDR_DB_COMPILE_AFTER_REFRESH`, `CIDR_DB_DEPLOY_AFTER_COMPILE`, `CIDR_DB_DEPLOY_TARGET`); `artifact_stamp` в refresh log.
- **Наблюдаемость** — `last_compile_at`, `last_deploy` в `GET /api/routing/cidr-db/status`; `PipelineStatusBar`, `PipelineTaskProgress` с результатом по нодам; Telegram `cidr_deploy_failed`, `cidr_ingest_partial`.
- **UI** — вкладка CIDR Pipeline: три этапа (обновить БД / собрать файлы / развернуть на ноду), выбор нод, «Сгенерировать + doall»; прогресс по этапам (`PipelineStageProgress`, `usePipelineTaskPoll`).
- **UI — CIDR-провайдеры** — колонки «контроллер / нода / БД», баннеры «нужен compile» и «нужен deploy»; подсказка Deploy после успешного compile.
- **API** — `compile_artifacts` в `GET /api/routing/cidr-db/status` (файлы на контроллере после этапа 2).
- **Пути** — `app/paths.py`: единый `LIST_DIR` (`backend/data/cidr/list`); миграция legacy-артефактов из `backend/app/data/cidr/list` при старте.
- **Зависимости** — `netaddr` для агрегации CIDR при compile.
- **Документация** — `docs/CIDR_PIPELINE_VARIANT_A.md` (спецификация pipeline, фазы 0–6).
- **Тесты** — `test_cidr_pipeline_orchestrator.py`, `test_cidr_pipeline_deploy.py`, `test_cidr_db_deploy.py`, `test_cidr_multi_deploy.py`, `test_cidr_scheduler.py`, `test_cidr_notify.py`; retry commit в `test_background_tasks_service.py`.
- **Per-node mTLS** — включение mTLS для каждого удалённого узла отдельно из панели (страница «Узлы» → «Включить mTLS»): генерация CA и сертификатов на панели, доставка на node agent (`POST /system/provision-mtls`), health по HTTPS; смешанный режим HTTP + mTLS.
- **API** — `POST /api/nodes/{id}/enable-mtls`, `GET /api/nodes/mtls/status` (готовность CA, пути, права на каталог), поле `mtls_enabled` в `NodeResponse`.
- **Тесты** — `test_node_mtls_migration.py`, `test_node_mtls_adapter.py`, `test_node_mtls_certs.py`, `test_node_agent_provision_mtls.py`, `test_node_mtls_provision.py`.

### Fixed
- **CIDR refresh** — SQLite WAL + `busy_timeout` + retry commit при `database is locked`; устранены 500 при «Обновить из интернета».
- **CIDR compile** — исправлен путь `LIST_DIR` (файлы писались в `backend/app/data/…`, UI читал `backend/data/…`); добавлен `netaddr` (ошибка «netaddr package is required»).
- **Antifilter refresh** — batch commit при сохранении ~15k CIDR; прогресс по батчам; авто-сброс зависших задач по таймауту.
- **CIDR pipeline UI** — polling задач изолирован от глобального ProgressContext; exempt rate limit для `/api/routing` и `/api/tasks`; корректное возобновление `active_task` после перезагрузки страницы.
- **Обновление узла** — перезапуск node agent после git pull через `systemctl restart adminpanelaz-node`, если unit установлен; лог в `update-restart.log`.

### Changed
- **CIDR generate** — compile всегда на контроллере; `artifact_stamp` (hash артефактов) в result задачи; deploy на удалённые ноды через `RemoteNodeAdapter.save_provider_content`.
- **Узлы** — обновление узла только для node agent: убраны AntiZapret из `NodeUpdateDialog`, API `GET/POST /api/nodes/{id}/updates|update` и колонка `az` на странице «Узлы».
- **mTLS** — `NODE_AGENT_MTLS_ENABLED` в `.env` панели deprecated; режим соединения задаётся per-node (`nodes.mtls_enabled` в БД). Улучшены сообщения об ошибках SSL при несовпадении HTTP/HTTPS.

## [1.4.3] - 2026-06-09

### Added
- **`LOCAL_ANTIZAPRET_ENABLED`** — режим «только панель» в мастере не создаёт локальный узел; `sync_local_node()` синхронизирует запись при старте.
- **`openvpn_cert.py`** — чтение срока OpenVPN-сертификата с node agent (блок `<cert>` в `.ovpn`); автозаполнение `cert_expire_days` при списке конфигов и синхронизации.
- **Тесты** — `test_openvpn_cert.py`.

### Fixed
- **Удалённые узлы** — живой health-check на `GET /api/nodes/active`; автообновление статуса в шапке (poll + visibility); предупреждение при добавлении offline-узла; подсказки в мастере/node agent.
- **Карточки клиентов** — трафик с ноды для импортированных клиентов без строки политики; срок сертификата с узла вместо «не в панели».
- **Страница `/traffic`** — падение React #130 (`EmptyState` без `icon`); таймаут загрузки 25 с; fallback статистики из БД при недоступной ноде; безопасный рендер графиков.
- **Установка** — `seed-admin-user.py` / `seed-wizard-db.py` и `install.sh` запускают seed из `backend/` (корректный путь к SQLite); исправлен subshell в `seed_wizard_db_settings`.
- **HTTP LAN** — `COOP` только по HTTPS; удалены Google Fonts из `index.html` (конфликт с CSP); иконка по умолчанию в `EmptyState`.

### Changed
- **`TRAFFIC_SYNC_INTERVAL_SECONDS`** — значение по умолчанию `30` → `60` (prod-баланс: учёт лимитов трафика и нагрузка на SQLite/worker).
- **Мастер установки** — уточнён текст режима «только панель (управление удалёнными узлами)».

## [1.4.2] - 2026-06-08

### Added
- **Test suite parity audit (фаза 32)** — `test_aa_parity_audit.py`: матрица AA→AZ для всех 53 модулей AdminAntizapret + targeted tests (login captcha threshold, traffic collector rows, wg runtime subprocess errors).

### Changed
- **Test count** — 53 modules / 414 tests (parity с AA по числу модулей; 9 AA-модулей задокументированы как N/A).
- **`MIGRATION.md`**, **`MIGRATION_PLAN.md`**, **`README.md`** — In-panel pytest → ✅.

## [1.4.1] - 2026-06-08

### Added
- **Scanner dwell/window UI (фаза 31)** — `scanner_window_seconds`, `block_ip_blocked_dwell`, `ip_blocked_dwell_seconds` в API и SecurityTab.
- **Tests** — `test_security_scanner_settings.py`.

### Changed
- **`ip_restriction.py`** — runtime scanner/dwell settings читаются из AppSetting (не захардкожены).
- **`MIGRATION.md`**, **`MIGRATION_PLAN.md`**, **`README.md`** — безопасность / scanner dwell → ✅.

## [1.4.0] - 2026-06-08

### Added
- **Game filters exclude sync (фаза 30)** — `/routing/game-filters/sync` использует полный `sync_game_routes_filter` из `pipeline/games.py` (include + exclude, punch, `AZ-Game-*` файлы).
- **`game_filter_sync.py`** — path patching + `run_sync_game_routes_filter`; `NodeAdapter.sync_game_routes_filter` для local и remote узлов.
- **Node agent** — `POST /routing/game-filters/sync`.
- **Tests** — `test_game_filters_sync.py`.

### Changed
- **`game_filters.py`** — только UI state (`get_game_filters_state`); упрощённый legacy sync удалён.
- **`MIGRATION.md`**, **`MIGRATION_PLAN.md`**, **`README.md`** — game filters exclude → ✅.

## [1.3.1] - 2026-06-08

### Added
- **Ops console menu (фаза 29)** — `scripts/adminpanel-menu.sh`: интерактивное меню и флаги `--restart`, `--update`, `--backup`, `--tests`, `--diagnose`; обёртка над `start.sh`, systemd, `site-diagnostics.sh`.
- **`scripts/backup-cli.py`** — CLI создания/восстановления бэкапа через `BackupManager` (без веб-панели).

### Changed
- **`MIGRATION.md`**, **`README.md`** — консольное меню `adminpanel.sh` → ✅.

## [1.3.0] - 2026-06-08

### Added
- **VPN network guided wizard (фаза 28)** — `POST /api/settings/vpn-network/publish` запускает `scripts/nginx-setup.sh` через `BackgroundTaskService`; мастер в `VpnNetworkTab.tsx` (Nginx+LE, self-signed, direct HTTP).
- **Runtime panel port firewall** — `panel_port_firewall.py`; toggle «Блок на порту панели (iptables)» в Security tab; sync при сохранении whitelist и на startup.
- **`scripts/nginx-setup.sh`** — неинтерактивный режим (`--non-interactive`, env vars) для вызова из панели.
- **Tests** — `test_panel_port_firewall.py`, `test_ip_restriction_whitelist_firewall_gating.py`; расширен `test_vpn_network_settings.py`.

### Changed
- **`MIGRATION.md`**, **`README.md`** — VPN-сеть и firewall panel port → ✅; install `firewall-setup.sh` ≠ runtime whitelist (документировано).

## [1.2.2] - 2026-06-08

### Added
- **CI / pre-commit parity (фаза 27)** — ESLint (`npm run lint`) во `frontend/`; `pip-audit` и `bandit` в CI с `continue-on-error` (advisory, как в AA); pre-commit hooks eslint + bandit (non-blocking).
- **`frontend/eslint.config.js`** — flat config (typescript-eslint, react-hooks, react-refresh).

### Changed
- **`backend/requirements-dev.txt`** — `bandit`, `pip-audit`.
- **`MIGRATION.md`**, **`README.md`** — CI/CD, pre-commit → ✅.

## [1.2.1] - 2026-06-08

### Added
- **Test suite wave 2 (фаза 26)** — порт критичных AA-модулей: `test_cidr_db_updater_service`, `test_cidr_list_updater`, `test_access_remaining`, `test_db_migration_service`, `test_backup_scheduler`, `test_client_access_openvpn_block`, `test_settings_post_handlers`; сервис `access_remaining.py`, shim `cidr_list_updater.py`.
- **385 pytest** в 48 модулях (AA: 53; Jinja/Flask-only и phase-28 тесты не портируются).

### Changed
- **`pipeline_facade` / `facade_compat`** — `PROVIDER_SOURCES` и fallback на `cidr_list_updater` для file pipeline и тестов.
- **`games.py`** — regex чтения saved game keys поддерживает маркеры AdminPanelAZ.
- **`MIGRATION.md`**, **`README.md`** — In-panel pytest → ✅.

## [1.2.0] - 2026-06-08

### Added
- **Diff-подсветка в редакторе файлов (фаза 25)** — порт AA `buildLightDiff` (Myers + indexed fallback); live diff относительно сохранённой версии; кнопка «Сравнить с диском» (re-fetch с узла); preview diff в диалоге «Сохранить и применить».

### Changed
- **`MIGRATION.md`** — Diff-подсветка → ✅.

## [1.1.2] - 2026-06-08

### Added
- **QR max downloads (фаза 24a)** — поле «Макс. скачиваний» (1 / 3 / 5) в `SecurityTab` для `qr_download_max_downloads`.
- **`FEATURE_MAINTENANCE_ENABLED` (фаза 24b)** — toggle `maintenance` в `feature_toggles.py` и `env_defaults.sh`; guard `/api/maintenance/*` и maintenance API под `/api/settings/*`; скрытие вкладки «Обслуживание» в `SettingsNav`.
- **Тесты** — `test_feature_guards.py`: run-doall, restart-service, recreate-profiles, session-stats при отключённом maintenance.

### Changed
- **`MIGRATION.md`** — QR-настройки → ✅, `FEATURE_MAINTENANCE` → ✅, Feature toggles → ✅.

## [1.1.1] - 2026-06-08

### Added
- **CIDR presets CRUD (фаза 23)** — REST API `GET/POST /api/routing/cidr-db/presets`, `PUT/DELETE /presets/{id}`, `POST /presets/{id}/reset`; Pydantic-схемы; audit `log_action`.
- **`PresetsTab`** — создание/редактирование/удаление пользовательских пресетов, сброс встроенных, multi-select провайдеров, применение из БД.
- **Тесты** — `test_cidr_db_presets.py` (12 cases), feature guard для `/presets`.

### Changed
- **`MIGRATION.md`** — «Пресеты CIDR», «Маршрутизация / CIDR» → ✅.

## [1.1.0] - 2026-06-08

### Added
- **AdminNotify hooks (фаза 21)** — Telegram-уведомления при создании/удалении пользователя, блокировке/разблокировке OVPN/WG-клиента (с `node_id`/`node_name`) и входе с непривязанным TG ID (web + mini app).
- **Интеграционные тесты** — `test_admin_notify_integration.py`: user create/delete, client ban/unban, TG mini unlink, проверка toggles событий.

### Changed
- **Telegram Login / Mini App** — вход только для пользователей с привязанным `telegram_id` (без автосоздания `tg_*` аккаунта); при непривязанном ID — `send_tg_login_unlinked`.
- **`MIGRATION.md`** — Telegram admin-уведомления → ✅.

## [1.0.0] - 2026-06-08

Релиз после **фазы 20** (final parity audit). Baseline переноса: AdminAntizapret **1.9.0** → AdminPanelAZ **1.0.0**.

### Added
- **Test suite wave 2** — 5 модулей из AA: `test_antizapret_backup.py`, `test_backup_manager.py`, `test_firewall_tools_check.py`, `test_site_diagnostics.py`, `test_tg_mini_init_data.py` (итого **40 modules / 240 tests**).
- **README** — секция «Production readiness»: чеклист готовности, известные пробелы, таблица 🆕 возможностей сверх AA.

### Changed
- **`MIGRATION.md`** — parity audit: исправлены завышенные/заниженные статусы (presets CRUD 🟡, diff 🟡, temp whitelist 🟡, AdminNotify 🟡); baseline **1.0.0**; backlog актуализирован; test count 40/240.
- **Оценка готовности** в README: ~85–90% функциональности AA 1.9.0.

### Documented gaps (backlog 1.0.0+)
- AdminNotify TG-хуки: client ban/unban, user create/delete
- Временный IP whitelist UI; CIDR presets CRUD; diff в редакторе файлов
- `FEATURE_MAINTENANCE_ENABLED`; CI eslint/pip-audit advisory

## [0.7.3] - 2026-06-08

### Added
- **Ops CLI** — `scripts/site-diagnostics.sh` + `site-diagnostics-cli.py` (systemd, uvicorn, nginx; пути AdminPanelAZ).
- **Safe Browsing CLI** — `scripts/safe-browsing-status.py`; тест `test_safe_browsing_status_cli.py`.
- **AntiZapret backup (client.sh 8)** — `antizapret_backup.py`, `node_adapter.create_antizapret_backup`, node agent `POST /backups/antizapret`, опции в `BackupTab`.
- **Runtime backup cleanup worker** — почасовая очистка `data/cidr/runtime_backups`; toggle `RUNTIME_BACKUP_CLEANUP_ENABLED`.
- **Документация** — `docs/Telegram.md` (Login, Mini App, AdminNotify, backups).

### Changed
- **`backup_scheduler.py`** — авто-бэкап AntiZapret + TG-доставка второго архива; worker runtime cleanup.
- **`MIGRATION.md`** — ops CLI ✅, backup client.sh 8 ✅, Telegram.md ✅, RUNTIME_BACKUP_CLEANUP ✅.

## [0.7.2] - 2026-06-08

### Added
- **Global API rate limiting** — `ApiRateLimitMiddleware` для `/api/*` (per-IP sliding window, memory/Redis); исключения `/api/health`, `/api/ip-blocked*`.
- **Public download rate limit** — 30 req/min per IP на `/api/public/route-download/*` (паритет AA).
- **HTTP security parity** — CORP/COOP/X-Permitted-Cross-Domain-Policies, `X-Robots-Tag` noindex, `/robots.txt`, `/.well-known/security.txt`.
- **Shared rate limit module** — `app/services/rate_limit/` (backends + `SlidingWindowLimiter`); auth/API/public-download используют общую инфраструктуру.
- **Тесты** — `test_api_rate_limit.py`; расширен `test_http_security.py` (порт AA cases).

### Changed
- **`auth_rate_limit.py`** — рефакторинг на shared sliding-window backends (поведение без изменений).
- **`MIGRATION.md`** — rate limit login ✅, global API rate limit ✅ 🆕.

## [0.6.0] - 2026-06-08

### Added
- **Feature toggles parity (UI)** — шесть недостающих app_module toggles из AdminAntizapret 1.9.0: `amneziawg`, `user_management`, `action_logs`, `system_updates`, `qr_downloads`, `vpn_network` (stub).
- **Guards** — backend middleware и frontend `FeatureGuardRoute` / `SettingsNav` / dashboard для новых модулей; AWG tab отдельно от WireGuard; QR/download/one-time links под `qr_downloads`.
- **Тесты** — расширен `test_feature_guards.py` (users, action logs, updates, QR download, WG/AWG).

### Changed
- **Журналы** — `logs_dashboard` и `action_logs` разделены: вкладки и API guards независимы.
- **MIGRATION.md** — секция Feature toggles: app_module ✅/🟡, background workers ❌ (фазы 11/16/19).

## [0.5.2] - 2026-06-08

### Added
- **Game filters** — полный каталог `GAME_FILTER_CATALOG` из AdminAntizapret 1.9.0 (~75 игр) в `backend/app/services/cidr/game_catalog.py`; единый источник для CIDR pipeline и API/UI.
- **UI** — поиск по каталогу на вкладке «Игровые фильтры» (`GameFiltersTab`).
- **Тесты** — `test_game_catalog_coverage.py` (asns/server_ips, LoL Riot Direct, масштаб каталога).

### Changed
- **CIDR pipeline** — `provider_sources.py` импортирует каталог из `game_catalog.py` вместо дублирования.

## [0.5.1] - 2026-06-08

### Added
- **Маршрутизация — Конфиг AntiZapret** — вкладка на странице «Маршрутизация» для администраторов: загрузка и редактирование параметров `setup` через `GET/PUT /api/routing/antizapret-settings`, сохранение изменений и применение через doall.sh с подтверждением.

## [0.5.0] - 2026-06-08

### Added
- **AdminNotify** — Telegram-уведомления администратору: вход, операции с конфигами, изменения настроек, бэкапы, лимиты трафика, CPU/RAM; per-user доставка на `User.telegram_id` с подписками по типам событий.
- **API** — `GET/PATCH /api/settings/admin-notify`, `POST /api/settings/admin-notify/test` для управления подписками текущего администратора.
- **UI** — вкладка Telegram в настройках: секция «Уведомления администратору» с toggles по типам событий и тестом на свой Telegram ID.
- **Тесты** — `test_admin_notify.py`, `test_traffic_limit_notify.py`, `test_admin_notify_integration.py` (login → mock Telegram).

## [0.3.0] - 2026-06-07

### Changed
- **Установка без TTY** — `install.sh` отказывается продолжать при pipe (`wget|curl | bash`) без явных флагов; README и `--help` описывают скачивание в файл и `sudo bash /tmp/install.sh` как рекомендуемый способ.
- **Документация one-liner** — README и `--help` установщика: основной способ `wget|curl | sudo bash` вместо `sudo bash <(wget …)` (process substitution недоступен процессу sudo); для root — `bash <(wget …)`; добавлено пояснение ошибки `/dev/fd/63`.
- **UX/UI установщика** — общий модуль `scripts/install-ui.sh`: баннер с версией, цвета (NO_COLOR/TTY), info/warn/error/success, меню и шаги мастера «Шаг N/M», сводка, прогресс длительных операций, улучшенные `--help` и экран завершения установки.
- **UX/UI установщика** — рамки и иконки переведены на ASCII (`+`, `-`, `|`, `[i]`, `[!]`) вместо Unicode box-drawing; исправлены «ромбики с ?» в PuTTY и Windows SSH при включённых ANSI-цветах.
- **Мастер установки** — убран вариант «Полный стек»; AntiZapret не входит в установку AdminPanelAZ — путь фиксирован `/root/antizapret`, без интерактивного вопроса; при отсутствии каталога — предупреждение или прерывание (для режимов с VPN).
- **Мастер установки** — каталоги состояния controller и node agent больше не спрашиваются; используются значения по умолчанию (`/var/lib/adminpanelaz`, `/var/lib/adminpanelaz-node` при systemd).

### Added
- **Флаг `--node-only`** — неинтерактивная установка только node agent на VPN-сервере (`--node-only --with-systemd`); без TTY pipe-установка требует явных флагов.
- **One-liner установка** — `install.sh` при запуске через `wget`/`curl` и pipe (`wget | sudo bash`, `curl | sudo bash`, от root — `bash <(wget …)`) автоматически клонирует репозиторий в `/opt/AdminPanelAZ` и перезапускает мастер; команды и `INSTALL_FROM_GIT` / `INSTALL_TARGET` описаны в README.
- **Удаление и переустановка в `install.sh`** — меню при запуске без аргументов (новая установка / переустановка / полное удаление / справка); флаги `--uninstall`, `--purge`, `--reinstall`; переустановка с резервной копией `.env` в `.reinstall-backup/`; делегирование в `scripts/uninstall.sh`.
- **Расширенный `scripts/uninstall.sh`** — опции `--purge`, `--remove-nginx`, `--remove-firewall`, `--remove-env`, `--remove-system-config`, подтверждение `yes`/`AdminPanelAZ`; удаление DDNS timer, nginx, ufw-правил AdminPanelAZ; данные AntiZapret не затрагиваются.

### Fixed
- **Модальные формы и диалоги** — нативная HTML5-валидация (`required`, `type="email"` и т.д.) больше не блокирует отправку форм в модальных окнах без видимой обратной связи: `noValidate`, JS-валидация с toast-уведомлениями, единые паттерны submit в `ConfirmDialog` и `ConfirmActionDialog`, защита от закрытия диалога во время загрузки (`onOpenChange`), закрытие диалогов перед перезагрузкой данных при успехе. Затронуты NodesPage (добавление/редактирование/удаление/ротация ключей), DashboardPage, ClientActionsDialog, ConfigCardsSection, NodeUpdateDialog, EditFilesPage, ForcePasswordChange, SettingsPage, UsersTab, PersonalTab, TwoFactorTab.

## [0.2.0] - 2026-06-07

### Added
- **Ресурсы панели AdminPanelAZ** — фоновый сбор CPU/RAM процессов backend (uvicorn/FastAPI) на машине контроллера (`panel_resource_sample`), API `GET /api/monitoring/panel-resource-history` и `GET /api/monitoring/panel-resource-current` (только admin); вкладка «Панель» в NOC Мониторинг с графиками и live-карточками; настройки `PANEL_RESOURCE_METRICS_*`. Frontend в production — статика через backend (отдельного процесса нет).
- **История ресурсов в NOC Мониторинг** — фоновый сбор CPU/RAM/диска/load average по каждому узлу (`node_resource_sample`), API `GET /api/monitoring/resource-history` и `GET /api/nodes/{id}/resource-history` с периодами 1/7/30 дней; вкладка «VPN-узел» на странице мониторинга с графиками Recharts; настройки `RESOURCE_METRICS_*`.
- **DDNS в мастере установки** — шаг 3a в `install-wizard.sh`: DuckDNS (поддомен + token) и No-IP (hostname + учётные данные); автозаполнение домена для Let's Encrypt; `scripts/ddns-update.sh` и systemd timer `adminpanelaz-ddns.timer` (обновление IP каждые 5 мин); конфиг `/etc/adminpanelaz/ddns.env`.
- **README: бесплатные домены и единый путь установки** — сравнение DuckDNS, No-IP, FreeDNS, Dynu, deSEC, Cloudflare; подробный пошаговый разбор `sudo ./install.sh` как единственного способа установки; раздел «Работа с узлами и конфигурациями» (per-node scope, синхронизация, типичные ошибки); post-install утилиты отделены от установки.
- **Единый интерактивный `install.sh`** — все вопросы установки в одном мастере (controller/node, порты, Nginx/HTTPS, firewall, администратор, node agent, Telegram и др.); режим `--non-interactive` и флаги для CI; служебные скрипты `install-wizard.sh`, `install-systemd.sh`, `install-node-systemd.sh` вызываются из мастера.
- **Nginx-only установка и firewall** — backend по умолчанию на `127.0.0.1`, публикация через Nginx (рекомендуемый путь); настраиваемые порты backend/node/HTTPS/HTTP; опциональная настройка ufw/iptables (`scripts/firewall-setup.sh`); шаблоны `deploy/nginx/`, утилиты `scripts/nginx-setup.sh`, `scripts/nginx-common.sh`, `scripts/env_defaults.sh`.
- **Refresh-токены** — короткий access JWT + refresh в httpOnly cookie, ротация при обновлении сессии; настройки TTL и cookie в `.env` (см. `SECURITY.md`).
- **2FA (TOTP)** — включение для администраторов, резервные коды; вкладка в настройках, двухшаговый вход в UI.
- **Rate limit входа через Redis** — `AUTH_RATE_LIMIT_BACKEND=redis` и `REDIS_URL` для нескольких uvicorn workers; fallback на in-memory.
- **mTLS панель ↔ node agent** — опционально для вызовов панели к агенту; генерация сертификатов `scripts/generate-mtls-certs.sh`.
- **Ротация API-ключей узлов** — вручную на странице «Узлы» и по расписанию (`NODE_API_KEY_ROTATION_DAYS`); синхронизация ключа в env агента.
- **Обновление узла из панели** — на странице «Узлы» кнопка обновления (git pull) для node agent и/или AntiZapret на удалённом или локальном VPN-сервере; API `GET/POST /api/nodes/{id}/updates|update`, endpoints node agent `/system/updates` и `/system/update`; UI `NodeUpdateDialog`.
- **Переключатели модулей (feature toggles)** — реестр фоновых задач и разделов приложения, API и вкладка в настройках; маршруты с `FeatureGuardRoute`.
- **Мониторинг здоровья узлов** — фоновый worker и единый payload health для локального адаптера и node agent.
- **Лимиты трафика клиентов** — согласование лимитов с узлами (`traffic_limit`, reconcile).
- **Uvicorn workers** — `UVICORN_WORKERS` в `start.sh`/systemd; подсказка про Redis rate limit при workers > 1.
- **Единый UI-кит диалогов и уведомлений** — компоненты `AppDialog`, `ConfirmDialog`, хук `useConfirmDialog`, `SettingsAlert`, обновлённые `Toast` и `InlineProgressBar`; единый стиль подтверждений и прогресса на всех страницах.
- **Переработка настроек** — боковая навигация `SettingsNav`, отдельные вкладки `PersonalTab`, `UsersTab`, `SecurityTab`, `TwoFactorTab`, `FeatureTogglesTab`, `BackupTab`, `MaintenanceTab`, `TelegramTab`, `TestsTab`, `UpdatesTab`.
- Отображение версий `agent` и AntiZapret (`az`) в таблице узлов.
- Тесты: `test_security.py`, `test_node_update.py`, `test_node_health.py`, `test_feature_guards.py`, `test_node_scoping.py`, `test_node_adapter_parity.py`, `test_resource_metrics.py`, `test_panel_resource_metrics.py`.
- Статика Telegram Mini App в `backend/app/static/tg_mini/`.

### Changed
- **Полный UX/UI редизайн** — единый визуальный язык (карточки, заголовки, бейджи узла, состояния offline/unknown) на страницах Конфигурации, Узлы, Трафик, Журналы, Редактор файлов, NOC Мониторинг, Мониторинг сервера, Маршрутизация и Настройки.
- **ClientActionsDialog** — переработанный диалог действий с клиентом: группировка операций, иконки, подтверждения через `ConfirmDialog`, индикация прогресса.
- **Установка и документация** — README описывает единый `install.sh`, Nginx/HTTPS, DDNS, firewall, `SECURITY.md` и минимальный production `.env`; `uninstall.sh` расширен.
- Node agent version bumped to **1.1.0** (endpoint обновления).
- Срок жизни access JWT по умолчанию **30 минут** (refresh для длительной сессии).
- Расширены политики доступа, client access, tg mini и dashboard под мульти-узловую модель.
- NOC Мониторинг: вкладки «VPN-узел» и «Панель», явная привязка данных к активному узлу, предупреждения при offline/unknown.

### Fixed
- **Мульти-узловая изоляция данных** — аудит node-scoping по всем модулям:
  - `vpn_configs`: `node_id`, миграция, фильтрация API и перезагрузка Dashboard при смене узла.
  - `openvpn_access_policy` / `wg_access_policy`: добавлен `node_id`, миграция, запросы и reconcile лимитов трафика только для активного/целевого узла.
  - Frontend: перезагрузка данных при смене активного узла на страницах Dashboard, Monitoring, Traffic, Routing, Logs, EditFiles, ServerMonitor, Settings.
  - Seed БД при старте: новые клиенты привязываются к `node_id` активного узла.
- **Синхронизация node → panel** — данные с удалённых VPN-узлов корректно передаются на панель:
  - traffic worker: исправлен вызов `get_adapter_for_node(node)` (фоновый сбор трафика по всем узлам).
  - server monitor: метрики CPU/RAM/vnStat и bandwidth проксируются через node agent (`/server-monitor/*`), а не только с хоста контроллера.
  - node agent: расширенный `/health` (версии, службы, IP), endpoints мониторинга, WireGuard block/unblock, OpenVPN disconnect.
  - edit files и game filters: чтение/запись конфигов выполняется на активном узле через adapter, а не локально на контроллере.
  - settings: `antizapret_path` берётся из метаданных активного узла.
  - NodesPage: отображение IP сервера и состояния служб из health-метаданных.
- **NOC Мониторинг** — метрики и история ресурсов собираются с активного узла, а не с хоста контроллера; корректное отображение при недоступном node agent.

### Security
- **Усиление безопасности для сетевого развёртывания** — проверка секретов в `APP_ENV=production`, rate limit на auth, HTTP security headers (middleware, CSP, HSTS, X-Frame-Options), политика паролей, аудит чувствительных действий, constant-time проверка `X-Node-Key` на node agent, опциональный IP allowlist агента; документация в `SECURITY.md`.

## [0.1.0] - 2025-06-07

### Added
- Экспериментальный порт AdminAntizapret на FastAPI + React (TypeScript, Vite, Tailwind, shadcn/ui).
- Controller + Nodes с node agent, CIDR/routing pipeline, бэкапы, журналы, безопасность, мониторинг.
- Production-развёртывание: `install.sh`, daemon/watchdog, systemd, раздача UI из backend в prod-режиме.
- OpenVPN management sockets, vnStat, WebSocket-мониторинг, Telegram Mini App, in-panel pytest.

[Unreleased]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.9.0...v2.0.0
[1.9.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.4.3...v1.5.0
[1.4.3]: https://github.com/Kirito0098/AdminPanelAZ/compare/v1.4.2...v1.4.3
[0.3.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Kirito0098/AdminPanelAZ/releases/tag/v0.1.0
