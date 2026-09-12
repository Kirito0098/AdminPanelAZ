# Expand Feature Toggles (Разделы панели)

**Дата:** 2026-09-12  
**Статус:** implemented  
**Ветка:** `feature/client-portal`  
**Подход:** расширить явный реестр `FEATURE_TOGGLES` (не автогенерация, не UI-only hide)

## Контекст

Панель перегружена для части операторов: они выключают по 2–3 модуля вручную, чего недостаточно. Уже есть тогглы `app_module` / `background` и профили ресурсов (Minimal / Standard / Full), но:

- часть пунктов меню и настроек **нельзя** выключить (например **Узлы**, **Операции панели**);
- многие фоновые воркеры уже gated через env/settings, но **не видны** в «Разделах панели».

## Цели

1. Полный аудит: всё, что можно безопасно выключить, появляется в UI как тоггл.  
2. Один релиз: и **Раздел приложения**, и **Фоновая задача**.  
3. Новые тогглы: **default = on** (upgrade не меняет поведение).  
4. Выключение = UI + API (+ воркер), по текущему паттерну панели.

## Always-on (не тогглы)

Нельзя отключить и не показывать в списке:

- аутентификация / сессия;
- страница **Конфигурации** (`/`);
- **Настройки → личное**;
- **Настройки → Разделы панели** (`modules`).

Restart/rebuild, открытый из баннера после сохранения модулей, остаётся доступен (не зависит от `panel_ops`).

## Вне скоупа

- Пресеты «Только VPN» / мастер первого входа.  
- Автогенерация тогглов из nav/workers.  
- UI-only hide без API/воркер gate.  
- Замена профилей ресурсов отдельной моделью «сложности UI».

## Инвентарь — новые `app_module`

| key | UI | API / notes |
|-----|-----|-------------|
| `nodes` | Меню **Узлы** (`/nodes`) | См. особый случай ниже: `/api/nodes` в `ALWAYS_ALLOWED` |
| `panel_ops` | Настройки → **Операции панели** | Endpoints rebuild/restart панели, относящиеся к этой вкладке |

Существующие модули (OpenVPN, WG, routing, telegram, backups, security, unlock, portal, …) **не дублировать**.

## Инвентарь — новые `background`

| key | Env / settings (ориентир) | Поведение при off |
|-----|---------------------------|-------------------|
| `node_health` | `NODE_HEALTH_SYNC_ENABLED` | Опрос health узлов не крутится |
| `cert_sync` | `CERT_SYNC_ENABLED` | Синхронизация сертификатов off |
| `resource_metrics` | `RESOURCE_METRICS_ENABLED` | Метрики VPN-узлов off |
| `panel_resource_metrics` | `PANEL_RESOURCE_METRICS_ENABLED` | Метрики панели off |
| `cidr_scheduler` | `CIDR_DB_REFRESH_ENABLED` | Авто-scheduler CIDR DB off |
| `node_sync_reconcile` | `NODE_SYNC_RECONCILE_ENABLED` | Reconcile sync узлов off |
| `retention` | `RETENTION_ENABLED` | Автоочистка БД off. Источник правды — тоггл; переключатель в Maintenance читает/пишет тот же env |
| `key_rotation` | новый `FEATURE_KEY_ROTATION_ENABLED` (default on) + существующий `node_api_key_rotation_days` | Loop пропускает tick, если тоггл off **или** days ≤ 0 |
| `user_reminders` | `SELF_SERVICE_REMINDER_ENABLED` | Напоминания self-service off |
| `alert_rules` | `ALERT_RULES_ENABLED` / settings | Воркер алертов off + скрыть `AlertRulesCard` |
| `noc_reports` | `NOC_REPORT_ENABLED` | NOC-отчёты по расписанию off |
| `cloudflare_ips_update` | `CLOUDFLARE_IPS_AUTO_UPDATE` | Автообновление CF IP ranges off |
| `access_expiry` | новый `FEATURE_ACCESS_EXPIRY_ENABLED` (default on) | Loop `access_expiry` пропускает tick при off |
| `connection_history` | новый `FEATURE_CONNECTION_HISTORY_ENABLED` (default on); дополнительно уважать `resource_monitor` как сейчас | Сэмплы истории подключений off |

### Не отдельные тогглы (привязка)

| Worker / capability | Управляется через |
|---------------------|-------------------|
| `awg2_expire` | `awg2` |
| `backup_scheduler` | `backups` |
| traffic collector | `traffic_sync` |

## Архитектура

### Источник правды

`backend/app/services/feature_toggles.py` → `FEATURE_TOGGLES`.  
UI `FeatureTogglesTab` уже рендерит реестр: новые ключи появляются автоматически после добавления definition + labels.

### Поток

1. Админ меняет тоггл → запись в `backend/.env` → фронт `refreshModules`.  
2. **App module:** `Layout` / `SettingsNav` + middleware `check_path_access` и/или handler `require_*`.  
3. **Background:** runtime-gate в loop (предпочтительно, как у `traffic_sync` / `retention`); если gate только на старте — `disable_hint` требует перезапуск панели.

### Особый случай `nodes`

`/api/nodes` остаётся в `ALWAYS_ALLOWED` (агенты / health). Тоггл **не** удаляет весь префикс из allowlist.

| Слой | При `nodes=false` |
|------|-------------------|
| UI | Пункт меню `/nodes` скрыт; deep-link → redirect/empty как у других модулей |
| Agent / health | Пути агента и health **остаются** (список зафиксировать в implementation plan) |
| Admin mutating | create/update/delete/proxy admin operations → feature-disabled / 403 в handlers |

Паттерн тот же, что у `proxy_nodes` на handlers под `/api/nodes`.

### `panel_ops`

- Скрыть вкладку настроек.  
- Gate endpoints, которые обслуживает только эта вкладка.  
- Не блокировать компактный restart из баннера «Разделы панели».

### Профили ресурсов

Обновить `RESOURCE_PROFILES` (`minimal` / `standard` / `full`):

- `toggles` + `env` для новых background-ключей;  
- `minimal` выключает тяжёлые collectors/schedulers;  
- `standard` / `full` — on для новых ключей (кроме уже принятых исключений вроде warper/telegram).

Смысл профилей не меняется: это по-прежнему про нагрузку, не «режим UI».

### Frontend wiring

- `Layout.tsx`: `featureKey: 'nodes'` для `/nodes`.  
- `SettingsNav.tsx`: `settingsTab` / module key для `panel_ops`.  
- `FeatureModulesContext` / `SETTINGS_TAB_TO_MODULE` / `FRONTEND_PATH_TO_MODULE` — как у существующих.  
- `AlertRulesCard`: показывать только если `alert_rules` enabled (и при необходимости `resource_monitor` / monitoring tab).

## UX

- Без новой вкладки: список в текущем `FeatureTogglesTab` (2 колонки + поиск).  
- Русские `label` / `description` / `disable_hint`.  
- Sticky save + баннер перезапуска — существующее поведение.

## Тестирование

- Unit: уникальность keys/env; новые keys `default=True`; always-on paths не в реестре.  
- Guards: `nodes` mutating blocked; agent/health allowed.  
- Smoke: выключение background останавливает работу (mock loop skip или settings flip).  
- Frontend: `tsc`; ручная проверка меню/настроек после refresh modules.  
- Профили: apply minimal/standard/full не падает и пишет новые env keys.

## Критерии готовности

1. Все ключи из инвентаря видны в «Разделах панели»; always-on — нет.  
2. `nodes=false`: меню скрыто; agent/health живы; admin mutating недоступен.  
3. Каждый новый background-ключ реально останавливает работу (runtime или documented restart).  
4. Upgrade без правок `.env` → новые тогглы включены.  
5. Профили ресурсов учитывают новые background-ключи и не ломаются.  
6. Точечные backend-тесты + `tsc` зелёные.

## Порядок реализации (высокоуровнево)

1. Добавить definitions + env mapping + profile updates.  
2. Провести background runtime-gates / config bindings.  
3. Провести `nodes` + `panel_ops` UI/API.  
4. `alert_rules` UI card + остальные мелкие frontend gates.  
5. Тесты и changelog.
