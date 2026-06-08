# Статус переноса из AdminAntizapret

> **Baseline:** [AdminAntizapret](https://github.com/Kirito0098/AdminAntizapret) **1.9.0** → AdminPanelAZ **0.3.0**
> **Обновлено:** 2026-06-08
> **Источник для сравнения:** `/opt/AdminAntizapret` (Flask + Jinja2) · **Цель:** `/opt/AdminPanelAZ` (FastAPI + React)

AdminPanelAZ — экспериментальный порт веб-панели AdminAntizapret. На данный момент для production по-прежнему рекомендуется upstream **AdminAntizapret**. Этот документ фиксирует, что уже перенесено, что перенесено частично и что ещё предстоит перенести.

---

## Легенда

| Маркер | Значение |
|--------|----------|
| ✅ | **Перенесено** — функциональность есть, API и UI работают |
| 🟡 | **Частично** — упрощённый порт, подмножество возможностей или без UI |
| ❌ | **Не перенесено** — отсутствует в AdminPanelAZ |
| 🆕 | **Новое** — есть только в AdminPanelAZ (не было в AdminAntizapret) |

---

## Как обновлять этот документ

1. При переносе модуля из AdminAntizapret — перенести строку из ❌/🟡 в ✅ и обновить «Карту соответствия».
2. При упрощённом порте — оставить 🟡 с пояснением, чего не хватает.
3. Обновить поле **Обновлено** и при релизе — baseline-версию AdminPanelAZ.
4. Новую функциональность, которой не было в AA, добавлять в секцию «🆕 Новое».

---

## Сводная таблица

| Область | Статус | Комментарий |
|---------|--------|-------------|
| VPN-клиенты (OpenVPN, WireGuard, AmneziaWG) | ✅ | CRUD через `client.sh`, sync, download, QR |
| Политики доступа (блок, срок, лимиты) | ✅ | OpenVPN + WG/AWG |
| Синхронизация и графики трафика | ✅ | Фоновый collector + страница «Мониторинг трафика» |
| Лимиты трафика (reconcile) | ✅ | Без TG-уведомлений при превышении (🟡 notify) |
| Маршрутизация / CIDR | 🟡 | Pipeline, провайдеры, presets, games; вкладка «Конфиг AntiZapret» — ✅ |
| Редактор файлов AntiZapret | ✅ | Мультифайловый редактор + apply |
| Мониторинг сервера (CPU/RAM/vnstat/WS) | ✅ | Страница «Сервер» |
| NOC / подключённые клиенты / логи | ✅ | Monitoring + Logs |
| Безопасность (IP whitelist, scanner) | 🟡 | Упрощённый `security.py` |
| QR / одноразовые ссылки | ✅ | Настройки в SecurityTab (не отдельная вкладка) |
| Бэкапы (ручные + авто + TG) | ✅ | Без AntiZapret `client.sh 8` как отдельной опции в UI |
| Feature toggles | 🟡 | ~12 toggles vs больше в AA 1.9.0 |
| Telegram Login + Mini App | ✅ | |
| Telegram admin-уведомления | ✅ | AdminNotify + traffic_limit + CPU/RAM; UI подписок в TelegramTab |
| Auth (login, captcha, роли) | ✅ | + 🆕 2FA/TOTP, refresh tokens |
| Viewer role | ✅ | API, ограничения и UI назначения доступа в UsersTab |
| Журнал действий | ✅ | Просмотр и экспорт CSV |
| Обновление системы (git) | ✅ | Панель + 🆕 node agent / AntiZapret на узлах |
| In-panel pytest | 🟡 | 28 модулей vs 53 в AA |
| Установка / ops | 🟡 | `install.sh` + scripts; нет `adminpanel.sh`, diagnostics CLI |
| Multi-node | 🆕 | Controller + Node Agent |
| CI/CD | 🟡 | `.github/workflows/ci.yml`; `.pre-commit-config.yaml` (ruff, shellcheck) |

---

## Архитектура

```mermaid
flowchart LR
  subgraph legacy [AdminAntizapret]
    Flask[Flask_Monolith]
    Flask --> AZ1["/root/antizapret"]
  end
  subgraph current [AdminPanelAZ]
    React[React_SPA]
    Panel[FastAPI_Controller]
    Agent[Node_Agent]
    React --> Panel
    Panel --> Local[LocalNodeAdapter]
    Panel --> Remote[RemoteNodeAdapter]
    Local --> AZ2["/root/antizapret_local"]
    Remote --> Agent
    Agent --> AZ3["/root/antizapret_remote"]
  end
```

---

## Детально по разделам

### 1. VPN-клиенты

| Функция | AA 1.9.0 | AZ 0.3.0 | Статус |
|---------|----------|----------|--------|
| Создание / удаление OpenVPN | `ScriptExecutor` → `client.sh` | `antizapret.py` + `node_adapter.py` | ✅ |
| Создание / удаление WireGuard | то же | то же | ✅ |
| AmneziaWG (профили, вкладка) | index + config routes | `DashboardPage`, `ConfigCardsSection` | ✅ |
| Синхронизация списка с диском | index routes | `POST /api/configs/sync` | ✅ |
| Скачивание профилей | config routes | configs router | ✅ |
| QR-коды | `QRGenerator` | configs + qr endpoints | ✅ |
| Одноразовые ссылки | `QrDownloadService` | `qr_download.py`, `public_download.py` | ✅ |
| Продление сертификата OpenVPN | client actions | `ClientActionsDialog` | ✅ |
| Переключение OpenVPN UDP/TCP группы | `/set_openvpn_group` | `PUT /api/configs/openvpn-group`, `ConfigCardsSection` | ✅ |
| Публичные route-файлы (Keenetic, MikroTik, TP-Link) | `/public_download/<router>` | `GET /api/public/route-download/{router}` | ✅ |
| Toggle public download | `/toggle_public_download` | `POST /api/security/public-download`, `SecurityTab` | ✅ |
| `client.sh` в репозитории | ships `client.sh` | использует AntiZapret на сервере | — |

### 2. Политики доступа

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Временная / постоянная блокировка OpenVPN | `OpenVpnAccessPolicyService` | `access_policy.py` | ✅ |
| Блокировка WG/AWG + runtime | `WgAccessPolicyService`, `wg_awg_runtime_apply.py` | `access_policy.py`, `wg_runtime.py`, `wg_policy_sync_worker.py` | ✅ |
| Срок действия WG | WG policy | `client_access.py` | ✅ |
| Лимиты трафика (1/7/30 дней) | `traffic_limit.py` | `traffic_limit.py` | ✅ |
| Reconcile после sync | `traffic_limit_reconcile.py` | `traffic_limit_reconcile.py` | ✅ |
| TG-уведомление при превышении лимита | `traffic_limit_notify.py` | `traffic_limit_notify.py` | ✅ |
| OpenVPN banlist (`banned_clients`) | `OpenVPNBanlistService` | `openvpn_management.py` | ✅ |

### 3. Трафик и мониторинг

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Сбор статистики в SQLite | `utils/traffic_sync.py` | `traffic/collector.py` | ✅ |
| Графики per-client | traffic chart | `traffic/chart.py`, `TrafficPage.tsx` | ✅ |
| Подключённые клиенты (live) | `logs_dashboard/` | `MonitoringPage.tsx` | ✅ |
| OpenVPN events / sockets | logs routes | `LogsPage.tsx`, `logs.py` | ✅ |
| Сброс / очистка трафика | logs dashboard POST | `traffic.py` | ✅ |
| CPU/RAM + vnstat + WebSocket | `server_monitor/` | `server_monitor.py`, `ServerMonitorPage.tsx` | ✅ |
| TG-алерты CPU/RAM | AdminNotify | `admin_notify.py` + metrics workers | ✅ |
| NOC: метрики узла + панели | — | `MonitoringPage.tsx`, resource samples | 🆕 |
| История CPU/RAM (node + panel) | — | `node_resource_sample`, `panel_resource_sample` | 🆕 |

### 4. Маршрутизация и CIDR

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Обзор маршрутизации | `/routing` | `RoutingPage.tsx` | ✅ |
| Провайдеры CIDR | cidr routes | `ProvidersTab`, `cidr/ip_manager.py` | ✅ |
| CIDR DB pipeline (refresh/generate) | cidr_db APIs | `cidr_db.py`, `CidrPipelineTab` | ✅ |
| Antifilter.net sync | antifilter API | `cidr_db.py` | ✅ |
| Пресеты CIDR | presets API | `PresetsTab` | ✅ |
| Game filters | полный `GAME_FILTER_CATALOG` | `game_catalog.py` (~75 игр, AA 1.9.0) | ✅ |
| Route-файлы (include/exclude IPs) | routing files | `FilesTab` | ✅ |
| run-doall / apply | `/run-doall` | `POST /api/routing/apply` | ✅ |
| Вкладка «Конфиг AntiZapret» | `get/update_antizapret_settings`, schema | `AntizapretConfigTab`, `GET/PUT /api/routing/antizapret-settings` | ✅ |
| Nightly CIDR DB refresh cron | cron + updater | `cidr_scheduler.py` (worker) | ✅ |

### 5. Редактор файлов

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Domains (include/exclude/remove hosts) | `edit_files/` | `EditFilesPage.tsx`, `file_editor.py` | ✅ |
| IP/routing files | то же | то же | ✅ |
| Adblock hosts | то же | то же | ✅ |
| Security allow/deny IPs | то же | то же | ✅ |
| Apply + doall | POST handlers | `edit_files.py` | ✅ |
| Diff-подсветка | JS diff module | React editor | ✅ |

### 6. Безопасность и доступ

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Роли admin / viewer | `auth_manager.py` | `UserRole`, JWT | ✅ (+ 🆕 role `user`) |
| Captcha на login | captcha routes | `auth.py` | ✅ |
| IP allow-list (permanent) | `ip_restriction.py` | `security.py` | ✅ |
| Временный whitelist (1h/12h/24h) | temporary whitelist store | `ip_restriction.py` | ✅ |
| Scanner auto-block (ipset/iptables) | scanner store | `scanner_firewall_store.py` | ✅ |
| CSRF / CSP / security headers | `http_security.py` | middleware | ✅ |
| Rate limit login | Flask-Limiter (+ Redis) | auth rate limit (+ Redis для workers) | 🟡 |
| Глобальный rate limit API | Flask-Limiter | — | ❌ |
| 2FA / TOTP | — | `TwoFactorTab`, TOTP columns | 🆕 |
| IP blocked dwell page | `ip_blocked/` | `ip_blocked.py` | ✅ |
| Session heartbeat | `/api/session-heartbeat` | — | ❌ |
| Active session tracking | `ActiveWebSessionService` | — | ❌ |
| Nightly idle restart | `nightly_idle_restart.py` | — | ❌ |

### 7. Бэкапы и обслуживание

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Ручной бэкап (DB + .env + data) | `BackupManagerService` | `backups.py` | ✅ |
| Авто-бэкап по расписанию | `app_auto_backup.py` | `backup_scheduler.py` | ✅ |
| Restore / retention / delete | backup API | `backups.py` | ✅ |
| TG-доставка архивов | `backup_telegram_job.py` | `backup_scheduler.py`, `backups.py` | ✅ |
| Бэкап AntiZapret (`client.sh 8`) | `AntizapretBackupService` | опционально через lists на узле | 🟡 |
| run-doall | maintenance | `maintenance.py` | ✅ |
| recreate profiles (`client.sh 7`) | settings | `settings.py` | ✅ |
| Restart service | admin routes | `maintenance.py` | ✅ |
| Runtime backup cleanup cron | cron job | — | ❌ |

### 8. Telegram

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Telegram Login Widget | auth routes | `auth.py` | ✅ |
| Telegram Mini App | `tg_mini/` | `tg_mini.py`, static assets | ✅ |
| Отправка конфига в TG (Mini App) | tg_mini API | `tg_mini.py` | ✅ |
| AdminNotify (login, client ops, settings) | `admin_notify.py` | `admin_notify.py` | ✅ |
| CPU/RAM alerts в TG | AdminNotify | `admin_notify.py` + metrics workers | ✅ |
| Traffic limit alerts в TG | `traffic_limit_notify.py` | `traffic_limit_notify.py` | ✅ |
| Тест TG-сообщения | settings API | `maintenance.py` | ✅ |
| `Telegram.md` (документация) | отдельный файл | частично в README | 🟡 |

### 9. Настройки и администрирование

| Функция | AA | AZ | Статус |
|---------|----|----|--------|
| Управление пользователями | settings users tab | `UsersTab.tsx` | ✅ |
| Viewer config access UI | users tab | `UsersTab.tsx` + `/api/system/viewer-access` | ✅ |
| Feature toggles UI | settings tab | `FeatureTogglesTab.tsx` | 🟡 |
| QR-настройки (TTL, PIN, max downloads) | отдельная вкладка | `SecurityTab.tsx` | 🟡 |
| VPN-сеть (порт, HTTPS, Nginx из UI) | `_tab_vpn_network.html` | nginx через `install.sh` / `nginx-setup.sh` | 🟡 |
| Журнал действий (просмотр) | action logs | `LogsPage.tsx` | ✅ |
| Экспорт action logs CSV | `/api/settings/action-logs/export` | `GET /api/logs/action-logs/export` | ✅ |
| Обновление панели (git) | `/update_system` | `UpdatesTab.tsx`, `system.py` | ✅ |
| In-panel pytest | `api_tests.py` | `TestsTab.tsx`, `tests.py`, `backend/tests/` (28 модулей) | 🟡 |
| Обновление node agent + AntiZapret | — | `NodeUpdateDialog`, `nodes.py` | 🆕 |

### 10. Feature toggles (сравнение)

| Toggle (AA 1.9.0) | В AZ | Статус |
|-------------------|------|--------|
| `TRAFFIC_SYNC_ENABLED` | `traffic_sync` | ✅ |
| `MONITOR_ENABLED` | `resource_monitor` | ✅ |
| `FEATURE_OPENVPN_ENABLED` | `openvpn` | ✅ |
| `FEATURE_WIREGUARD_ENABLED` | `wireguard` | ✅ |
| `FEATURE_AMNEZIAWG_ENABLED` | `amneziawg` | ✅ |
| `FEATURE_LOGS_DASHBOARD_ENABLED` | `logs_dashboard` | ✅ |
| `FEATURE_SERVER_MONITOR_ENABLED` | `server_monitor` | ✅ |
| `FEATURE_ROUTING_ENABLED` | `routing` | ✅ |
| `FEATURE_EDIT_FILES_ENABLED` | `edit_files` | ✅ |
| `FEATURE_TELEGRAM_ENABLED` | `telegram` | ✅ |
| `FEATURE_BACKUPS_ENABLED` | `backups` | ✅ |
| `FEATURE_USER_MANAGEMENT_ENABLED` | `user_management` | ✅ |
| `FEATURE_SECURITY_ENABLED` | `security` | ✅ |
| `FEATURE_ACTION_LOGS_ENABLED` | `action_logs` | ✅ |
| `FEATURE_SYSTEM_UPDATES_ENABLED` | `system_updates` | ✅ |
| `FEATURE_DIAGNOSTICS_TESTS_ENABLED` | `diagnostics_tests` | ✅ |
| `FEATURE_QR_DOWNLOADS_ENABLED` | `qr_downloads` | ✅ |
| `FEATURE_VPN_NETWORK_ENABLED` | `vpn_network` (stub UI) | 🟡 |
| `WG_POLICY_SYNC` (background) | cron `wg_awg_policy_sync.py` | `wg_policy_sync_worker.py` (async loop) | ✅ |
| `ACTIVE_SESSION_TRACKING` (background) | — | ❌ |
| `NIGHTLY_IDLE_RESTART` (background) | — | ❌ |
| `RUNTIME_BACKUP_CLEANUP` (background) | — | ❌ |

> **Feature toggles (фаза 10):** UI parity для app_module toggles ✅; фоновые workers WG_POLICY_SYNC ✅; ACTIVE_SESSION_TRACKING / NIGHTLY_IDLE_RESTART / RUNTIME_BACKUP_CLEANUP — фазы 16/19.

### 11. Установка и ops

| Компонент | AA | AZ | Статус |
|-----------|----|----|--------|
| One-liner install | `install.sh` | `install.sh` (+ pipe guard) | ✅ |
| Интерактивный мастер | `adminpanel.sh --install` | `install.sh` wizard | ✅ |
| Консольное меню (`adminpanel.sh`) | restart/update/backup/tests | `start.sh`, systemd | 🟡 |
| SSL / Nginx setup | `ssl_setup.sh` | `scripts/nginx-setup.sh` | ✅ |
| Firewall panel port | `panel_port_firewall.py` | `scripts/firewall-setup.sh` | 🟡 |
| Uninstall / reinstall | `uninstall.sh` | `scripts/uninstall.sh` + menu | ✅ |
| Site diagnostics CLI | `site_diagnostics.sh` | — | ❌ |
| Safe Browsing status CLI | `safe_browsing_status_cli.py` | — | ❌ |
| env defaults | `env_defaults.sh` | `scripts/env_defaults.sh` (sync AA 1.9.0) | ✅ |
| CI (pytest, ruff, shellcheck, eslint) | `.github/workflows/ci.yml` | `.github/workflows/ci.yml` (без eslint) | 🟡 |
| pre-commit hooks | `.pre-commit-config.yaml` | `.pre-commit-config.yaml` (ruff, shellcheck) | 🟡 |

### 12. UI / UX

| Аспект | AA | AZ | Статус |
|--------|----|----|--------|
| Рендеринг | Jinja2 + vanilla JS | React SPA (Vite, Tailwind, shadcn/ui) | 🆕 |
| Тёмная тема | CSS | Tailwind dark | ✅ |
| Mobile / Telegram Mini App | tg_mini templates | static tg_mini | ✅ |
| Прогресс фоновых задач (doall/update) | BackgroundTaskService | BackgroundTaskService + GET /api/tasks/{id} | ✅ |
| Multi-node selector | — | `NodeSelector`, `NodesPage` | 🆕 |

---

## 🆕 Новое в AdminPanelAZ

Функциональность, которой **не было** в AdminAntizapret 1.9.0:

- **Multi-node architecture** — Controller + Node Agent ([`backend/app/routers/nodes.py`](backend/app/routers/nodes.py), [`backend/node_agent/main.py`](backend/node_agent/main.py))
- **NOC-мониторинг** — вкладки VPN-узел / панель ([`frontend/src/pages/MonitoringPage.tsx`](frontend/src/pages/MonitoringPage.tsx))
- **2FA/TOTP** и refresh tokens ([`backend/app/routers/auth.py`](backend/app/routers/auth.py), [`frontend/src/components/settings/TwoFactorTab.tsx`](frontend/src/components/settings/TwoFactorTab.tsx))
- **Обновление node agent и AntiZapret** с панели ([`frontend/src/components/NodeUpdateDialog.tsx`](frontend/src/components/NodeUpdateDialog.tsx))
- **Resource metrics history** — CPU/RAM samples для узлов и controller
- **mTLS** panel ↔ agent ([`scripts/generate-mtls-certs.sh`](scripts/generate-mtls-certs.sh))
- **DDNS timer** (DuckDNS / No-IP)
- **Per-node scoping** в БД — `vpn_configs`, access policies привязаны к `node_id` ([`backend/app/database.py`](backend/app/database.py))
- **React SPA** вместо server-rendered Jinja2
- **Роль `user`** (между admin и viewer) в модели пользователей

---

## Карта соответствия файлов (AA → AZ)

| AdminAntizapret | AdminPanelAZ | Примечание |
|-----------------|--------------|------------|
| `core/services/access_policy.py` (OVPN/WG) | `backend/app/services/access_policy.py` | ported 1.9.0 |
| `core/services/traffic_limit.py` | `backend/app/services/traffic_limit.py` | ported 1.9.0 |
| `utils/traffic_limit_reconcile.py` | `backend/app/services/traffic_limit_reconcile.py` | ported 1.9.0 |
| `utils/traffic_sync.py` | `backend/app/services/traffic/collector.py` | ported |
| `core/services/file_editor.py` | `backend/app/services/file_editor.py` | ported |
| `core/services/env_file.py` | `backend/app/services/env_file.py` | ported |
| `core/services/feature_toggles.py` | `backend/app/services/feature_toggles.py` | ported 1.9.0 |
| `core/services/feature_guards.py` | `backend/app/services/feature_guards.py` | parity 1.9.0 |
| `core/services/ip_restriction.py` | `backend/app/services/ip_restriction.py` | ported |
| `core/services/scanner_firewall_store.py` | `backend/app/services/scanner_firewall_store.py` | ported |
| `core/services/security.py` | `backend/app/services/security.py` | simplified |
| `core/services/server_monitor.py` | `backend/app/services/server_monitor.py` | ported |
| `core/services/openvpn_management.py` | `backend/app/services/openvpn_management.py` | ported |
| `core/services/wg_awg_runtime_enforcer.py` | `backend/app/services/wg_runtime.py` | ported (syncconf fallback) |
| `core/services/qr_download*.py` | `backend/app/services/qr_download.py` | ported |
| `utils/app_auto_backup.py` | `backend/app/services/backup_scheduler.py` | ported |
| `core/services/background_tasks.py` | `backend/app/services/background_tasks.py` | ported (phase 14) |
| `core/services/cidr/*` | `backend/app/services/cidr/*` | ported |
| `ips/ip_manager.py` | `backend/app/services/cidr/ip_manager.py` | ported |
| `core/services/game_catalog.py` | `backend/app/services/cidr/game_catalog.py` | full catalog (AA 1.9.0) |
| `tg_mini/` | `backend/app/routers/tg_mini.py` + static | ported |
| `routes/settings/api_tests.py` | `backend/app/routers/tests.py` | ported |
| `ip_blocked/` | `backend/app/routers/ip_blocked.py` | ported |
| `script_sh/env_defaults.sh` | `scripts/env_defaults.sh` | synced 1.9.0 |
| `script_sh/ssl_setup.sh` | `scripts/nginx-setup.sh`, `nginx-common.sh` | patterned |
| `app.py` (Flask monolith) | `backend/app/main.py` + routers | restructured |
| `templates/` + `static/` | `frontend/src/` | full rewrite React |
| `core/services/admin_notify.py` | `backend/app/services/admin_notify.py` | service ported (hooks pending) |
| `routes/settings/antizapret.py` | — | not ported |
| `utils/nightly_idle_restart.py` | — | not ported |
| `utils/wg_awg_runtime_apply.py` | `wg_runtime.py` + `wg_policy_sync_worker.py` | inline, no standalone CLI |
| `script_sh/adminpanel.sh` | `install.sh`, `start.sh`, systemd | different UX |

---

## Backlog переноса (приоритеты)

### Высокий приоритет

1. **Полный game filter catalog** + тест покрытия

**Сделано (0.5.2):** UI viewer config access — назначение групп конфигов в `UsersTab`.

**Сделано (0.5.1):** вкладка «Конфиг AntiZapret» на маршрутизации (`AntizapretConfigTab`).

**Сделано (0.5.0):** AdminNotify (login, client ops, settings, CPU/RAM, traffic limits) + UI подписок в TelegramTab.

### Средний приоритет

6. Feature toggles parity — `FEATURE_AMNEZIAWG_ENABLED`, `FEATURE_VPN_NETWORK_ENABLED`, background jobs
7. ~~**Экспорт action logs CSV**~~ — **Сделано (0.6.2):** `GET /api/logs/action-logs/export`
8. **Публичные route-файлы** для роутеров (Keenetic, MikroTik, TP-Link)
9. **OpenVPN UDP/TCP group switching**
10. ~~**WG policy sync cron** (`wg_awg_runtime_apply` как worker/CLI)~~ — **Сделано (0.6.1):** `wg_policy_sync_worker.py`
11. **CI pipeline** — pytest, ruff, frontend build

### Низкий приоритет

12. Session heartbeat + active session tracking + nightly idle restart
13. **VPN-сеть** — управление HTTPS/Nginx из UI (сейчас через scripts)
14. **Site diagnostics CLI** и **Safe Browsing status CLI**
15. **adminpanel.sh**-style console menu (опционально)
16. **Telegram.md** — отдельная документация
17. Расширение test suite до паритета с AA (~53 модуля)
18. Global API rate limiting (Flask-Limiter equivalent)
19. ~~**BackgroundTaskService** — единый прогресс для doall/update/restart~~ ✅ (0.6.4)

---

## Тестирование паритета

| Область | AA tests | AZ tests | Статус |
|---------|----------|----------|--------|
| Общее покрытие | ~53 pytest modules | 28 modules | 🟡 |
| Node adapter local/remote | — | `test_node_adapter_parity.py` | 🆕 |
| Feature guards | `test_feature_toggles.py` | `test_feature_guards.py` | ✅ |
| Security / IP restriction | multiple | `test_security.py` | 🟡 |
| Node scoping | — | `test_node_scoping.py` | 🆕 |

---

## Связанные документы

- [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) — поэтапный план (20 фаз), промпты для Cursor, режимы агента
- [`README.md`](README.md) — установка, multi-node, статус проекта
- [`CHANGELOG.md`](CHANGELOG.md) — история версий AdminPanelAZ
- [`SECURITY.md`](SECURITY.md) — hardening, JWT, rate limits, mTLS
