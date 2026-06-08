# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where applicable.

## [Unreleased]

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

[Unreleased]: https://github.com/Kirito0098/AdminPanelAZ/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Kirito0098/AdminPanelAZ/releases/tag/v0.1.0
