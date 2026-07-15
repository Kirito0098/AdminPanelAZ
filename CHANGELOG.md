# Changelog — AdminPanel AntiZapret

<!-- markdownlint-disable MD013 -->

> История заметных изменений веб-панели для VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN).
> Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
> версионирование — [Semantic Versioning](https://semver.org/lang/ru/).

| Раздел | Описание |
| -------- | ---------- |
| ✨ **Added** | Новые возможности |
| 🔄 **Changed** | Изменения в существующем поведении |
| 🐛 **Fixed** | Исправления ошибок |
| 🗑️ **Removed** | Удалённый функционал |
| 🔒 **Security** | Улучшения безопасности |
| 🧪 **Tests** | Тесты и проверки |

## Быстрая навигация

- [Unreleased](#unreleased)
- [2.17.0](#2170---2026-07-15) — 2026-07-15
- [2.16.0](#2160---2026-07-13) — 2026-07-13
- [2.15.0](#2150---2026-07-12) — 2026-07-12
- [2.14.0](#2140---2026-07-11) — 2026-07-11
- [2.13.0](#2130---2026-07-11) — 2026-07-11
- [2.12.0](#2120---2026-07-10) — 2026-07-10
- [2.11.0](#2110---2026-07-08) — 2026-07-08
- [2.10.0](#2100---2026-07-05) — 2026-07-05
- [2.9.0](#290---2026-07-05) — 2026-07-05
- [2.8.0](#280---2026-07-02) — 2026-07-02
- [2.7.0](#270---2026-07-02) — 2026-07-02
- [2.6.0](#260---2026-07-02) — 2026-07-02
- [2.5.0](#250---2026-06-30) — 2026-06-30
- [2.4.0](#240---2026-06-18) — 2026-06-18
- [2.3.0](#230---2026-06-16) — 2026-06-16
- [2.2.0](#220---2026-06-16) — 2026-06-16
- [2.1.0](#210---2026-06-16) — 2026-06-16
- [2.0.0](#200---2026-06-16) — 2026-06-16
- [Архив 1.x и 0.x](#архив-версии-1x-и-0x)

---

## [Unreleased]

### ✨ Added

### 🔄 Changed

- **Удаление узла из HA-группы** — вместо сырого 409 в консоли: диалог с объяснением, что сначала нужно расформировать группу синхронизации; подсказка при удалении; массовое удаление пропускает узлы в HA (`nodeHa.ts`, `NodesPage.tsx`, `ConfirmDialog.tsx`, `NodeSyncGroupSection.tsx`).

### 🐛 Fixed

- **`DELETE /api/nodes/{id}` → Internal Server Error** после удаления VPS у хостера (или для offline-узла): при удалении не чистилась таблица `connection_count_samples` → `FOREIGN KEY constraint failed` и голый 500. Теперь сэмплы истории подключений удаляются в `purge_node_related`; неожиданный FK даёт понятный **409**, а не 500 (`node_manager.py`, `nodes.py`). Удаление записи в панели по-прежнему локально в БД и не требует доступности агента на сервере. Если узел в HA — сначала «Группы синхронизации» → расформировать группу.

---

## [2.17.0] - 2026-07-15

> **Кратко:** консолидация **Пользователь** (ACL чужих клиентов, `can_create_configs`, снятие `viewer`); **видимость VPN-профилей** (default + per-user); копирование `/link` в буфер; фикс Mini App после отвязки Telegram; docs совместной публикации со StatusOpenVPN; **обратная связь** на [Fider](https://claymore0098.fider.io/).

### ✨ Added

- **Обратная связь** — доска [Fider](https://claymore0098.fider.io/) для пожеланий и багов; ссылки в [README.md](README.md) и [docs/README.md](docs/README.md).
- **Пользователь: доп. доступ к клиентам** — белый список чужих VPN-клиентов (просмотр/скачивание без владения), API `GET/PUT /users/{id}/config-access`, паритет web / Mini App / Telegram / traffic; таблица `user_config_access` (бывш. `viewer_config_access`).
- **Пользователь: флаг «Может создавать конфигурации»** (`can_create_configs`) — отдельный переключатель, не путать с квотой `0` (unlimited); квота `SelfServiceQuota.can_create` учитывает флаг.
- **Видимость VPN-профилей** — глобальное умолчание (`GET/PUT /settings/user-vpn-visibility-default`, `AppSetting` `user_visible_vpn_profiles_default`) и per-user override (`User.visible_vpn_profiles`, `null` = наследовать): маршруты AZ/VPN, протоколы OVPN/WG/AWG, группы OpenVPN (`udp_tcp` / `udp` / `tcp`); каталог create/download/фильтры скрывают запрещённое в web / Mini App / Telegram; admin без ограничений; `GET /configs/visible-vpn-profiles` и `GET /tg-mini/visible-vpn-profiles` — эффективная политика для текущего пользователя (`vpn_profile_visibility.py`, `VpnVisibilityPolicyEditor.tsx`).
- **Копирование `/link` в буфер** — при генерации кода привязки Telegram в «Мой профиль» и в админском разделе Telegram (`PersonalTelegramCard.tsx`, `useTelegramSettings.ts`).

### 🔄 Changed

- Роль **Только просмотр** (`viewer`) снята: существующие записи мигрируют в `user` с `can_create_configs=false`, grants сохраняются в `user_config_access`; startup-миграция `viewer_config_access` → `user_config_access`. После обновления — повторный вход.
- Mutate (delete/patch) по whitelist запрещён (раньше viewer API мог мутировать при grant); общий сервис `config_access.py` (`can_view_config` / `can_mutate_config`).
- **Редактор пользователя** — компактный диалог: квота, «Может создавать», whitelist клиентов и политика VPN-профилей в одной карточке (`UsersTab.tsx`, `AppDialog.tsx`).
- **Дашборд** — кнопка «Создать» скрыта при `can_create_configs=false` (в т.ч. при unlimited quota); инфо-баннер «Создание отключено»; тип VPN в форме создания и карточки клиентов подстраиваются под политику видимости (`DashboardPage.tsx`, `ConfigCardsSection.tsx`).
- **TG-уведомления о входе** — успешный login / 2FA / Telegram login уходит admin-notify для всех ролей (раньше `viewer` пропускался) (`auth.py`).
- **Документация** — пошаговая инструкция совместной публикации со StatusOpenVPN на одном домене и восстановление через `nginx-repair.sh` (`docs/nastrojki/set-i-publikaciya.md`, `diagnostika.md`, `docs/konfiguracii.md`, `docs/nastrojki/polzovateli.md`); README — раздел «StatusOpenVPN на одном домене»; `SECURITY.md` — роли admin/user; планы `docs/plans/user-role-consolidation/`, `docs/plans/vpn-profile-visibility/`.

### 🗑️ Removed

- Роль `viewer` / «Наблюдатель» из enum, UI, навигации (`viewerOk`) и `/system/viewer-access` (`system.py`, `Layout.tsx`, `reset-password.py`).

### 🐛 Fixed

- **Mini App после отвязки Telegram** — доступ отзывается сразу: Mini App API требуют живой `telegram_id`, авто-relink по `tg_*` убран; дедуп алертов «вход без привязки», чтобы не было двойных TG-уведомлений после unlink (`tg_mini.py`, `auth.py`, `admin_notify.py`).

### 🧪 Tests

- **ACL пользователя** — `test_user_config_access.py`: grants, `can_create_configs`, отсутствие `viewer` в enum.
- **Видимость профилей** — `test_vpn_profile_visibility.py`: resolve default/override, фильтрация файлов и enforce create.
- **Mini App unlink** — `test_tg_mini_unlink.py`, `test_tg_unlinked_notify_dedup.py`.

---

## [2.16.0] - 2026-07-13

> **Кратко:** **NOC Ops** — federated SSE, Mbps/длительность, лента инцидентов, health score, фильтры, история подключений, HA physical node, disconnect/restart; **TG-алерт offline узла с grace**; UX сводки узлов (табы «Сводка / Сравнение», full-width); роль **Пользователь** — Telegram в профиле, упрощённый Mini App, ops-разделы только admin; фикс GeoIP `tcp4-server:` и белого экрана при F5.

### ✨ Added

#### NOC / Мониторинг

- **Federated SSE** — `/monitoring/stream?scope=node|all&ha_mode=dedupe|raw`; UI «Все узлы» без polling overview (`monitoring.py`, `MonitoringPage.tsx`).
- **Лента инцидентов** — `GET /monitoring/incidents` + `NocIncidentFeed` (пусто → скрыто) (`noc_incidents.py`).
- **Скорость и длительность** — колонки ↓/↑ Mbps и длительности OVPN; клиентский delta rate (`useConnectionRates`, `formatBitrate`, `formatDurationShort`); у WG без session start длительность не выдумывается.
- **История подключений** — таблица `connection_count_samples`, worker (~60 с), `GET /monitoring/connection-history`, график 1h/6h/24h (`connection_history.py`, `MonitoringCharts.tsx`).
- **Health score** — `health_score` / `health_level` в summary узлов + цветной бейдж (`node_health_score.py`, `NodeSummaryCard`).
- **Фильтры NOC** — узел / город / ISP / длительность + sort `rate`/`duration`, persist в localStorage (`NocConnectionFilters.tsx`).
- **Source / freshness / GeoIP** — `served_from_cache`, `geoip_mode`, возраст данных и stale (`NocDataFreshness.tsx`).
- **HA physical node** — `active_node_*`, `ha_nodes`, toggle `ha_mode=raw` («Показать по узлам»).
- **Действия NOC** — OVPN disconnect с confirm; restart службы в `ServiceMatrix` только на scope=node.

#### Telegram / узлы (offline)

- **TG-алерт «узел offline / восстановление»** — событие AdminNotify `node_offline` (по умолчанию вкл.): после непрерывного offline дольше grace-порога (по умолчанию **3 мин**, 60–86400 с) + recovery только если offline-алерт уже уходил; дедуп `node_metadata.tg_offline_alert_sent` / якорь `offline_since` (`node_status_notify.py`, `update_node_from_health`).
- **Настройка grace** — `AppSetting` `node_offline_notify_grace_seconds` в `GET/PATCH /settings/admin-notify` (`node_offline_grace_seconds`); UI на **Узлы** (`NodeOfflineNotifyCard`) и **Telegram → Уведомления** (пресеты 1 / 3 / 5 / 10 мин).
- **Журнал / webhooks** — `log_action` `node_offline` / `node_online` (подпись в `actionLogLabels.ts`).

#### Telegram / профиль

- **Привязка Telegram в «Мой профиль»** — любой залогиненный пользователь получает одноразовый код `/link` без доступа к админскому разделу Telegram (`PersonalTelegramCard.tsx`, `GET /telegram/link-code`).
- **Ссылка на бота** — `GET /telegram/bot-info` (`bot_username`, `bot_url`); кнопка «Открыть бота» в профиле (`telegram_webhook.py`, `PersonalTelegramCard.tsx`).
- **Самостоятельная отвязка** — пользователь может очистить свой `telegram_id` через `PATCH /users/{id}` (установка чужого ID по-прежнему только admin) (`users.py`).

### 🔄 Changed

#### NOC / Мониторинг

- **SSE interval** — отдельный `monitoring_stream_interval_seconds` (по умолчанию **10 с**); стрим всегда свежий snapshot (без overview-кэша), чтобы Mbps появлялись быстрее (`config.py`, `monitoring.py`).
- **Пока считается rate** — в колонках Mbps показывается `…` вместо «—»; последняя валидная скорость сохраняется на дублирующих тиках (`useConnectionRates.ts`).
- **Сводка по узлам** — одна карточка с табами **Сводка** / **Сравнение** (отдельный `NodesCompareSection` на NOC убран); full-width `table-fixed`, компактные CPU/RAM (растягиваемый бар + %), цветной health, точка «активный», подсветка неполных служб (`MonitoringPage.tsx`, `nodeSummaryMetrics.tsx`, `NodeSummaryCard.tsx`).
- **Бейдж статуса** — `whitespace-nowrap`, чтобы «В сети» не переносилось (`NodeSelector.tsx`).

#### Роли и навигация

- **Пункт «Мой профиль»** вместо вложенных «Настроек» для non-admin — прямой переход на `/settings/personal`; у admin flyout «Настройки» без изменений (`Layout.tsx`, `SettingsPage.tsx`).
- **Подпись роли** в футере сайдбара — «Пользователь» вместо «Оператор» (`ROLE_LABELS`, `Layout.tsx`).
- **NOC Мониторинг, Журналы, Маршрутизация / CIDR, Редактор файлов** — только admin (меню, редирект страниц, API `require_admin`) (`Layout.tsx`, `monitoring.py`, `logs.py`, `routing.py`, `cidr_db.py`, `edit_files.py`).
- **Дашборд для non-admin** — только счётчик своих конфигов; без глобального «онлайн», IP сервера и служб (`DashboardPage.tsx`, `GET /monitoring/summary`).
- **Мониторинг трафика** — без изменений по доступу: по-прежнему scoped по `owner_id` (свои клиенты).
- **Лимит трафика на карточке конфига** — прогресс-бар и мета «израсходовано / лимит» для своих конфигов; `GET /client-access/policies` доступен владельцу (только свои имена на активном узле), мутации политик по-прежнему admin-only (`client_access.py`, `DashboardPage.tsx`, `ConfigCard.tsx`).

#### Telegram Mini App

- **Навигация user/viewer** — вкладки **Конфиги** + **Настройки**, старт с конфигов (без Дашборда) (`MiniBottomNav.tsx`, `HomeRoute` в `App.tsx`).
- **Настройки Mini App для non-admin** — привязка TG и 3 персональных напоминания (`cert_expiry` / `traffic_limit` / `temp_block`); без IP сервера и полного каталога admin-notify (`Settings.tsx`, `tg_mini.py`).
- **Admin-notify broadcast** — события не из персональных напоминаний доставляются только роли `admin` (defaults user больше не ловят чужие логины/CRUD) (`admin_notify.py`).

#### Документация и бот

- Подсказки `/start`, `/link` и docs указывают на **Мой профиль** вместо «Telegram → Команды бота» / «Настройки → Личное» (`telegram_bot_i18n.py`, `telegram_link.py`, `docs/Telegram.md` и др.).
- **`docs/noc-monitoring.md`**, `docs/Telegram.md`, `docs/nastrojki/monitoring-i-alerty.md` и план `docs/plans/noc-ops/` — NOC Ops (10 эпиков `done`) + grace offline-алерты.

### 🔒 Security

- **2FA и passkeys** — настройка своего аккаунта доступна любому залогиненному (раньше `require_admin` → 403 в профиле пользователя) (`auth.py`: `/2fa/*`, `/passkeys/*`).
- **Mini `PATCH /admin-notify`** — non-admin не может менять `recipient_user_ids`, admin-события и grace offline; только персональные ключи напоминаний (`tg_mini.py`).
- **`GET /monitoring/dashboard` overview/stream** — admin-only (живые IP/сессии всех клиентов) (`monitoring.py`).

### 🐛 Fixed

- **GeoIP для OpenVPN `tcp4-server:` / `udp4-client:`** — префиксы management interface не снимались → lookup шёл по мусору вместо IP; город/провайдер и `display_address` теперь корректны (`ip_geo.py`).
- **Белый экран при F5 на `/settings/...`** — Vite `base: './'` резолвил assets как `/settings/assets/...` (HTML MIME). При раздаче SPA пути переписываются в абсолютные `/assets/...` (с учётом `ACCESS_PATH`) (`html_csp.py`, `rewrite_relative_asset_urls`).
- **Предупреждение Radix Dialog в консоли** — `Missing Description for DialogContent` при открытии карточки без описания; всегда есть `DialogDescription` (видимое или `sr-only`) (`ClientActionsDialog.tsx`, `AppDialog.tsx`, `ConfirmDialog.tsx`).

### 🧪 Tests

- **NOC Ops** — `tests/test_noc_ops.py`: health score, HA aggregate, разбор `tcp4-server:` endpoint.
- **Node offline notify** — `tests/test_node_status_notify.py`: grace ниже порога / один алерт / recovery только после алерта / clamp grace.

---

## [2.15.0] - 2026-07-12

> **Кратко:** адаптивная вёрстка панели для телефонов и планшетов — safe area и `100dvh`, карточные списки вместо широких таблиц, компактный header и toolbar, **компактный sidebar в landscape**; общие компоненты `ResponsiveDataView`, `PageSectionHeader`, `ToolbarButton`; мобильные **Настройки** с inline-accordion и выпадающим переключателем разделов; улучшения HA-селектора узлов и бейджей группы; HA UI — одна кнопка «Синхронизировать» вместо «Настройка» + «Push full»; **`ANTIZAPRET_WARP` / `VPN_WARP` синхронизируются** с конфигом AntiZapret (не AZ-WARP); Telegram Mini App — синхронизация темы WebApp и исправление загрузки assets; понятные ошибки при «Подключить бота к панели» (сеть/DNS/timeout вместо сырого `Errno 101`); dev-proxy Vite для `ENFORCE_HTTPS`; **HA OpenVPN parity без перевыпуска сертификатов** — byte-copy PKI и `.ovpn` с primary на replica, read-only download/verify, полная синхронизация с копией профилей после restore; **строгая идентичность replica** — wipe-and-replace VPN/crypto, prune лишних клиентов, защита профилей от «Домен», routing apply и CSV/шаблонов; исправление ложных расхождений Verify из-за `parse_easyrsa_index`; исправления OpenVPN restart после HA sync, сломанных `/traffic` и `/edit-files`, flyout настроек за пределами экрана; **node agent 1.5.0**.

### ✨ Added

#### Адаптивный UI

- **`ResponsiveDataView`** — единый переключатель card/list ↔ table по Tailwind-breakpoint без runtime `matchMedia` (`ResponsiveDataView.tsx`).
- **`PageSectionHeader`** — стандартный hero страницы: иконка, заголовок, описание и flex-wrap toolbar; колонка на mobile, строка с `sm` (`PageSectionHeader.tsx`).
- **`ToolbarButton`** — кнопки панели инструментов с icon-only на узких экранах (`aria-label`), короткими подписями на `sm` и `touch-manipulation` (`ToolbarButton.tsx`).
- **`MobileSettingsSectionPicker`** — выпадающий выбор раздела настроек на экранах `< lg`, с той же видимостью пунктов, что и в боковой навигации (`MobileSettingsSectionPicker.tsx`, `SettingsPage.tsx`).
- **`NodeSummaryCard`** — карточный список узлов на **Monitoring** вместо широкой таблицы сводки (`NodeSummaryCard.tsx`, `MonitoringPage.tsx`).
- **Карточные layout'ы на mobile** — `ResponsiveDataView` на **Traffic** (клиенты, топ, детали), **Logs** (подключения, QR-аудит, сокеты OpenVPN, журнал действий), **Monitoring** (подключения, сводка узлов), **Узлы** (таблица узлов и HA-группы), **Настройки → Пользователи**, **Routing → Анализ DPI**, **Dashboard → сравнение узлов**, **Node Sync** (группы HA, политики узлов).
- **Safe area и динамическая высота viewport** — CSS-переменные `--safe-*`, утилиты `pt-safe` / `pb-safe` / `px-safe`, `viewport-fit=cover` в `index.html`, Tailwind `min-h-dscreen` / `h-dscreen` / `max-h-90dscreen` (`index.css`, `tailwind.config.js`).
- **Компактный режим в landscape** — классы `orientation-compact-*` для header, вкладок и страницы настроек на низких экранах в альбомной ориентации (`index.css`, `Layout.tsx`).
- **Landscape sidebar / sheet** — при `max-height: 500px` в landscape меню не съедает экран: скрыты подзаголовок и «Система активна», плотнее пункты nav, footer одной строкой (avatar + имя + тема + выход); mobile sheet шире (`min(20rem, 70vw)`) (`Layout.tsx`, `index.css`).
- **Компактный `NodeSelector` в mobile-header** — выбор узла/HA-группы в шапке на экранах `< sm`, без переполнения toolbar (`Layout.tsx`, `NodeSelector.tsx`).

#### Node Sync / HA

- **`HaScopeEnforcer`** — при входе на HA-scope страницы с активной replica автоматически переключает контекст на primary (`HaScopeEnforcer.tsx`, `Layout.tsx`).
- **Хелперы `haNodeScope` / `haBadgeLabel`** — единая логика scope страниц (shared vs diagnostic), подписи HA-группы в селекторе и tooltip бейджа `· N узла` (`haNodeScope.ts`, `haBadgeLabel.ts`).
- **Модуль `openvpn_pki`** — разбор `easyrsa3/pki/index.txt`, извлечение serial из PEM в `.ovpn`, read-only валидация профилей (`openvpn_pki.py`).
- **Verify: блок `openvpn_profile_certs`** — диагностика отозванных/просроченных cert в `.ovpn` на primary и replica без изменения файлов на диске (`verify.py`, `haVerifySummary.ts`, `types.ts`).
- **Fingerprints для HA parity** — `easyrsa3/pki/crl.pem` и агрегированный hash каталога `openvpn/client_profiles` в отчёте «Проверить» (`fingerprints.py`, `haVerifySummary.ts`).
- **Export/import `.ovpn` через node agent** — `GET/POST /profiles/openvpn/export|import` для byte-copy профилей между узлами (`node_agent/main.py`, `antizapret.py`, `node_adapter.py`).
- **Push full: поле `openvpn_profile_copy`** — в JSON результата синхронизации — статус копии `.ovpn` с primary на каждую replica (`push_full.py`, `haSyncSummary.ts`).

#### Telegram Mini App

- **`initTelegramWebApp`** — `ready()`, `expand()`, синхронизация `--tg-theme-*` и высоты MainButton при `themeChanged` / `viewportChanged` (`telegramWebAppInit.ts`, `tg-mini/main.tsx`).
- **Safe area в Mini App** — отступы с учётом `env(safe-area-inset-*)` в `tg-mini.css`.

#### Разработка

- **Dev-proxy Vite с `X-Forwarded-Proto: https`** — локальный `npm run dev` работает с backend при `ENFORCE_HTTPS=true` без правки `.env` (`vite.config.ts`, `devApiProxy()`).
- **esbuild target `es2022`** — для dev-сборки и `optimizeDeps` (`vite.config.ts`).

### 🔄 Changed

#### Адаптивный UI

- **Оболочка панели** — `min-h-screen` → `min-h-dscreen`, sidebar/sheet/nav на полную высоту `dscreen`, `pb-safe` у footer sidebar, subtitle NOC и часы скрываются в landscape-compact (`Layout.tsx`).
- **Настройки на mobile** — flyout подменю заменён на **inline accordion** с chevron и подсветкой активного раздела; на `< lg` навигация по разделам через `MobileSettingsSectionPicker` (`SettingsSidebarSection.tsx`, `SettingsPage.tsx`).
- **Dashboard** — toolbar синхронизации на `ToolbarButton` с короткими подписями; карточки конфигов — горизонтальный scroll вкладок протоколов и сетка bulk-действий на mobile (`DashboardPage.tsx`, `ConfigCardsSection.tsx`).
- **Edit Files** — двухколоночный layout с `Select` файлов на mobile, адаптивные кнопки diff/копирования, уменьшаемая высота редактора (`EditFilesPage.tsx`).
- **Login** — `min-h-dscreen`, блок 2FA/passkey в bordered-секции, без горизонтального overflow (`LoginPage.tsx`).
- **Telegram (настройки)** — формы бота/OIDC/mini app в колонку на mobile, полная ширина полей и кнопок (`TelegramSettingsPanel.tsx`, `TelegramRecipientsPanel.tsx`).
- **HA-группы и диалоги** — карточки групп на mobile, `max-h-[min(90dvh,…)]` для модалок Push/verify (`NodeSyncGroupSection.tsx`, `HaSyncResultDialog.tsx`, `HaVerifyResultDialog.tsx`).
- **Узлы, Server Monitor, Warper** — карточный список узлов и адаптивные grid карточек метрик; bulk-toolbar с full-width кнопками на mobile (`NodesPage.tsx`, `ServerMonitorPage.tsx`, `WarperPage.tsx`, `OverviewCards.tsx`).
- **Sheet навигации** — `SheetDescription` для доступности mobile menu (`sheet.tsx`).

#### Node Sync / HA

- **Селектор узлов на HA-scope страницах** — на Dashboard, Traffic, Routing, Edit Files, Settings и AntiZapret в шапке показывается название HA-группы (а не отдельные primary/replica); replica скрыта из списка. На диагностических страницах (Логи, Мониторинг сервера, Warper, Monitoring, Узлы) список узлов без изменений (`NodeSelector.tsx`, `NodeContext.tsx`).
- **Бейдж HA на карточках и в таблицах** — вместо непонятного `(2)` показывается `· 2 узла`; при наведении — подсказка, что клиент доступен на всех узлах группы (`ConfigCard.tsx`, `TrafficClientDetails.tsx`, `MonitoringConnectionsList.tsx`).
- **HA crypto sync OpenVPN** — порядок: import PKI с primary → byte-copy `.ovpn` → restart; **без** `client.sh 7` на replica (`vpn_state_sync.py`, `copy_openvpn_profiles_from_primary`).
- **Push full OpenVPN** — убран auto-repair/re-issue перед backup; после restore на replica — копия `.ovpn` с primary (restore вызывает `client.sh 7`, copy выравнивает профили) (`push_full.py`).
- **OpenVPN profile helpers** — `recreate_openvpn_profiles()` (только `client.sh 7`), `validate_openvpn_profiles()` (read-only), `recreate_openvpn_profiles_after_admin_change()` после явного create/renew (`openvpn_profile_repair.py`).
- **Download / QR / Telegram** — отдают `.ovpn` as-is с диска, без repair и перевыпуска cert (`configs.py`, `public_download.py`, `telegram_config_send.py`).
- **Отчёт полной синхронизации в UI** — секция «OpenVPN-профили на реплике» вместо «перевыпуск на primary»; подсказки verify рекомендуют «Синхронизировать», а не renew cert (`haSyncSummary.ts`, `haVerifySummary.ts`).
- **Полная синхронизация: HA restore (`?ha_replica=true`)** — перед копированием бэкапа на replica выполняется wipe VPN/crypto путей (`easyrsa3`, server WireGuard `.conf`, каталоги профилей OVPN/WG/AWG); **без `client.sh 7`** на replica. Каталог `config/` — merge, как раньше (`push_full.py`, `antizapret_backup.py`).
- **Полная синхронизация: prune** — после copy `.ovpn` удаляются VPN-клиенты OpenVPN/WireGuard, которых нет на primary (`replica_prune` в JSON результата и отчёте синхронизации) (`vpn_state_sync.py`, `push_full.py`).
- **Полная синхронизация: hard fail** — ошибки copy `.ovpn`, prune, restart OpenVPN или apply WireGuard runtime помечают replica как failed (не «успех с предупреждениями»); пустой архив профилей с primary и недействительные сертификаты в `.ovpn` после копии на replica также прерывают шаг (`push_full.py`, `vpn_state_sync.py`).
- **HA crypto sync** — `import_easyrsa3_archive` делает `rmtree` PKI перед extract; WireGuard server `.conf` — mirror-sync (лишние файлы на replica удаляются) (`vpn_state_sync.py`).
- **«Домен» / shared domain** — после `client.sh 7` на replica выполняется byte-copy `.ovpn` с primary (как при полной синхронизации), чтобы профили оставались идентичными основному узлу (`shared_domain.py`).
- **HA auto: routing apply на replica** — `routing_apply_replica` больше не вызывает `client.sh 7` на реплике (`recreate_profiles=False`): только `sync_cidr_providers` + `doall.sh` (`background_tasks.py`, `antizapret_sync.py`).
- **CSV-импорт и шаблоны клиентов** — после batch-создания OpenVPN-клиентов один раз вызывается `client.sh 7`; на HA-primary затем копируются `.ovpn` на реплики (`config_csv_ops.py`, `client_templates.py`).
- **UI HA-групп** — одна кнопка «Синхронизировать» вместо «Настройка» + «Push full» (полный цикл: домен → wipe/копия VPN/crypto на реплику → проверка); отдельно «Домен» и «Проверить»; при смене состава группы — тот же диалог полной синхронизации; явные подсказки, что синхронизация удаляет VPN/crypto на реплике (`NodeSyncGroupSection.tsx`).
- **`ANTIZAPRET_WARP` / `VPN_WARP` синхронизируются** — встроенные флаги Cloudflare WARP из «Конфиг AntiZapret» убраны из `ANTIZAPRET_HA_SETTING_EXCLUDE` (это не AZ-WARP / Warper). На реплику уходит тот же setup, что на primary; node-local по-прежнему только `warper-include-ips.txt` (`antizapret_params.py`, UI подсказки HA, docs).

#### Документация

- **`docs/NodeSync.md`** — один `.ovpn` + один cert на обоих IP; HA копирует PKI и файлы профилей; `client.sh 1` только по кнопке «Обновить сертификат»; verify сравнивает `openvpn/client_profiles`; `ANTIZAPRET_HA_SETTING_EXCLUDE` пуст (WARP-флаги setup реплицируются).
- **`docs/antizapret-config.md`** — `ANTIZAPRET_WARP` / `VPN_WARP` входят в HA-репликацию setup; отличие от AZ-WARP / `warper-include-ips.txt`.

#### Node agent

- **Версия node agent `1.5.0`** — `GET/POST /profiles/openvpn/export|import` для byte-copy `.ovpn` между узлами при HA sync и Push full (`NODE_AGENT_VERSION`, `node_agent/main.py`, `antizapret.py`). Минимум для PKI/WG crypto-sync — **≥ 1.3.0**; для копии OpenVPN-профилей — **≥ 1.5.0**; после обновления панели перезапустите агент на VPN-узлах.

### 🐛 Fixed

#### Адаптивный UI

- **Flyout «Настройки» за пределами экрана на mobile** — подменю открывалось off-screen на узких viewport; заменено inline-accordion с видимой обратной связью (`SettingsSidebarSection.tsx`).
- **Сломанные `/traffic` и `/edit-files`** — отсутствующие импорты `formatBytes` и `useConfirmDialog` после рефакторинга HA-scope (`TrafficPage.tsx`, `EditFilesPage.tsx`).

#### Node Sync / HA

- **OpenVPN restart после HA sync** — `systemctl restart openvpn-server@*` больше не поднимает службы, остановленные вручную; перезапускаются только unit'ы в состоянии `active` (`openvpn_restart.py`).
- **Replica отклоняла тот же `.ovpn`, что работал на primary** — при рассинхроне PKI/CRL/профилей replica возвращала `certificate revoked` для того же serial; исправлено byte-copy PKI + `.ovpn` с primary без `recreate_profiles` на replica (`vpn_state_sync.py`, `push_full.py`).
- **Auto `client.sh 1` при sync/download ломал рабочие cert** — панель могла перевыпустить cert при Push full, HA sync или скачивании конфига; auto re-issue убран из автоматических путей, остаётся только при явном create/renew в UI (`openvpn_profile_repair.py`).
- **`parse_easyrsa_index`** — корректный разбор строк `V`/`E` с пустым полем revocation в реальном `index.txt` EasyRSA (`V\texpiry\t\tserial\t…`). Раньше все валидные сертификаты пропускались → ложные `not_in_index` в Verify и блокировка Push full при рабочем VPN (`openvpn_pki.py`).
- **«Домен» без Push full** — `client.sh 7` на реплике из локального PKI больше не оставляет `.ovpn` рассинхронизированными с primary (`shared_domain.py`).
- **Авто-применение маршрутизации** — фоновый `routing_apply_replica` не пересобирает `.ovpn` на реплике из локального PKI (`antizapret_sync.py`, `background_tasks.py`).

#### Telegram Mini App

- **Зависание на «Загрузка Mini App…»** — относительные пути `./assets/…` при открытии `/api/tg-mini` (без trailing slash) резолвились в `/api/assets/…` и отдавали 404; JS/CSS не загружались. При отдаче страницы пути переписываются в `/api/tg-mini/assets/…` (`tg_mini.py`).

#### Telegram-бот

- **Непонятный `setWebhook: [Errno 101] Network is unreachable`** — при сбое исходящего доступа к `api.telegram.org` показывался сырой errno. Теперь `format_telegram_connect_error` объясняет: сеть недоступна / timeout / DNS / TLS / нужен HTTPS, с подсказкой `curl -4 https://api.telegram.org/` (`telegram_api.py`, `maintenance.py`).
- **Подсказка в UI** — под кнопкой «Подключить бота к панели» уточнено про исходящий доступ сервера к Telegram API (`TelegramSettingsPanel.tsx`).

### 🧪 Tests

- **`haNodeScope` / `haBadgeLabel`** — unit-тесты scope страниц, подписей группы и tooltip (`haNodeScope.test.ts`, `haBadgeLabel.test.ts`).
- **OpenVPN restart только active** — `test_node_sync_openvpn_restart.py`: пропуск stopped unit'ов, fallback при недоступном monitoring.
- **OpenVPN PKI и profile validation** — `test_openvpn_pki.py`: разбор `index.txt`, serial из PEM, статусы revoked/expired.
- **Profile repair без auto re-issue** — `test_openvpn_profile_repair.py`: `recreate_openvpn_profiles` не вызывает `add_openvpn_client`.
- **HA crypto sync OpenVPN** — `test_vpn_state_sync.py`: replica import PKI + `.ovpn`, без `recreate_profiles`.
- **Push full: copy `.ovpn` после restore** — `test_node_sync_push_full.py`: `copy_openvpn_profiles_from_primary` на успешных репликах, поле `openvpn_profile_copy`.
- **Verify: `openvpn_profile_certs`** — `test_node_sync_verify_profiles.py`: `ready=false` при revoked cert в профиле primary.
- **HA restore без `client.sh 7`** — `test_antizapret_backup_ha_restore.py`: wipe VPN/crypto перед copy на replica.
- **Prune, mirror WG, hard fail `.ovpn`** — `test_vpn_state_sync.py`: `prune_replica_vpn_clients`, mirror WireGuard server configs, ошибка при пустом архиве профилей.
- **Push full: HA restore, prune, invalid certs** — `test_node_sync_push_full.py`: флаг `ha_replica`, prune, hard fail при ошибке copy профилей и при invalid certs после копии.
- **EasyRSA `index.txt` с пустой revocation-колонкой** — `test_openvpn_pki.py`: строки `V`/`E` с `V\texpiry\t\tserial\t…`.
- **Shared domain: byte-copy `.ovpn`** — `test_node_sync_shared_domain.py`: копия профилей primary → replica после `client.sh 7`.
- **Routing apply без `client.sh 7` на replica** — `test_background_tasks_doall.py`: `recreate_profiles=False` для `routing_apply_replica`.
- **Ошибки Telegram webhook** — `test_telegram_api_errors.py`: `Network is unreachable`, timeout, HTTPS URL required, fallback для неизвестных ошибок.
- **HA setup: WARP-флаги реплицируются** — `test_antizapret_ha_settings.py`: `ANTIZAPRET_WARP` / `VPN_WARP` не в exclude, проходят `filter_ha_replicable_settings`.

### 🗑️ Removed

#### Node Sync / HA

- **Отдельные кнопки «Настройка» и «Push full» в UI групп** — заменены одной «Синхронизировать» (API `POST …/setup` и `POST …/push-full` сохранены для совместимости).

---

## [2.14.0] - 2026-07-11

> **Кратко:** устранение критических проблем HA Node Sync — накопление счётчика auto-heal и notify после N неудач; reconcile не трогает группы в `pending`; Push full continue-on-error без прерывания на первой упавшей реплике; запрет записи на replica (backend 403 + баннер readonly в Edit Files, Routing, Settings, AntiZapret); разделение статусов verify и репликации (два badge); `warnings` в API групп; возобновление опроса фоновой задачи после reload; renew OVPN без shadow — crypto PKI fallback; очистка shadow при переходе auto→manual; prompt Push full при смене состава группы; `NODE_SYNC_AUTO_REPLICATE_POLICIES`; подсказки verify с учётом `manual_full`; ссылки на runbook в секции HA; **node agent 1.4.0**.

### ✨ Added

#### Node Sync / HA

- **Backend guards для replica** — `require_ha_primary_for_client_ops` / `require_ha_primary_for_config_ops` на edit-files, routing, settings, configs и bulk-операциях; HTTP 403 при попытке записи не с primary (`groups.py`, `edit_files.py`, `routing.py`, `settings.py`).
- **Компонент `HaReplicaBanner`** — предупреждение «HA: узел replica — только просмотр» на Dashboard, Edit Files, Routing, Settings, AntiZapret (`HaReplicaBanner.tsx`, `useHaReplicaReadonly`).
- **Readonly AntiZapret на replica** — отключены сохранение, apply и правка списков в `AntizapretConfigTab` при активном replica-узле.
- **Два badge в таблице HA-групп** — отдельно «Verify: …» и «Репликация: …», чтобы расхождения паритета не скрывали `sync_status=failed` (`verifyBadge`, `replicationBadge`, `NodeSyncGroupSection.tsx`).
- **Поле `warnings` в API групп** — auto-heal failures, ошибки репликации при успешном verify, shadow linking (`build_group_warnings`, `group_to_dict`, `groups.py`).
- **Возобновление опроса pending-задачи** — после reload UI подхватывает `last_sync_task_id` и продолжает poll Push full / Setup / «Домен → узлы» (`NodeSyncGroupSection.tsx`, `node_sync.py`).
- **Раздельные действия синхронизации** — кнопки «Настройка», «Push full» и «Домен» вместо одной «Синхронизировать»; диалог подтверждения «Применить shared domain».
- **Prompt Push full при смене состава** — после изменения primary или списка replica — диалог «Обязательна полная синхронизация» (`NodeSyncGroupSection.tsx`).
- **Runbook в описании секции HA** — ссылки на `docs/NodeSync.md` и `reviews/HA-sync-remediation-plan.md`.

### 🔄 Changed

#### Node Sync / HA

- **Reconcile пропускает `pending`** — фоновый worker не выставляет `failed` и не запускает auto-heal во время Push full / Setup (`reconcile_worker.py`).
- **Push full continue-on-error** — ошибка restore на одной реплике не прерывает цикл; shadow link только если все restore OK; итог `sync_status=failed` при partial failure (`push_full.py`).
- **Verify не затирает `sync_status`** — обновляет только `last_verify_at` / `last_verify_result`; счётчик `auto_heal_failures` сохраняется между verify (`verify.py`, `reconcile_worker.py`).
- **Push full → `failed` при shadow/verify issues** — частичный restore, конфликты shadow linking или verify not ready помечают репликацию как failed с понятным `last_sync_error` (`push_full.py`).
- **Renew OVPN без shadow — crypto fallback** — при отсутствии shadow `VpnConfig` на replica копируется easyrsa3 с primary вместо hard error (`replicate.py`, `_handle_client_renew_cert`).
- **Переход auto→manual очищает shadow** — `clear_shadow_links_for_group` сбрасывает `ha_primary_config_id` при смене режима (`node_sync.py`, `dissolve.py`).
- **`NODE_SYNC_AUTO_REPLICATE_POLICIES`** — флаг из `.env` учитывается в `replicate_policy_op`, `replicate_node_default_policy` и `heal_policy_drift` (`policy_sync.py`).
- **Подсказки verify с учётом режима** — в отчёте «Проверить» для `manual_full` рекомендуется Push full, для `auto` — incremental heal / синхронизация (`haVerifySummary.ts`).

#### Документация

- **`docs/NodeSync.md`** — домен применяется через Setup / «Домен → узлы», а не автоматически при создании группы; уточнения по `manual_full` / `auto` и auto-heal.

#### Node agent

- **Версия node agent `1.4.0`** — без изменений HTTP API; маркер релиза вместе с панелью 2.14.0 (`NODE_AGENT_VERSION`, `node_health.py`, `node_agent/main.py`). Минимум для HA crypto-sync и verify по-прежнему **≥ 1.3.0**; после обновления панели перезапустите агент на узлах, чтобы в «Узлах» отображалась актуальная версия.

### 🐛 Fixed

#### Node Sync / HA

- **Счётчик auto-heal не накапливался** — `prior_failures` читался из свежего verify вместо `group.last_verify_result`; после N неудач не срабатывал admin notify (`reconcile_worker.py`).
- **Reconcile во время Push full** — мог выставить `sync_status=failed` поверх активной синхронизации (`reconcile_worker.py`).
- **Push full прерывался на первой ошибке** — оставшиеся реплики не обрабатывались (`push_full.py`).
- **Запись на replica без ограничений** — edit-files, routing и settings принимали изменения с replica-узла, риск split-brain (`edit_files.py`, `routing.py`, `settings.py`).
- **`synced` при ненулевом `last_sync_error`** — Push full мог оставить успешный статус при проблемах shadow link или verify (`push_full.py`).
- **Verify маскировал failed репликацию** — один badge «готово» при `sync_status=failed` и успешном паритете; исправлено разделением badge и `warnings`.

### 🧪 Tests

- **Auto-heal counter и pending skip** — `test_node_sync_reconcile_worker.py`: накопление `auto_heal_failures`, notify после исчерпания лимита, reconcile пропускает `pending`.
- **Push full continue-on-error** — `test_node_sync_push_full.py`: partial failure на одной из трёх реплик, обработка всех узлов, shadow link только при полном restore.
- **Edit-files 403 на replica** — `test_edit_files_ha_replica.py`: сохранение файла с replica-узла возвращает 403.

---

## [2.13.0] - 2026-07-11

> **Кратко:** переработка Telegram-бота — компактное меню, сводка трафика с топ-5, метки OVPN/WG/AWG на конфигах, live-скорость сети в /status для admin; сброс Web App-кнопки меню при webhook; двусторонняя синхронизация VPN-клиентов с диском узла; CLI `reset-password.py` для сброса паролей и второго фактора; автоперезапуск панели после восстановления из бэкапа; подсказки в UI обновления о длительной сборке и ложной «Ошибке опроса»; HA — **копирование ключей WG/AWG и OpenVPN с primary на replica** (в `sync_mode=auto` и crypto-sync при create/delete в `manual_full`), без `client.sh 4/1` на реплике; полная замена каталогов профилей WG/AWG на replica; **предупреждение в UI**, если репликация ключей после создания клиента не удалась; auto-heal `crypto_sync`, перезапуск OpenVPN после синхронизации, модальные отчёты «Синхронизировать» и «Проверить» с понятными описаниями, live health-check перед verify, **детализация расхождений config/ по файлам** (группы провайдеров/маршрутизации, без ложного «Только на основном» при устаревшем node agent); публикация панели по подпути на общем домене (`ACCESS_PATH`, nginx snippet); интеграция со [StatusOpenVPN](https://github.com/TheMurmabis/StatusOpenVPN) на общем домене; скрипт восстановления nginx после сбоя сторонних uninstall-скриптов; согласованность «Адрес сайта и HTTPS» — нестандартные порты, `HTTP_ACME_PORT`, определение nginx-режима и единое имя вкладки; исправления багов мастера публикации (зависший диалог, залипший `ACCESS_PATH`, рассинхрон `.env`/форма, проверка портов и общего домена); **node agent 1.3.0**.

### ✨ Added

#### Сеть и публикация

- **`ACCESS_PATH`** — публикация панели по подпути на общем домене (например `https://example.com/panel/` рядом с `/monitor`): нативные маршруты backend/frontend, nginx snippet + опциональный auto-include, поле в мастере «Сеть и публикация», переменная `.env`, runtime `window.__PANEL_ACCESS_PATH__` для SPA без пересборки.
- **Интеграция со StatusOpenVPN** — переключатель в мастере «Сеть и публикация» при обнаружении `/status/` на домене: безопасное добавление `include` только в активный vhost `sites-enabled`, бэкап конфига, проверка сохранности блока `/status/`; API `shared_domain_status_openvpn` (`panel_publish_info.py`, `nginx-common.sh`, `SharedDomainPublishSection.tsx`).
- **`scripts/nginx-repair.sh`** — восстановление nginx для панели после поломки сторонними скриптами (например `uninstall.sh` StatusOpenVPN): чтение `backend/.env`, удаление сломанных vhost'ов домена, установка выделенного vhost AdminPanelAZ, перезапуск панели; пункт в `adminpanel-menu.sh` → «Диагностика».
- **Секция «Общий домен» в мастере публикации** — карточка с префиксом URL (`https://домен/` + подпуть), превью полного адреса, схема сосуществования путей при StatusOpenVPN (`SharedDomainPublishSection.tsx`).
- **Блокирующий диалог публикации** — `PublishAwaitDialog`: модальное окно на время применения настроек (running / completed / failed), без сырого HTML nginx в toast; ручное открытие URL вместо авто-редиректа (`VpnNetworkTab.tsx`, `publishWizardUi.ts`).
- **Хелперы публичного HTTPS-origin** — `public_https_origin_host()` / `public_https_origin_url()` в `panel_publish_info.py`; `formatPublicHttpsHost()` / `formatPublicHttpsOrigin()` во frontend (`publishWizardUi.ts`) — единая сборка `https://домен[:порт]` для диагностики, `security.txt` и превью подпути.

#### Операции и CLI

- **`reset-password.py`** — интерактивный скрипт в корне репозитория: выбор пользователей панели, генерация случайного 12-символьного пароля, флаг `must_change_password`, отзыв refresh-токенов; опциональный сброс TOTP 2FA и удаление passkey; неинтерактивный режим `-u admin -y --disable-2fa`; автозапуск через `backend/.venv`.

#### Telegram-бот — /status (admin)

- **Блок ресурсов сервера** — CPU, RAM, диск, аптайм, load average и live RX/TX по интерфейсам в `/status` (`build_server_status_block`, `telegram_bot_handlers/status.py`).
- **Live throughput API** — `sample_interface_throughput`, `get_live_throughput` в `server_monitor.py`; прокси через `NodeAdapter.get_server_live_throughput` и `GET /server-monitor/live-throughput` на node agent.

#### Telegram-бот — /traffic

- **Сводка и топ-5 за сутки** — вместо постраничного списка: клиентов, online, трафик за 24 ч и всего, медали 🥇🥈🥉 для лидеров (`telegram_bot_handlers/traffic.py`).
- **Два режима** — admin видит флот целиком; пользователь — только свои конфиги.

#### Telegram-бот — /configs

- **Метки протокола на кнопках** — OVPN / WG / AWG по реальным файлам профиля на узле (`classify_config_profile_groups`, `format_config_protocol_badge` в `telegram_profile_ui.py`).
- **Подменю «Ещё»** — компактная reply-клавиатура (Конфиги · Статус · Ещё); трафик, помощь и admin-разделы — inline-меню «Дополнительно» (`menu.py`, `handle_more_menu`).

#### Node Sync / HA

- **Перезапуск OpenVPN после синхронизации** — после Push full на каждой реплике и после «Домен → узлы» на всех узлах группы выполняется `systemctl restart` для всех установленных `openvpn-server@*` (`openvpn_restart.py`, `push_full.py`, `shared_domain.py`).
- **Копирование crypto-состояния primary → replica** — модуль `vpn_state_sync.py`: WireGuard — `/etc/wireguard/*.conf`, `wg syncconf`, **файлы профилей** `client/wireguard/` и `client/amneziawg/` (не `client.sh 7` на replica); OpenVPN — tar `/etc/openvpn/easyrsa3/`, `client.sh 7`, restart OpenVPN (`replicate.py` create/delete/renew).
- **API node agent для HA crypto sync** — `GET/PUT /wireguard/server-config/{interface}`, `POST /wireguard/apply-runtime`, `GET/POST /profiles/wireguard/export|import`, `PUT /profiles/upload`; прокси в `LocalNodeAdapter` / `RemoteNodeAdapter` (`antizapret.py`, `node_agent/main.py`, `node_adapter.py`).
- **Auto-heal `crypto_sync`** — reconcile worker при drift `wireguard/conf_files`, `easyrsa3/*`, списков OVPN/WG клиентов копирует PKI и WG peers с primary на все replica (opt-in `NODE_SYNC_AUTO_HEAL=true`; без auto Push full) (`reconcile_worker.py`, `heal_crypto_drift`).
- **Модальное окно отчёта синхронизации** — после «Синхронизировать» и «Домен → узлы» вместо длинного toast открывается `HaSyncResultDialog`: секции (домен в setup, копия AntiZapret, адреса в конфигах, перезапуск OpenVPN), пояснения к шагам и итог с рекомендацией «Проверить» (`haSyncSummary.ts`, `NodeSyncGroupSection.tsx`).
- **Модальное окно отчёта проверки** — кнопка «Проверить» и ссылка «Отчёт проверки» открывают `HaVerifyResultDialog`: список проверок (клиенты OVPN/WG, PKI, config/), расхождения с подсказками «что делать», блок «Дальше» (DNS / синхронизация) (`haVerifySummary.ts`, `HaVerifyResultDialog.tsx`).
- **Детализация расхождений config/ в HA verify** — per-file SHA256 для `antizapret/config/*.txt`, один mismatch с полями `changed_files` / `only_primary` / `only_replica`; в UI — сгруппированные списки (провайдеры CIDR, списки маршрутизации, прочие), моноширинные имена файлов и подписи из редактора (`fingerprints.py`, `verify.py`, `haVerifySummary.ts`).
- **Fallback per-file fingerprints через node agent** — `GET /backups/antizapret/config-file-fingerprints`, `get_config_file_fingerprints()` в адаптерах, обогащение отпечатков перед сравнением (`node_agent/main.py`, `node_adapter.py`, `verify.py`); для HA verify — node agent **≥ 1.2.0**, для crypto-sync — **1.3.0** на всех узлах группы.
- **Понятные формулировки в отчётах** — человекочитаемые названия профилей OpenVPN (AntiZapret UDP/TCP и т.д.), доменов в конфигах, объектов PKI и файлов AntiZapret вместо технических ключей и `openvpn-server@*`.
- **Предупреждение HA при создании клиента** — поле `ha_replicate_warning` в ответе `POST /configs`; жёлтый toast на Dashboard, если копирование ключей на replica не удалось (`format_ha_replicate_errors`, `client_sync.py`, `DashboardPage.tsx`).

#### Node agent

- **Версия node agent `1.3.0`** — API HA crypto-sync: `GET/PUT /wireguard/server-config/{interface}`, `POST /wireguard/apply-runtime`, `GET/POST /profiles/wireguard/export|import`, `PUT /profiles/upload`, `GET/POST /openvpn/easyrsa3/export|import`; import профилей WG/AWG с полной заменой каталогов на диске (`NODE_AGENT_VERSION`, `node_agent/main.py`, `antizapret.py`).

### 🔄 Changed

#### Дашборд — синхронизация конфигов

- **Двусторонняя сверка с диском узла** — `POST /configs/sync` и `import_clients_from_disk` удаляют из БД `VpnConfig`, если клиент вручную удалён на сервере; при удалении primary очищаются HA shadow-записи; ответ API и toast в UI показывают «добавлено N, удалено M» (`config_import.py`, `configs.py`, `DashboardPage`).

#### Telegram-бот

- **Имя узла** в `/status` и `/traffic`.
- **Фильтр конфигов** — список строится только по клиентам с файлами на активном узле; WG/AWG-фильтр сразу открывает нужный тип; контекст фильтра сохраняется при возврате из карточки (`configs.py`, `parse_config_callback`).
- **Команда /traffic в BotFather** — описание «Трафик: сводка и топ-5»; подпись WARP-кнопки «🌐 WARP» (старая «AZ-WARP» по-прежнему распознаётся).
- **Placeholder reply-клавиатуры** — «Конфиги, статус или Ещё…» (`reply_keyboard` + `input_field_placeholder`).

#### Резервные копии

- **Автоперезапуск после восстановления** — `POST /backups/restore` и upload с `restore=true` через ~2 с закрывают соединения SQLite и перезапускают `adminpanelaz` (systemd или `start.sh`); ответ API: «Панель будет перезапущена через несколько секунд» (`backups.py`, `system_update.py`).
- **Предупреждение в веб-UI** — диалоги восстановления и загрузки+восстановления сообщают об автоматическом перезапуске; кнопки «Восстановить и перезапустить» / «Загрузить, восстановить и перезапустить» (`BackupTab.tsx`).
- **Telegram-бот** — те же формулировки в подтверждении и после успешного restore (`settings_backups.py`, `telegram_bot_i18n.py`).

#### Telegram — webhook и Mini App

- **Кнопка меню бота** — при подключении/отключении webhook панель сбрасывает `menu_button` в default вместо Web App «Открыть» (`reset_chat_menu_button_sync`, `maintenance.py`).
- **Инструкции Mini App** — убран шаг BotFather `/setmenubutton`; открытие через inline `@бот` или карточку конфига (`TelegramMiniAppGuide`, `docs/Telegram.md`).

#### Настройки — обновления и пересборка

- **Подсказки о длительности** — в «Обновления» и «Пересборка интерфейса» предупреждение, что процесс может занять до 15–20 минут на слабом VPS (этап `npm run build:all`); то же в диалоге подтверждения и подсказках разделов (`updateGuidance.ts`, `UpdatesTab.tsx`, `PanelRebuildCard.tsx`, `settingsLabels.ts`).
- **«Ошибка опроса» с HTML во время сборки** — пояснение, что сервер временно занят сборкой и повторно запускать обновление не нужно; при таком сбое опроса — warning-toast вместо сырого HTML в ошибке (`isLikelyBuildBusyPollError`, `resolveUpdateTaskErrorMessage`).

#### Node Sync / HA

- **Проверка паритета (verify)** — перед сравнением primary и replica выполняется live health-check каждого узла; статус в БД обновляется, чтобы не помечать доступную реплику как `node_status: offline` после синхронизации (`verify.py`, `_refresh_node_online`).
- **Сводки verify на русском** — итог проверки: «Готово к DNS-переключению» / «Расхождения между основным узлом и репликой» вместо англоязычных строк в API и UI.
- **Отчёт проверки в UI** — убран общий жёлтый баннер под таблицей HA-групп; результат привязан к группе, статус в строке обновляется сразу после «Проверить».
- **HA auto-sync create/delete/renew** — в `sync_mode=auto` на replica больше не вызывается `client.sh 4/1` (новые ключи на каждом узле); вместо этого копируется crypto-состояние primary — один профиль работает на обоих IP через общий домен (`vpn_state_sync.py`, `replicate.py`). Push full по-прежнему нужен для первичного выравнивания и recovery после split-brain.
- **Crypto-sync в `manual_full`** — create/delete/renew OVPN на primary дополнительно копирует WG conf + профили и easyrsa3 на replica; shadow `VpnConfig` и прочая auto-репликация политик/файлов — только в `auto` (`client_sync.py`, `replicate_primary_crypto_to_replicas`, `docs/NodeSync.md`).
- **Import профилей WG/AWG на replica** — перед распаковкой архива удаляются каталоги `client/wireguard` и `client/amneziawg`, чтобы не оставались старые ключи (`antizapret.import_wireguard_client_profiles_archive`).
- **Описание auto-sync в UI** — уточнено: копия WG conf + профилей и PKI OVPN с primary, shadow `VpnConfig` в режиме auto (`NodeSyncGroupSection.tsx`, `AUTO_SYNC_OPERATIONS`).

#### Адрес сайта и HTTPS

- **Единое название вкладки** — «Адрес сайта и HTTPS» в документации, README, переключателях модулей и журнале действий (раньше в разных местах: «Сеть и публикация», «Порт, HTTPS и Nginx», «VPN-сеть») (`feature_toggles.py`, `set-i-publikaciya.md`, `actionLogLabels.ts`).
- **`HTTP_ACME_PORT` в сводке .env** — переменная отображается в `env_rows` и подхватывается формой мастера при загрузке (`panel_publish_info.py`, `VpnNetworkTab.tsx`).
- **Подсказки по портам** — тексты мастера, карточки текущего режима и предупреждение `nginx_selfsigned` учитывают значения из полей `HTTPS_PUBLIC_PORT` / `HTTP_ACME_PORT`, а не жёсткое «80/443» (`publishWizardUi.ts`, `panel_publish_info.py`).
- **Определение активного nginx-режима** — без `PUBLISH_MODE` режим выводится из cert в vhost на диске (`nginx_ssl_cert_path_for_domain`, `infer_nginx_publish_mode_from_cert`, `resolve_active_publish_mode_key`).
- **Предупреждения uvicorn + nginx** — `nginx_listens_on_https_port(port)` с учётом `HTTPS_PUBLIC_PORT` из `.env`, не только проверка `:443` (`build_uvicorn_publish_warnings`).
- **Индикатор безопасного режима в UI** — вместо мёртвой проверки `mode_key === 'nginx_le'` используется `active_publish_mode` (`VpnNetworkTab.tsx`).
- **`GET /settings/vpn-network/domain-ssl`** — в ответ добавлены `shared_domain_foreign_vhost` и `shared_domain_status_openvpn` для введённого домена (не только из `.env`); секция «Общий домен» и переключатель интеграции обновляются при смене домена в мастере (`maintenance.py`, `VpnNetworkTab.tsx`).
- **Чтение `.env` на вкладке** — `build_panel_publish_context` и «Текущий адрес в браузере» различают отсутствие ключа и пустое значение (`env_key_defined_in_file`, `_resolve_env_string`, `resolve_vpn_network_request_url`); после unset в `.env` API не подставляет устаревший кэш `get_settings()` до перезапуска uvicorn.
- **Диалог публикации при обрыве связи** — `PublishAwaitDialog` можно закрыть в состоянии `running`, если старт задачи завершился transient-ошибкой (502/сеть), без зависания модалки (`allowDismissWhileRunning`).

#### Сеть и публикация

- **Мастер публикации по подпути** — переключатель интеграции (Switch) вместо чекбокса; отдельный UX для StatusOpenVPN и для прочих сторонних vhost; предупреждения и план подтверждения учитывают выключенную интеграцию (`publishWizardUi.ts`, `VpnNetworkTab.tsx`).
- **Сброс `ACCESS_PATH`** — пустое поле в мастере явно очищает переменную в `.env` (не восстанавливает старое значение) (`background_tasks.py`).
- **Nginx subpath snippet** — `include` встраивается во все vhost'ы домена; для StatusOpenVPN — только `sites-enabled`; приоритет `sites-enabled` над `sites-available` (`nginx-common.sh`, `nginx-setup.sh`).

### 🧪 Tests

- **OpenVPN restart после HA** — `test_node_sync_openvpn_restart.py`: перезапуск установленных `openvpn-server@*`, пропуск отсутствующих unit без ошибки.
- **HA verify config/** — `test_node_sync_fingerprints.py`, `test_node_sync_verify_config_diff.py`: per-file ключи, симметричный и асимметричный diff, enrichment через fallback API.
- **HA crypto sync** — `test_vpn_state_sync.py`, `test_node_sync_replicate_crypto.py`: копирование WG conf / easyrsa3 primary→replica, replicate create/delete/renew без `client.sh 4/1` на replica, classify heal `crypto_sync`; fallback копирование профилей одного клиента при пустом архиве; import с полной заменой каталогов профилей.
- **`ACCESS_PATH`** — `test_panel_paths.py`: нормализация подпути, `with_access_path`, `strip_access_path`, валидатор в `Settings`.
- **Адрес сайта и HTTPS** — `test_panel_publish_info.py`: `public_https_origin_*`, `get_panel_branding` с нестандартным портом, `resolve_active_publish_mode_key` (nginx LE/custom/self-signed, cert из vhost), `HTTP_ACME_PORT` в `env_rows`, `nginx_listens_on_https_port`.
- **Баги мастера публикации** — `test_panel_publish_info.py`: `inspect_tcp_port` без ложного «занят» на `:8080` при проверке `:80`, пустой `ACCESS_PATH` при явном unset в `.env`, устойчивость к невалидному `ACCESS_PATH` на GET, `uvicorn_le` при LE-сертификате на диске; `publishWizardUi.test.ts`: `isPublishStartTransientError` (404 не transient), `guessPublishAccessUrl` без подпути для non-nginx режимов.

### 🐛 Fixed

#### Node Sync / HA

- **Разные ключи WG/AWG и OpenVPN на replica при auto-sync** — create/delete/renew на primary реплицировался через `add_wireguard_client` / `add_openvpn_client` на каждой реплике; клиентский профиль с primary не подключался к IP replica. Исправлено копированием `/etc/wireguard/*.conf` и `/etc/openvpn/easyrsa3/` с primary (`vpn_state_sync.py`). Для уже созданных клиентов с drift — один раз **Push full** или auto-heal с `NODE_SYNC_AUTO_HEAL=true`.
- **Crypto-sync не срабатывал в `manual_full`** — при режиме по умолчанию create/delete только привязывал `sync_group_id`, ключи на replica не обновлялись; теперь crypto копируется с primary в любом режиме (`client_sync.py`, `replicate_primary_crypto_to_replicas`).
- **Разные PrivateKey/PSK в профиле при совпадающем PublicKey в `[Peer]`** — после копии server conf на replica вызывался `client.sh 7` / копировался один профиль; исправлено полным архивом профилей WG/AWG с primary; `wg syncconf` при ошибке не блокирует копирование файлов (`vpn_state_sync.py`).
- **Auto-sync: пустой/неполный архив профилей WG** — server conf копировался, а профили на replica оставались старыми; import теперь заменяет каталоги `client/wireguard` и `client/amneziawg`, при пустом архиве — fallback копирование файлов нового клиента; ошибка HA показывается в toast при создании (`antizapret.py`, `configs.py`, `DashboardPage.tsx`).
- **HA verify: ложный `node_status`** — проверка опиралась только на кэшированный статус узла в БД; после Push full реплика могла быть доступна, но помечалась «Есть расхождения» до ручного health-poll (`verify.py`).
- **HA verify: ложное «Только на основном» для config/** — если реплика отдавала только агрегатный хеш `antizapret/config` (устаревший node agent), все файлы primary ошибочно считались отсутствующими на реплике; per-file diff выполняется только при симметричных данных, иначе — `detail` с просьбой обновить агент (`verify.py`, `haVerifySummary.ts`).

#### Прочее

- **Восстановление из бэкапа (SQLite WAL)** — после записи `adminpanel.db` и `cidr.db` удаляются файлы `-wal`/`-shm`; без этого при работающей панели восстановленная база могла оставаться пустой или битой, хотя архив содержал полные данные (`backup_manager.py`, `remove_sqlite_sidecars`).
- **Диагностика сайта** — 500 при `BEHIND_NGINX`: в тексте health-probe не была определена `app_port` (`site_diagnostics.py`).
- **`ACCESS_PATH` на выделенном домене** — корень и прочие пути вне подпути отдают 404 без редиректа; убирает дефолтную страницу «Welcome to nginx» (`nginx-common.sh`).
- **Публикация на общем домене: 404 после смены подпути** — `include` попадал в `sites-available`, а nginx читал отдельную копию в `sites-enabled` (типично для StatusOpenVPN); интеграция исправлена с приоритетом активного vhost (`nginx-common.sh`).
- **Повторная публикация после интеграции** — vhost с `include snippets/adminpanelaz-*` ошибочно считался «своим» и не находился как сторонний; детекция только по заголовку `# AdminPanelAZ —` (`nginx-common.sh`, `panel_publish_info.py`).
- **Subpath snippet в чужом vhost** — `$connection_upgrade` не определён вне выделенного vhost панели; в snippet используется `Connection "upgrade"` (`adminpanelaz-subpath.conf.template`).
- **Принудительная интеграция** — `NGINX_SUBPATH_INTEGRATE` из UI теперь реально управляет встраиванием snippet (раньше foreign vhost интегрировался всегда) (`nginx-setup.sh`).
- **500 на странице «VPN / Сеть»** — `access_path_value` использовался до определения в `panel_publish_info.py`.
- **Опрос фоновой публикации** — `ReferenceError: opts is not defined` в `useBackgroundTaskPoll.startPoll`.
- **HTML nginx в уведомлениях** — нормализация ошибок proxy/502 при опросе задачи публикации (`httpErrorMessage.ts`, `publishWizardUi.ts`).
- **`HTTP_ACME_PORT` сбрасывался при повторной публикации** — UI не загружал значение из `.env`, поле всегда оставалось `80`; повторный запуск мастера мог перезаписать нестандартный HTTP-порт (`VpnNetworkTab.tsx`).
- **Нестандартный `HTTPS_PUBLIC_PORT` вне QR/one-time URL** — диагностика сайта, `security.txt` (`/.well-known/security.txt`) и префикс «Общий домен» строили URL без порта — ложные предупреждения и неверный canonical (`site_diagnostics.py`, `http_security.py`, `SharedDomainPublishSection.tsx`).
- **Все nginx-режимы без `PUBLISH_MODE` отображались как Let's Encrypt** — после `nginx_clear_app_ssl_env` в `.env` пустые `SSL_CERT`/`SSL_KEY`, хотя cert лежит в nginx vhost (`resolve_active_publish_mode_key`).

#### Адрес сайта и HTTPS — мастер публикации

- **Зависший диалог «Публикация запущена»** — при сетевой ошибке или 502 на `POST /settings/vpn-network/publish` UI ставил `status: running` без опроса задачи и без кнопки закрытия; HTTP **404** ошибочно считался transient-ошибкой и запускал тот же сценарий (`isPublishStartTransientError`, `PublishAwaitDialog`, `VpnNetworkTab.tsx`).
- **`ACCESS_PATH` не сбрасывался при переходе на uvicorn / HTTP-direct** — после публикации с подпутём `/panel` через nginx переключение на `uvicorn_le` или `http_direct` оставляло старый путь в `.env`, хотя мастер показывал корневой URL (`nginx_apply_direct_http_env`, `nginx_apply_direct_https_env` в `nginx-common.sh`).
- **Форма не сбрасывала domain и порты** — при пустых `DOMAIN` / `HTTPS_PUBLIC_PORT` / `HTTP_ACME_PORT` в ответе API поля сохраняли прежние значения (`VpnNetworkTab.tsx`).
- **Переключатель интеграции сбрасывался после публикации** — `nginxSubpathIntegrate` принудительно включался при каждом `loadSettings`, если на домене есть foreign vhost; теперь только при первой загрузке вкладки.
- **Ложное «порт занят»** — `inspect_tcp_port` матчил `:80` внутри `:8080` / `:8000` и `:443` внутри `:4430`; проверка по границе порта (`panel_publish_info.py`).
- **Нет валидации `HTTP_ACME_PORT` в UI** — пустое поле, диапазон 1–65535 и совпадение с HTTPS-портом не проверялись до запроса на backend (`VpnNetworkTab.tsx`, `handlePublish`).
- **Preview URL с устаревшим подпутём** — при смене nginx → `http_direct` preview показывал `/panel/`, хотя поле скрыто; подпуть не участвует в `guessPublishAccessUrl` для non-nginx режимов, state очищается при выходе из `nginx_*` (`publishWizardUi.ts`, `VpnNetworkTab.tsx`).
- **Домен с `:port` уходил в publish** — `panel.example.com:8443` ломал certbot/LE; host нормализуется на backend и во frontend перед отправкой (`maintenance.py`, `VpnNetworkTab.tsx`).
- **500 на всей вкладке при невалидном `ACCESS_PATH`** — `GET /settings/vpn-network` падал на `normalize_access_path` (например `/api`); ошибка перехватывается, вкладка остаётся доступной (`panel_publish_info.py`).
- **«Текущий адрес в браузере» после publish** — до перезапуска uvicorn строился из кэшированного `behind_nginx` без актуального `ACCESS_PATH` и порта (`resolve_vpn_network_request_url`).
- **Блок «Сертификат найден» без путей LE** — в `getLetsEncryptPathsForDomain` передавался `boolean` вместо `domainSslStatus` (`PublishAccessWizard.tsx`).
- **Гонки при быстрой смене домена/портов** — устаревший ответ domain-ssl или port-status перезаписывал новый; sequence guard в debounced effects (`domainSslSeqRef`, `portStatusSeqRef`).
- **Нельзя очистить поля cert/key** — effect автоподстановки снова подставлял `known_ssl_*` после ручной очистки (`suppressSslAutofillRef`, `VpnNetworkTab.tsx`).
- **Режим `uvicorn_le` определялся как самоподписанный** — при пустом `SSL_CERT` в `.env`, но наличии LE-сертификата на диске (`resolve_active_publish_mode_key`).
- **Подсказка URL для `direct_https`** — использовала `HTTPS_PUBLIC_PORT` вместо `BACKEND_PORT` при рассинхроне `.env` (`panel_publish_info.py`).

---

## [2.12.0] - 2026-07-10

> **Кратко:** HA verify показывает расхождения `config/` по конкретным файлам (группы провайдеров и маршрутизации), без ложного «Только на основном» при устаревшем node agent; fallback API per-file fingerprints на агенте; **node agent 1.2.0**.

### ✨ Added

#### Node Sync / HA

- **Детализация расхождений config/ в HA verify** — per-file SHA256 для `antizapret/config/*.txt`, один mismatch с `changed_files` / `only_primary` / `only_replica`; в модалке — сгруппированные списки файлов с подписями (`fingerprints.py`, `verify.py`, `haVerifySummary.ts`, `HaVerifyResultDialog.tsx`).
- **Fallback per-file fingerprints** — `GET /backups/antizapret/config-file-fingerprints` на node agent; `get_config_file_fingerprints()` в локальном и удалённом адаптере; обогащение отпечатков перед сравнением (`node_agent/main.py`, `node_adapter.py`).

#### Node agent

- **Версия node agent `1.2.0`** — per-file fingerprints в `GET /backups/antizapret/fingerprints`, новый `GET /backups/antizapret/config-file-fingerprints` для fallback HA verify (`NODE_AGENT_VERSION`, `fingerprints.py`).

### 🐛 Fixed

#### Node Sync / HA

- **Ложное «Только на основном»** — при асимметрии per-file отпечатков (панель с новым кодом, реплика со старым агентом) файлы на диске реплики ошибочно помечались как отсутствующие; теперь — агрегатный хеш и понятный `detail` («обновите node agent») без списка из десятков ложных имён.

### 🧪 Tests

- **`test_node_sync_fingerprints.py`**, **`test_node_sync_verify_config_diff.py`** — per-file ключи, симметричный/асимметричный diff, enrichment fallback.

---

## [2.11.0] - 2026-07-08

> **Кратко:** мастер публикации панели (Nginx ↔ uvicorn, 7 режимов), проверка домена и порта, загрузка резервной копии с компьютера; единые названия режимов и контекстные подсказки в UI.

### ✨ Added

#### VPN / Сеть — мастер публикации

- **7 режимов доступа** — в «Настройки → VPN / Сеть»: Nginx + LE / самоподписанный / свои cert; HTTPS на uvicorn + LE / свои cert / самоподписанный; прямой HTTP (`VpnNetworkTab`, `scripts/nginx-setup.sh`, `POST /api/settings/vpn-network/publish`).
- **HTTPS на uvicorn без Nginx** — TLS на приложении по образцу AdminAntizapret: `USE_HTTPS`, `SSL_CERT`, `SSL_KEY` в `.env`, флаги uvicorn в `start.sh`, режимы `--uvicorn-le|custom|selfsigned` в `nginx-setup.sh`.
- **Фоновая задача публикации** — `task_vpn_network_publish`: `nginx-setup.sh`, отложенный перезапуск панели (`SKIP_PANEL_RESTART`, `panel_restart_command` в результате), `ACCESS_URL` и `PUBLISH_MODE` (`background_tasks.py`, `VpnNetworkTab`).
- **Подсказки по сертификатам** — `known_ssl_cert`, `known_ssl_key`, `ssl_cert_suggestions[]` (`.env`, Let's Encrypt, самоподписанный adminpanelaz); автоподстановка путей при custom-режимах (`panel_publish_info.py`, `nginx_resolve_existing_ssl_paths`).
- **Сканирование всех LE-сертификатов** — `discover_ssl_certificate_candidates` перечисляет `/etc/letsencrypt/live/*`, не только домен из `.env`.
- **API проверки домена и порта** — `GET /settings/vpn-network/domain-ssl`, `GET /settings/vpn-network/port-status`; `server_primary_ip` в ответе настроек (`maintenance.py`, `panel_publish_info.py`).
- **Проверка порта в UI** — под полями порта: свободен / занят панелью / nginx / другой процесс (`VpnNetworkTab`, debounce).
- **Пути найденного LE в UI** — блок «Сертификат найден» показывает `cert` и `key` на диске.
- **Multi-site: редирект 443 → uvicorn** — если nginx уже слушает 443, для uvicorn на другом порту создаётся vhost с LE и редиректом `https://domain/` → `https://domain:port/` (`deploy/nginx/adminpanelaz-redirect.conf.template`, `nginx_install_uvicorn_redirect`).
- **Firewall при смене режима** — `firewall_apply_publish_mode` (nginx: 80/443; uvicorn/HTTP: открытие порта приложения) вызывается из `nginx-setup.sh` (`scripts/firewall-setup.sh`).
- **Certbot webroot** — при работающем nginx сначала выпуск LE через webroot без остановки всех сайтов; standalone — fallback (`nginx_obtain_letsencrypt_cert`).
- **Предупреждения uvicorn** — `uvicorn_publish_warnings[]` при nginx на 443; контекстные подсказки в UI (`publishWizardUi.ts`).
- **Поле домена** — для самоподписанного uvicorn/nginx (CN в cert); без домена — IP сервера (`nginx_resolve_selfsigned_cn`).
- **Модуль `publishWizardUi.ts`** — план подтверждения, preview URL, фильтрация предупреждений и рисков по режиму.

#### Резервные копии

- **Загрузка архива с компьютера** — `POST /api/backups/upload` (до 200 МБ): ранее скачанный `adminpanelaz_*.tar.gz` можно загрузить в список или сразу восстановить после переустановки (`BackupTab`, `BackupManager.import_uploaded_backup`, `inspect_backup_archive`).
- **Кнопки в UI** — «Загрузить» и «Загрузить и восстановить» в блоке «Сохранённые копии»; пустое состояние с подсказкой про архив после переустановки.

#### Установка

- **Мастер install-wizard** — defaults по Enter: panel+AntiZapret, production, systemd, full profile, mTLS, auto-backup, firewall off; режимы публикации Nginx/uvicorn; ввод путей cert/key при `nginx_custom` и `uvicorn_custom` с проверкой файлов на диске.
- **`scripts/backend-health-check.sh`** — единая проверка HTTP/HTTPS backend для `install.sh` и диагностики.
- **Тесты режимов публикации** — `scripts/test-install-publish-modes.sh`, `scripts/test-backend-health-check.sh` (health-check при HTTPS uvicorn).

### 🔄 Changed

#### VPN / Сеть

- **Единые названия режимов** — «Let's Encrypt», «Собственные сертификаты», «Самоподписанный SSL», «Прямой HTTP»; метод отдельной строкой: Nginx / Uvicorn (`method` в API, `VpnNetworkTab`).
- **Порядок карточек** — Let's Encrypt → свои cert → самоподписанный → HTTP; группы «Через Nginx» и «Напрямую на uvicorn».
- **Подсказки по стеку** — отдельные тексты для Nginx и uvicorn (адрес входа, риски); сокращённые формулировки «только для тестов».
- **Preview URL** — прямой HTTP: `http://IP:порт/` (не домен из `.env`); выбор найденного cert подставляет домен в поле.
- **Диалог подтверждения** — контекстные info/warning/danger по режиму, карточка домена/порта/URL; красная кнопка только для рискованных режимов; uvicorn-предупреждения не показываются для nginx-режимов (`filterPublishWarningsForMode`).
- **`PUBLISH_MODE` в `.env`** — активный режим мастера сохраняется и не сбрасывается при перезагрузке настроек без явного выбора пользователя.
- **`nginx_install_site`** — не удаляет `sites-enabled/default`, если на сервере уже есть другие сайты; reload вместо restart где возможно.
- **`nginx_apply_behind_proxy_env`** — `ENFORCE_HTTPS=true` при публикации через nginx из UI.
- **CN самоподписанного cert** — при пустом домене IP сервера вместо hostname (`nginx-common.sh`, `install.sh`, `nginx-setup.sh`).
- **Поля SSL в мастере установки и UI** — выбор своих сертификатов запрашивает пути к `.crt/.pem` и `.key` с повтором при отсутствии файла (`install-wizard.sh`, `VpnNetworkTab`).

#### Прочее

- **Удалены упоминания 3x-ui** — из UI, `.env.example`, `panel_publish_info.py`.
- **README** — таблица сценариев установки: только панель / панель + узел / узел; когда какой вариант выбирать.

#### Резервные копии

- **Уведомления admin** — событие `settings_backup_upload` в Telegram и журнале действий.

### 🐛 Fixed

#### VPN / Сеть

- **Кнопка «Применить настройки»** — `ConfirmDialogHost` получал props неверно (`{...dialogProps}` вместо `dialogProps={…}`), диалог не открывался.
- **Сброс выбранного режима** — `loadSettings` перезаписывал режим на `active_publish_mode` после клика; добавлен `userPickedModeRef`.
- **Самоподписанный → Let's Encrypt в UI** — скрипт больше не подменяет self-signed на LE; режим в мастере соответствует выбору.
- **502 Bad Gateway** — восстановлена функция `panel_restart_command()` в `panel_publish_info.py` (ImportError ломал старт uvicorn).
- **Ложный fail установки** — `backend-health-check.sh` и installer пробуют HTTPS, когда uvicorn слушает TLS (`install.sh`, `site_diagnostics.py`).
- **`http_direct` + firewall** — whitelist порта панели при прямом HTTP.
- **Ложный «Сертификат найден»** — подсказка LE привязана к домену в форме, а не к любому cert на сервере (`domain-ssl`, `getLetsEncryptPathsForDomain`).
- **500 при загрузке VPN / Сеть** — `has_le` не была определена в `build_uvicorn_publish_warnings`; `server_primary_ip()` падала на пустом `hostname -I`.
- **Лишние подсказки при HTTP** — блок uvicorn-предупреждений (Nginx/LE) не показывается в режиме `http_direct`.
- **Лишние uvicorn-предупреждения в nginx-режимах** — в диалоге подтверждения Nginx+LE не показывается «стена» предупреждений про uvicorn (`filterPublishWarningsForMode`).

#### Резервные копии

- **`backup-cli.py restore`** — абсолютный путь к архиву на диске принимается в `_resolve_archive` (раньше работало только имя из каталога бэкапов).

### 🧪 Tests

- **`scripts/test-backend-health-check.sh`** — схема health-check для режимов uvicorn HTTPS.
- **`scripts/test-install-publish-modes.sh`** — матрица 8 режимов публикации.
- **CI** — оба скрипта в job `backend` (`.github/workflows/ci.yml`).

---

## [2.10.0] - 2026-07-05

> **Кратко:** Telegram Mini App — создание и полное управление конфигами (шаблоны, блокировка, смена владельца), переработанный UX карточки клиента, исправления авторизации и прокрутки формы создания.

### ✨ Added

#### Telegram Mini App — конфиги

- **Создание конфигов** — кнопка «Новый конфиг» на вкладке «Конфиги»: имя, протокол (OpenVPN / WireGuard), срок сертификата, описание; для admin — выбор владельца; учёт квоты self-service (`CreateConfigDialog`, `GET/POST /api/configs`, `GET /api/configs/quota`).
- **Шаблоны** — one-click создание по шаблонам узла: укажите имя клиента и нажмите шаблон (`GET /api/client-templates`, `POST /api/client-templates/{id}/apply`).
- **Управление конфигом** — в карточке конфига: редактирование описания, обновление сертификата OpenVPN, удаление с подтверждением (свои конфиги; все — для admin).
- **Admin: смена владельца** — передача конфига другому пользователю панели (`PATCH /api/configs/{id}`, `ConfigOwnerSelect`).
- **Admin: блокировка** — временная и постоянная блокировка OpenVPN / WireGuard, разблокировка; отображение текущего статуса (`/api/client-access/*`, `ConfigManagePanel`).

#### Telegram Mini App — API

- **Обёртки panel API** — Mini App вызывает основные эндпоинты панели с JWT из Telegram (`panelApiFetch` в `tg-mini/api.ts`): CRUD конфигов, квота, шаблоны, политики доступа, список пользователей.
- **`user_id` в `/tg-mini/settings`** — для предвыбора владельца при создании конфига admin'ом (`tg_mini.py`).

### 🔄 Changed

#### Telegram Mini App — карточка конфига

- **Новый UX bottom sheet** — вкладки «Получить» / «Управление», sticky-кнопки внизу, пошаговые карточки (профиль → устройство → действие) (`ConfigActionDialog`).
- **Выбор профиля** — tappable-карточки файлов с бейджем расширения вместо dropdown; подсказки AntiZapret / VPN (`MiniProfileFilePicker`, `profileRouteHint`).
- **Выбор устройства** — сетка 3+2, динамическая подпись «инструкция для …» (`MiniPlatformPicker`).
- **Управление** — сворачиваемые секции: основное, владелец, сертификат, доступ, удаление.
- **Успешная отправка** — отдельный экран подтверждения с haptic feedback.

#### Telegram Mini App — форма «Новый конфиг»

- **Bottom sheet layout** — прокручиваемое тело формы и sticky footer с кнопками «Создать» / «Отмена» (классы `tg-mini-config-sheet`, `tg-mini-config-sheet-body`, `tg-mini-config-sheet-footer`).

#### Telegram Mini App — авторизация

- **Обновление сессии** — при 401 автоматический re-auth через Telegram `initData` (`refreshTgSession`, `refreshTgSessionFromInitData`); `/auth` больше не отправляет устаревший Bearer.
- **Ожидание initData** — расширен polling до ~2.5 с для медленных клиентов Telegram (`waitForTelegramInitData`).

### 🐛 Fixed

#### Telegram Mini App

- **Первый вход / «Неверный токен авторизации»** — протухший JWT в `localStorage` больше не блокирует вход: приложение прозрачно перевыпускает сессию без экрана «Повторить» (`TgAuthContext`).
- **Форма «Новый конфиг» на маленьком экране** — поля и шаблоны не обрезаются; кнопки создания всегда доступны (touch-scroll на Android).

---

## [2.9.0] - 2026-07-05

> **Кратко:** Telegram — OIDC-вход, несколько получателей уведомлений и бэкапов, объединённая вкладка «Бот и авторизация», сворачиваемые инструкции; NOC — расширенные сводки и PNG-дашборд; единый карточный формат TG-алертов; мониторинг — TB, доля трафика, live CPU, графики ресурсов; короткие ссылки на конфиги учитывают `HTTPS_PUBLIC_PORT`.

### ✨ Added

#### NOC — Telegram-сводки и PNG-дашборд

- **Ежедневная/еженедельная текстовая сводка** — трафик за период с Δ; CPU/RAM/Диск (среднее и пик); lag сбора; блокировки по лимиту; сессии OVPN/WG (среднее и пик); топ клиентов; алерты; CIDR; офлайн-узлы (`noc_report.py`, `resource_metrics.py`).
- **Еженедельный PNG-дашборд** — одна картинка в TG вместо PDF: KPI-карточки, таблица узлов, bar chart топ клиентов, инциденты и CIDR (`noc_report_image.py`, `sendPhoto` в `telegram.py`).
- **Bundled-шрифты** — Liberation Sans/Mono и DejaVu в `backend/static/fonts/`; резолвер `image_fonts.py` (кириллица без «квадратиков»).
- **Предпросмотр NOC** — кнопки «Ежедневная сводка» / «Еженедельная сводка» / «Еженедельная картинка»; `POST /settings/admin-notify/test-noc-report`, `test-noc-image` (алиас `test-noc-pdf`).
- **Тест каждого TG-уведомления** — кнопка Send у каждого переключателя «О чём сообщать»; `POST /settings/admin-notify/test-event`.

#### TG — уведомления

- **IP и устройство при входе** — парсинг User-Agent (`user_agent_format.py`); строки «IP входа» и «Устройство» в `login_success` / `login_failed`; для Telegram Login — `Telegram`.
- **Несколько получателей** — `chat_ids` для бэкапов и `recipient_user_ids` для алертов (`telegram_recipients.py`); хранение в `telegram_chat_id` (comma/JSON) и `telegram_notify_recipient_user_ids`; фильтрация в `admin_notify`, NOC и scheduler; тесты и авто-отправка — всем выбранным.
- **Единая панель получателей** — `TelegramRecipientsPanel`: один список admin с галочками «Уведомления» / «Бэкапы», быстрые действия (все, синхронизация, сброс), дополнительные chat ID группы/канала через запятую.

#### TG — OpenID Connect login

- **Новый способ входа** — Authorization Code + PKCE через `oauth.telegram.org`; проверка `id_token` по JWKS (`telegram_oidc.py`).
- **Маршруты** — `GET /auth/telegram/oidc/start`, `GET /auth/telegram/oidc/callback`, `POST /auth/telegram/oidc/token`.
- **Legacy / OIDC** — взаимоисключающий выбор (`auth_method`: `legacy` | `oidc`); подсказки Redirect URI и Trusted Origin для BotFather; CSP `oauth.telegram.org`.
- **Страница входа** — кнопка «Войти через Telegram» для OIDC; legacy-виджет только при `auth_method=legacy`; ошибки и подсказки ссылаются на «Telegram → Бот и авторизация».

#### TG — настройки и UX

- **Объединённая вкладка «Бот и авторизация»** — токен, username, способ входа и одна кнопка «Сохранить»; legacy-редirect `?tab=auth` → `bot`.
- **Привязанные аккаунты** — таблица пользователей с `telegram_id` на «Команды бота»; отвязка админом с подтверждением; запись `telegram_unlink` в журнал действий.
- **Подробные инструкции** — сворачиваемые блоки (`TelegramInstructionPanel`) на вкладках «Бот и авторизация», «Приложение», «Команды бота»: пошаговое подключение, таблицы команд/возможностей, сравнение Legacy vs OIDC, troubleshooting.
- **Выбор admin из «Пользователи»** — вместо ручного ввода Telegram ID для получателей (ранее single-select picker).

#### Мониторинг сервера — история ресурсов

- **Графики CPU / RAM / Диск** — на странице «Сервер» под live-карточками: история за 1 / 7 / 30 дней (`ResourceHistoryCharts`, `GET /api/monitoring/resource-history`); снимки ~раз в минуту фоновым worker.
- **Load average** — второй график в том же блоке, если в истории есть `load_1`.

#### Мониторинг трафика — производительность БД

- **Составной индекс** `(node_id, created_at)` на `user_traffic_sample` — ускоряет агрегацию окон 1д / 7д / 30д; миграция при старте панели (`models.py`, `database.py`).

### 🔄 Changed

#### NOC — Telegram

- **Env weekly image** — `NOC_REPORT_WEEKLY_IMAGE_*` (алиасы `NOC_REPORT_WEEKLY_PDF_*`); scheduler отдаёт PNG, не PDF.
- **UI настроек Telegram** — блок предпросмотра NOC и подписи под «картинку» вместо PDF.

#### TG — единый формат сообщений

- **Карточный layout** — `_format_notify_card` в `admin_notify.py`: заголовок с эмодзи → актор (👤/👨‍💼) → строки деталей (`Label : value`) → 🕐 время.
- **Все типы событий** — вход, конфиги, пользователи, блокировки, лимит трафика, настройки, CPU/RAM, alert rules, CIDR, напоминания пользователям; узел (`📡 Узел`) встроен в карточку, а не в начало сообщения.
- **Пример входа:**

  ```text
  ✅ Вход в панель
  👤 Пользователь Claymore
  🌐 IP входа : 203.0.113.42
  💻 Устройство Chrome · Windows
  🕐 2026-07-05 12:36 UTC
  ```

- **Напоминания владельцу VPN** — тот же формат в `user_reminder_service.py` (сертификат, лимит, временная блокировка).

#### TG — структура раздела Telegram

- **5 вкладок вместо 6** — «Авторизация через TG» и «Данные бота» объединены в **«Бот и авторизация»**; overview-карточки и описания вкладок обновлены.
- **«Уведомления»** — переключатели «Отправлять уведомления» / «Присылать бэкапы» и блок получателей перенесены с «Данные бота»; одно сохранение пишет toggles + `chat_ids` + `recipient_user_ids`.
- **Авто-бэкапы и отправка конфигов** — цикл по всем `chat_ids` (`backup_scheduler.py`, `backups.py`, `telegram_config_send.py`); NOC учитывает фильтр получателей.
- **Подсказки бота** — код `/link` и сообщения об ошибках ссылаются на «Telegram → Команды бота» (вместо «Интерактив»).

#### Мониторинг трафика — формат объёмов

- **`formatBytes()`** — при объёме ≥ 1024 GB значение показывается в **TB** (например, 2712 GB → 2.65 TB); между числом и единицей — неразрывный пробел, чтобы «GB» / «TB» не отрывались от числа (`MonitoringCharts.tsx`, `warper/utils.ts`).
- **Таблица клиентов** — колонки RX / TX / Всего / 1д / 7д / 30д с `whitespace-nowrap` (`TrafficPage.tsx`).

#### Мониторинг сервера — интерфейсы и UI

- **Селект vnStat** — понятные подписи: `-udp`/`-tcp` → OpenVPN, `vpn`/`antizapret` без суффикса → WireGuard / AWG; техническое имя в скобках (`ServerMonitorPage.tsx`, `server_monitor.collect_interface_groups`).
- **Hover на графиках Recharts** — снова показываются вертикальная линия и точки на сериях (`index.css`, графики трафика и ресурсов).
- **Страница «Сервер»** — убрана дублирующая таблица «Сетевые интерфейсы»; переключение интерфейса только через селект над графиком vnStat.

#### Мониторинг трафика — расчёт окон 1д / 7д / 30д

- **`TrafficCollectorService._recent_usage()`** — один SQL-запрос с `GROUP BY` и условным `SUM` за 30 дней вместо трёх полных выборок `.all()` по `user_traffic_sample` (`collector.py`); `/traffic/overview` перестаёт сканировать таблицу сэмплов в Python.

### 🗑️ Removed

#### NOC — PDF

- **Weekly PDF-отчёт** — `noc_report_pdf.py`, зависимость `reportlab`; вместо PDF — PNG-дашборд.

### 🐛 Fixed

#### NOC — PNG-дашборд

- **Кириллица «квадратиками»** — bundled DejaVu/Liberation вместо `load_default()` Pillow.
- **Спецсимволы в PNG** — убраны ✓, Δ, →, длинное тире (не поддерживались шрифтом в TG-картинке).
- **Наложение элементов** — перестроена вёрстка KPI-карточек (в т.ч. «Диск»); цвета dark theme панели.

#### TG — уведомления

- **Текст `cidr_ingest_partial`** — добавлено формирование сообщения в `admin_notify._build_text` (раньше мог не отправляться).

#### NOC — ложная ошибка CIDR

- **NOC-сводка показывала «CIDR: 1 ошибок обновления» при успешном cron** — в `_weekly_cidr_failures` успешный статус `ok` не учитывался (проверялся несуществующий `success`); исправлено (`noc_report.py`).

#### NOC — среднее WG-сессий

- **WireGuard в NOC показывал `WG 0`** — для WG `connected_since_ts` не заполнялся, а `last_seen_at` хранит только последний handshake (~минуты), из-за чего среднее за сутки округлялось до нуля; исправлен расчёт overlap и запись `connected_since_ts` при сборе трафика (`noc_report.py`, `collector.py`).

#### Мониторинг трафика — колонка «Доля»

- **Неверный расчёт доли** — процент считался относительно **максимального** клиента (у лидера всегда 100%), а не от суммы трафика всех видимых клиентов; исправлено на `totalBytes = sum(total_bytes)` (`TrafficPage.tsx`).

#### Мониторинг сервера — live CPU

- **WebSocket CPU всегда 0%** — `LocalNodeAdapter` создавал новый `ServerMonitorService` на каждый опрос; psutil не успевал накопить интервал между замерами. Добавлен process-wide singleton `get_server_monitor()` (`server_monitor.py`, `node_adapter.py`).

#### Мониторинг трафика — двойная загрузка

- **Дублирующий `GET /traffic/overview`** — страница вызывала overview до и после resolve активного узла (`activeNode?.id`: `null` → число). Загрузка и служебные запросы откладываются до `NodeContext.loading === false` (`TrafficPage.tsx`).

#### Раздача конфигов — короткие ссылки и публичный URL

- **Неверный порт в one-time URL** — при публикации панели за nginx на нестандартном HTTPS (например `:5050`) QR-коды и ссылки «Скопировать» формировались как для `:443`; nginx передаёт `Host` без порта. Публичный origin строится с учётом `HTTPS_PUBLIC_PORT` из `.env` (`panel_publish_info.py`, `configs.py`, `tg_mini.py`).
- **Webhook, Mini App, OIDC callback** — те же правила для `resolve_request_url_root` (раньше тоже теряли порт).
- **После обновления** — при стандартном 443 ничего менять не нужно (дефолт); при нестандартном порте добавьте в `backend/.env` строку `HTTPS_PUBLIC_PORT=<порт>` или перепубликуйте панель через «Настройки → VPN / сеть».

---

## [2.8.0] - 2026-07-02

> **Кратко:** настройки отображения карточек клиентов (сетка, видимость полей, цвет кнопок), усиление CI.

### ✨ Added

#### Конфигурации — настройки отображения карточек

- **Кнопка настроек** — в шапке «Список клиентов» рядом с поиском; выпадающее меню (`ConfigCardViewSettings.tsx`, `ConfigCardsSection.tsx`).
- **Столбцы сетки** — выбор «Авто» / 1 / 2 / 3 / 4; «Авто» сохраняет адаптивную сетку 2→3→4 колонки (`gridColsClass`, `configCardViewPrefs.ts`).
- **Видимость полей** — чекбоксы для описания, тегов, бейджей VPN/AZ, мета-полей (создан, сертификат, владелец, трафик, блокировка, онлайн), кнопок скачивания, QR, ссылки «Трафик», блока «Блок / удалить» (`ConfigCard.tsx`).
- **Цвет кнопок** — пресеты cyan / amber / emerald / red и режим «по умолчанию» (VPN — primary, AntiZapret — amber); остальные пресеты задают единый акцент на все outline-кнопки карточки.
- **Свой цвет** — color picker и ввод hex (`#rrggbb`); применяется через CSS-переменные к кнопкам и бейджам VPN/AntiZapret.
- **Сохранение настроек** — `localStorage` с префиксом `dashboard-config-cards` (по образцу NOC Мониторинг).
- **UI** — компонент `dropdown-menu.tsx` (Radix) для выпадающих меню в панели.

### 🧪 Tests

- **CI** — три параллельных job (backend / frontend / shell): compileall и import smoke для panel + node agent, сборка `build:all` (tg-mini), npm audit advisory, GitHub-аннотации ruff, таймаут 15 мин.
- **CI fixes** — shellcheck только на `-S error`, ESLint: unused imports и rules-of-hooks в RoutingPage / tg-mini Nodes.
- **CI hardening** — обновлены уязвимые Python-зависимости (pip-audit clean), безопасный `tarfile.extractall`, bandit.yaml, advisory-шаги стали блокирующими, ESLint `--quiet`.

---

## [2.7.0] - 2026-07-02

> **Кратко:** перезапуск и пересборка панели из UI, перезапуск node agent на странице узлов, надёжное удаление сервисов (systemd + state в `/var/lib`).

### ✨ Added

#### Настройки — перезапуск и пересборка

- **Раздел «Перезапуск и пересборка»** — новая вкладка в группе «Панель» (`panel_ops`, `PanelOpsTab.tsx`, `SettingsNav.tsx`, `settingsLabels.ts`).
- **`POST /api/system/restart`** — отложенный перезапуск `adminpanelaz` через systemd или `start.sh restart` (`schedule_controller_restart`, `PanelRestartCard.tsx`); запись `system_restart` в журнал действий.
- **`POST /api/system/rebuild`** — фоновая задача `rebuild_frontend`: `npm run build:all` + перезапуск без `git pull` (`apply_controller_rebuild`, `PanelRebuildCard.tsx`); прогресс в UI через `ProgressContext`; запись `system_rebuild_queued`.
- **Защита от параллельных операций** — `409 Conflict`, если уже выполняется `update_system` или `rebuild_frontend`.

#### Узлы — перезапуск node agent

- **`POST /api/nodes/{node_id}/restart-agent`** — перезапуск агента на удалённой ноде (`nodes.py`, `node_adapter.restart_agent`).
- **`POST /system/restart-agent`** на node agent — отложенный restart через `schedule_agent_restart` (`node_agent/main.py`).
- **Кнопка «Перезапуск»** на странице **Узлы** с подтверждением (`NodesPage.tsx`); запись `node_restart_agent` в журнале.

#### Журналы — русские подписи

- **Новые действия** — «Перезапуск панели», «Пересборка frontend в очереди», «Перезапуск node agent» (`actionLogLabels.ts`, `actionLogDetails.ts`).

### 🔄 Changed

#### Настройки — разделы панели

- **Баннер «Перезапустите панель»** — после смены профиля или модулей добавлена компактная кнопка перезапуска прямо в `FeatureTogglesTab.tsx` (рядом с «Перезапуск выполнен»).

#### Установка — простой установщик

- **`install-easy.sh`** — флаги `--uninstall`, `--purge-all`, `--purge`, `--reinstall` делегируются в `install.sh` (в т.ч. без TTY для `-y` / CI).
- **Меню** — отдельные пункты: удаление с подтверждениями, удаление без вопросов, «удалить всё без следов»; обновлена справка в шапке скрипта.

### 🐛 Fixed

#### Установка — удаление сервисов

- **`scripts/uninstall.sh`** — `stop_local_daemons` останавливает процессы во **всех** каталогах state: из `.env`, `/var/lib/adminpanelaz*`, `.runtime` (раньше смотрел только в `.runtime`, и сервисы после лёгкой установки оставались работать).
- **`stop_all_services`** — явная остановка `adminpanelaz`, `adminpanelaz-node`, `adminpanelaz-ddns.timer` / `.service` даже если unit-файл уже удалён (`systemd_unit_exists`, `stop_systemd_unit_if_loaded`).
- **DDNS timer** — удаление через `ddns-update.sh remove-timer` с fallback на ручную очистку systemd.

---

## [2.6.0] - 2026-07-02

> **Кратко:** UX/UI настроек и конфигураций, карточки клиентов с онлайн-статусом и адаптивной сеткой, журнал действий с группировкой, русские подписи, Telegram Mini App и Runbook/обновления из удалённого changelog.

### ✨ Added

#### Журналы — группировка действий

- **Журнал действий** — подряд идущие одинаковые записи (тот же пользователь, действие и детали) сворачиваются в одну строку с бейджем **×N** и диапазоном времени; клик раскрывает полный список событий (`groupActionLogs.ts`, `LogsPage.tsx`).

#### Настройки — резервные копии

- **Черновик и «Сохранить»** — Telegram и авто-копии редактируются локально и сохраняются кнопкой «Сохранить настройки»; опции «Создать копию» применяются при создании архива.
- **`send_to_telegram`** в `POST /backups/create` — явная отправка в Telegram с учётом галочек на странице (`BackupCreateRequest`, кнопка в `BackupTab.tsx`).
- **`BackupTestTelegramRequest`** — тело `POST /backups/test-telegram` с `include_configs` / `include_antizapret_backup` (бот Telegram использует настройку `backup_az_enabled`).

#### Настройки — нагрузка и уведомления

- **Hero-блок** — метрики порогов CPU/RAM, ссылка «Настроить Telegram» (`MonitoringTab.tsx`).
- **Пресеты** — интервалы проверки, паузы и пороги в `MonitorSettingsCard.tsx`; кнопки сравнения и паузы в форме правил (`AlertRulesCard.tsx`).

#### Настройки — разделы панели

- **Hero и метрики** — профиль ресурсов, счётчик включённых модулей (`FeatureTogglesTab.tsx`).
- **Карточки профилей** Minimal / Standard / Full с иконками, бейджем «Текущий» и выровненными кнопками.
- **Карточки модулей** — Switch, бейдж нагрузки (низкая / средняя / высокая), подсказка при отключении.
- **Фактическое потребление RAM** — замер стека AdminPanelAZ + локальная нода (node agent + OpenVPN/процессы `ANTIZAPRET_PATH`); сторонние проекты на VDS исключены.

#### Конфигурации — карточки клиентов

- **Статус подключения** — бейдж «онлайн / офлайн» на карточке по данным OpenVPN / WireGuard (`ConfigCard.tsx`, `connectionMap`).
- **Фильтры присутствия** — «Онлайн», «Оффлайн», «Заблокированные» рядом с фильтрами срока действия (`ClientPresenceFilter`, `ConfigCardsSection.tsx`).
- **Массовая смена владельца** — операция `change_owner` в `POST /api/configs/bulk` и UI выбора нового владельца (`bulk_config_ops.py`).

#### Настройки — обновления и диагностика

- **`GET /api/system/latest-changelog`** — загрузка `CHANGELOG.md` с `origin/main` (не из локального working tree); парсер версий и секций (`changelog_remote.py`, `UpdatesTab.tsx`).
- **Runbook** — пошаговая диагностика с группировкой проверок, сворачиваемыми блоками и рекомендуемыми командами только при ошибках (`RunbookTab.tsx`, `site_diagnostics.py`).

#### Документация

- **README** — скриншоты интерфейса в `docs/assets/` (конфигурации, NOC, трафик); обновлённый hero-блок.

### 🔄 Changed

#### Навигация — боковое меню

- **Главное меню** (`Layout.tsx`) — пункты сгруппированы: «Операции», «Конфигурация», «Система»; активный пункт с иконкой-плиткой, без blur-эффектов, мешающих читаемости текста.
- **Настройки** (`SettingsNav.tsx`, `SettingsPage.tsx`) — те же принципы: секции, мягкие активные состояния, единая типографика.

#### Конфигурации — страница Dashboard

- **Hero-баннер** — метрики и pill-карточки вместо статичных info-alert (`DashboardPage.tsx`, `MetricCard.tsx`).
- **Карточки клиентов** — адаптивная сетка **3 колонки на 1080p**, **4 колонки на 2K+** (брейкпоинт `2k`); одинаковая высота карточек и выравнивание кнопок внизу; «Удалить» — только иконка (`ConfigCardsSection.tsx`, `ConfigCard.tsx`, `tailwind.config.js`).
- **Массовый выбор** — стилизованный чекбокс (`checkbox.tsx`); удаление тегов с выбранных конфигов.

#### Редактор файлов

- **Подсказки и placeholders** — для каждого типа файла: краткое описание, пример значений и формат ввода (`EditFilesPage.tsx`, `FILE_META`).

#### Настройки — обновления и диагностика

- **Обновления** (`UpdatesTab.tsx`) — pipeline «код → зависимости → сборка → перезапуск»; блок «Что нового» из удалённого changelog; метрики текущей и доступной версии.
- **Runbook** — понятнее статусы шагов; уточнена диагностика режима `BEHIND_NGINX` (когда панель за reverse proxy).

#### Telegram — бот и Mini App

- **Меню бота** — упрощённая навигация, просмотр конфигов и ввод настроек; кнопки меню работают надёжнее (`menu.py`, `configs.py`, `telegram_bot_i18n.py`).

#### Журналы — русские подписи в журнале действий

- **Колонка «Действие»** — технические коды (`login_success`, `settings_cidr_deploy`, `node_activate` и др.) заменены на понятные русские подписи (`actionLogLabels.ts`).
- **Колонка «Детали»** — параметры событий отображаются по-русски: способ входа (пароль / 2FA / Passkey), роли пользователей, цели развёртывания CIDR, узлы, IP, лимиты клиентов и пр. (`actionLogDetails.ts`).
- **Поиск** — учитывает и русские названия действий и деталей, не только исходные коды в БД.

#### Telegram — понятный интерфейс настройки

- **Вкладки** — переименованы для обычного пользователя: «С чего начать», «Данные бота», «Приложение», «Команды бота», «Уведомления» (вместо «Mini App», «Интерактив» и т.п.); под списком вкладок — краткое описание текущего раздела (`telegramLabels.ts`, по аналогии со страницей маршрутизации).
- **Карточки статуса** — статусы на человеческом языке («Подключён», «Работает», «Нужно подключить»); порядок блоков: вход → бот → приложение → команды → уведомления.
- **Шапка страницы** — статусы «Всё работает», «Настройка не завершена», «Нужно подключить бота»; кнопка «Проверить вход» вместо «Открыть /login».
- **Инструкция «С чего начать»** — пошаговый гайд переписан простым языком: что открыть в BotFather, что скопировать и куда вставить.
- **Формы и переключатели** — убран технический жаргон (`webhook`, `Login Widget`, `AdminNotify`, `chat_id`); вместо них — «Подключить бота к панели», «Связь с панелью», «ID чата для резервных копий», «Общий переключатель уведомлений».
- **Предупреждения** — алерты объясняют проблему и куда перейти без терминов вроде webhook и per-user.
- **Отключение модуля** — текст блока «Отключить Telegram» упрощён.

#### Настройки — общий UX/UI

- **Единый стиль вкладок** — hero-полоса с метриками, цветные полоски на карточках, `SectionHeading`, компактные списки и пресеты для числовых полей; общие подписи в `settingsLabels.ts`.
- **Защита входа** (`SecurityTab.tsx`) — секции доступа, активности и интеграций; выровненные пары карточек.
- **Обслуживание VPN** (`MaintenanceTab.tsx`) — пресеты хранения и интервалов.
- **Пользователи** (`UsersTab.tsx`) — hero, выбор роли кнопками, строки вместо таблицы.
- **Мой профиль** (`PersonalTab.tsx`, `TwoFactorTab.tsx`, `PasskeysTab.tsx`) — превью темы, карточки 2FA и passkeys.
- **Выдача VPN-профилей** (`ConfigDeliveryTab.tsx`, `RouteResultsPanel.tsx`).
- **Адрес сайта и HTTPS** (`VpnNetworkTab.tsx`) — карточки режимов с иконками.
- **Резервные копии** (`BackupTab.tsx`) — блоки AdminPanel и AntiZapret с пояснением, что в Telegram уходят отдельные файлы; `OptionCard` с чекбоксом и бейджем Вкл./Выкл.
- **Нагрузка и уведомления** — переработаны `MonitoringTab`, `MonitorSettingsCard`, `AlertRulesCard`; условие срабатывания (сравнение + порог) в одном блоке.
- **Разделы панели** — профили ресурсов и модули вместо кнопок «Включён / Выключен»; подписи RAM берутся из API (`recommended_ram_gb`), формулировка «ориентир ~N GB».

#### Настройки — 2FA

- **QR-код TOTP** — генерация PNG чёрным по белому фону (`totp_service.py`); контейнер `bg-white` в `TwoFactorTab.tsx` для тёмной темы.

#### Backend — резервные копии

- **`_create_backup_with_optional_telegram`** — общая логика создания архива и отправки в Telegram для `create` и `test-telegram`.

### 🐛 Fixed

#### Настройки — резервные копии

- **Отправка в Telegram** — кнопка «Отправить в Telegram» больше не тянет полный архив AntiZapret из настройки авто-копии (`backup_az_enabled`), если на странице снята галочка «Создать полный архив VPN».
- **Тестовая отправка** — `POST /backups/test-telegram` учитывает `include_antizapret_backup` из тела запроса, а не только сохранённый флаг авто-копии.

#### Настройки — 2FA

- **QR на тёмной теме** — SVG без фона был невидим; исправлено PNG + белая подложка.

#### Настройки — разделы панели

- **Карточки профилей** — выровненная высота и кнопки внизу без избыточных пустых блоков.

#### Telegram — Mini App

- **Авторизация в WebView** — Mini App открывался без валидного `initData` внутри Telegram; исправлена передача и разбор initData (`telegramInitData.ts`, `TgAuthContext.tsx`, `vite.config.ts`).

---

## [2.5.0] - 2026-06-30

> **Кратко:** полноценный HA auto-sync (`sync_mode=auto`) — репликация политик, конфигов, routing и CIDR с primary на replica; суммарный трафик по HA-группе; reconcile, opt-in auto-heal и 103+ тестов.

### ✨ Added

#### Мониторинг трафика — суммарный объём по HA-группе

- **Агрегация трафика по Sync Group** — если активный узел входит в HA-группу, страница **Мониторинг трафика** показывает **суммарный** объём по всем узлам группы (primary + replica) для каждого логического клиента (`common_name` + протокол): сумма `RX/TX/всего`, окна `1д/7д/30д` и сессий; `first_seen` = min, `last_seen` = max, `online` = активен на любом узле. График (`/traffic/chart`) и сессии (`/traffic/client-sessions`) сливаются по всем узлам группы.
- **`traffic/ha_aggregate.py`** — `resolve_traffic_scope(db, node_id)`: solo-узел → `[node_id]`; узел в группе → все member-узлы + HA-метаданные (через `find_sync_group_containing_node`, `group_member_node_ids`, `build_ha_metadata`).
- **API** — `TrafficClientRow` дополнен `ha` / `ha_aggregated` / `ha_node_breakdown` (разбивка по узлам); `TrafficOverview.ha_context`; `TrafficClientSessionsResponse.ha_aggregated` + `nodes`; в сессиях — `node_id` / `node_name`.
- **UI** — бейдж «HA: domain (N узл.)» в строке и деталях клиента, блок «По узлам HA-группы» с разбивкой, инфо-баннер «Суммарный трафик HA-группы». Хранение статистики остаётся **per node**; лимиты трафика по-прежнему считаются по каждому узлу отдельно (фаза 2).

#### HA auto-sync (`sync_mode=auto`) — инфраструктура

- **`node_sync/replicate.py`** — центральный диспетчер `replicate_to_replicas`, `ReplicateResult`, `finalize_replicate_outcome` (partial failure → `sync_status=failed`, audit `ha_replicate_partial_failure`), `get_shadow_configs`, `iter_replica_adapters`, enum `ReplicateOperation` (в т.ч. `OPENVPN_DISCONNECT`).
- **`node_sync/policy_sync.py`** — `replicate_policy_op` / `maybe_replicate_policy_op`: block/unblock, traffic limit, WG expiry; копирование policy row через `copy_single_client_policy`.
- **`node_sync/config_sync.py`** — `replicate_config_files` / `maybe_replicate_config_files`; обёртка над `edit_files_transfer`; учёт `CONFIG_FINGERPRINT_EXCLUDE`.
- **`node_sync/antizapret_sync.py`** — репликация `setup` (`filter_ha_replicable_settings`, `ANTIZAPRET_HA_SETTING_EXCLUDE`) и фоновый apply на replica (`enqueue_ha_routing_apply_replicas`).
- **`node_sync/shared_domain.py`** — `apply_shared_domain_to_members`: запись `shared_domain` группы в `OPENVPN_HOST` / `WIREGUARD_HOST` (`/root/antizapret/setup`) на **primary и все replica**, затем `doall.sh` + `client.sh 7` на каждом узле. Эндпоинт `POST /nodes/sync-groups/{id}/apply-shared-domain` (фоновая задача `node_sync_shared_domain`); авто-запуск при создании группы и смене домена + кнопка «Домен → узлы» в UI.
- **`node_sync/provider_sync.py`** — provider files и deploy после compile (`replicate_provider_content`, `deploy_compiled_providers_to_replicas`).
- **`node_sync/client_ops_sync.py`** — `replicate_openvpn_disconnect` / `maybe_replicate_openvpn_disconnect` (best-effort: клиент не online на replica — не ошибка).
- **`policy_import.copy_single_client_policy`** — точечное копирование policy row primary → replica.
- **Настройки `NODE_SYNC_*`** (`.env.example`, `config.py`): `NODE_SYNC_AUTO_REPLICATE_CONFIG_FILES`, `NODE_SYNC_AUTO_REPLICATE_POLICIES`, `NODE_SYNC_REPLICATE_DOALL`, `NODE_SYNC_RECONCILE_*`, `NODE_SYNC_AUTO_HEAL`, `NODE_SYNC_AUTO_HEAL_MAX_FAILURES`.

#### HA auto-sync — хуки API (primary → replica)

| Область | Endpoint / действие | Модуль |
| --------- | --------------------- | -------- |
| Политики клиента | `POST /client-access/*` (block, limit, expiry, defaults) | `policy_sync` |
| VPN-клиенты | create / delete / PATCH cert / metadata | `client_sync` |
| Bulk | block, renew, unblock, delete | `bulk_config_ops` |
| Шаблоны | apply template | `client_templates` |
| CSV import | import row + опц. политики | `config_csv_ops` |
| OpenVPN disconnect | `POST /client-access/openvpn/disconnect` | `client_ops_sync` |
| Настройки списков | `PATCH /settings` | `config_sync` |
| Редактор файлов | `PUT /edit-files/*`, `POST /edit-files/batch` | `config_sync` |
| Route files (Routing UI) | `PUT /routing/files/{file_key}` | `config_sync` (`run_doall=False`) |
| AntiZapret setup | `PUT /routing/antizapret-settings` | `antizapret_sync` |
| Routing apply | `POST /routing/apply` | `antizapret_sync` |
| CIDR providers | `PUT /routing/providers/*`, `POST /routing/sync` | `provider_sync` |

- **Guards primary-only** — `require_ha_primary_for_client_ops` на create/delete/renew/block/import; на replica — 403; список конфигов при активной replica — конфиги primary (`monitoring`, `configs`).

#### HA auto-sync — reconcile и auto-heal

- **`reconcile_worker`** — периодический Verify всех групп; при drift → `sync_status=failed`.
- **Opt-in auto-heal** (`NODE_SYNC_AUTO_HEAL=false` по умолчанию) — incremental heal: `policy_sync`, `config_sync`, `antizapret_sync`; **без** auto Push full; notify после `NODE_SYNC_AUTO_HEAL_MAX_FAILURES` неудач.

#### HA auto-sync — CSV import с политиками

- Опциональные колонки импорта: `traffic_limit_bytes`, `traffic_limit_days`, `block_mode` (`permanent`, `temp`, `temp:N`).
- После create: `AccessPolicyService` на primary → `maybe_replicate_create` → `maybe_replicate_policy_op` (как шаблоны).
- Экспорт CSV включает те же колонки политик.
- Пример: `docs/examples/vpn-configs-import.example.csv`.

#### HA — расформирование Sync Group

- **`node_sync/dissolve.py`** — при удалении группы: снятие `sync_group_id` / `ha_primary_config_id`, shadow → обычные конфиги; файлы на VPN-серверах **не удаляются**.

#### UI — Node Sync / HA

- **`NodeSyncGroupSection.tsx`** — полный список операций в `sync_mode=auto`; polling auto-групп; warning-toast при переходе в `sync_status=failed`; отображение `last_sync_error`.
- **`HaReplicaBanner`**, **`useHaReplicaReadonly`** — replica read-only для client ops.
- **`EditFilesPage.tsx`** — на primary+auto: alert про auto-replicate; «Перенести на узлы» помечен Fallback; на replica transfer скрыт.
- **`DashboardPage.tsx`** — подсказка к импорту CSV (колонки политик, HA replicate).
- Диалог «Расформировать» вместо «Удалить» для Sync Group.

#### Прочее

- **SQLite — `PRAGMA foreign_keys=ON`** — на каждом подключении к основной и CIDR-БД (`apply_sqlite_connection_pragmas`).
- **Личные настройки — часовой пояс** — `users.timezone`, UI в «Настройки → Личные», `TimezoneContext`, `lib/datetime.ts`, заголовок `X-Client-Timezone` для Telegram.

#### Документация

- **`docs/NodeSync.md`** — v2: scope `auto`, partial failure, `NODE_SYNC_*`, route files, disconnect, CSV.
- **`docs/edit-files.md`** — auto-replicate vs manual transfer (fallback).
- **`docs/antizapret-config.md`** — `ANTIZAPRET_HA_SETTING_EXCLUDE`, HA scope setup.
- **`docs/konfiguracii.md`** — формат CSV import с политиками.
- **`docs/traffic-monitoring.md`** — секция HA-групп: суммарный трафик, бейджи, лимиты per node.
- **`reviews/HA-auto-sync-roadmap.md`**, **`reviews/traffic-ha-aggregation-plan.md`** — план auto-sync и агрегации трафика.

### 🔄 Changed

- **`sync_mode=auto`** — не только create/delete клиентов: политики, config/route files, setup/apply, CIDR, OpenVPN disconnect, node defaults, CSV policies, opt-in auto-heal. Partial failure на replica **не откатывает** primary.
- **`client_sync.py`** — create/delete/renew/metadata через `replicate_to_replicas`; `purge_ha_shadow_configs` перед delete primary.
- **`bulk_config_ops.py`** — HA replicate для block/renew/unblock/delete.
- **`reconcile_worker.py`** — классификация drift, incremental heal, notify.
- **`groups.py`** — `require_ha_primary_for_client_ops`, `is_auto_sync_enabled`, preflight validate.
- **`fingerprints.py`** — `CONFIG_FINGERPRINT_EXCLUDE` для node-local файлов (warper).
- **`antizapret_params.py`** — `ANTIZAPRET_HA_SETTING_EXCLUDE`, `filter_ha_replicable_settings` (WARP-флаги excluded; `OPENVPN_HOST` / `WIREGUARD_HOST` реплицируются).
- **Удаление узла** — `purge_node_related`: ConfigTag, ClientTemplate, AlertRule, отвязка `ha_primary_config_id`.
- **Удаление пользователя** — `_purge_user_before_delete`: UserReminderLog, WebAuthnCredential.
- **Push full** остаётся для bootstrap / disaster recovery, не для каждой правки config.
- **HA Push full переносит `OPENVPN_HOST` / `WIREGUARD_HOST` с primary на replica** — `run_push_full` читает непустые хосты из `setup` primary и пишет их в `setup` каждой replica **перед** restore, так что `client.sh 7` (recreate_profiles) внутри restore регенерирует профили клиентов с правильным хостом. Архив `client.sh 8` файл `setup` не содержит, поэтому раньше в `manual_full` хосты по Push full не переносились. В `auto` хосты уже реплицируются автоматически при правке настроек на primary (`replicate_antizapret_settings` + `enqueue_ha_routing_apply_replicas` → doall + recreate). Результат Push full содержит `host_copy` (по узлам).

### 🐛 Fixed

- **HA: `OPENVPN_HOST` / `WIREGUARD_HOST` пустые в `/root/antizapret/setup` после изменения состава группы** — `NodeSyncGroupSection.tsx` запускал apply-shared-domain только при изменении `shared_domain`; добавление/смена replica (или primary) без смены домена оставляли новый узел с пустыми хостами. Теперь apply запускается также при изменении состава группы (primary или список replica). Текущее состояние лечится кнопкой «Домен → узлы».
- **Удаление primary VPN-клиента** — `purge_ha_shadow_configs` в роутере и bulk delete (FK на `ha_primary_config_id`).
- **`test_verify_primary_missing_returns_gracefully`** — корректный mock `db.get` без нарушения FK при `primary_node_id` missing.

### 🧪 Tests

#### HA auto-sync — unit / integration (103+ в `test_node_sync_*`)

| Модуль | Файлы |
| -------- | ------- |
| Replicate / client | `test_node_sync_replicate.py`, `test_node_sync_client_sync.py`, `test_node_sync_manual_link.py` |
| Policy | `test_node_sync_policy_sync.py`, `test_node_default_policy.py`, `test_client_templates_ha.py` |
| Config files | `test_node_sync_config_sync.py`, `test_node_sync_config_hooks.py` |
| AntiZapret | `test_node_sync_antizapret_sync.py`, `test_node_sync_antizapret_hooks.py`, `test_antizapret_ha_settings.py` |
| CIDR / providers | `test_node_sync_provider_sync.py`, `test_node_sync_provider_hooks.py`, `test_node_sync_provider_deploy.py`, `test_cidr_ha_deploy_targets.py` |
| Routing | `test_node_sync_routing_apply_hooks.py`, `test_node_sync_routing_sync_hooks.py`, `test_node_sync_routing_files_hooks.py` |
| OpenVPN disconnect | `test_node_sync_openvpn_disconnect.py` |
| CSV + policies | `test_config_csv_import_ha.py`, `test_config_csv_import_export.py` |
| Reconcile / heal | `test_node_sync_reconcile.py` |
| Verify / push / dissolve | `test_node_sync_verify.py`, `test_node_sync_push_full.py`, `test_node_sync_dissolve.py`, `test_node_sync_fingerprints.py` |
| Guards / PATCH | `test_ha_replica_client_guard.py`, `test_configs_ha_patch.py`, `test_client_access_openvpn_block.py` |
| Settings | `test_node_sync_config.py` |

- **`test_sqlite_foreign_keys.py`** — `foreign_keys=1` на SQLite engine.
- **`test_nodes_delete.py`**, **`test_user_delete.py`** — каскадная очистка при удалении узла/пользователя.

#### E2E checklist (roadmap §7)

- **Integration-proxy:** прогнан 2026-06-19, **103 passed** (mock adapters, `auto_group_db`).
- **Live staging:** открыт — требует Sync Group + Push full + Verify на двух VPN-узлах (см. `reviews/HA-auto-sync-roadmap.md`).

---

## [2.4.0] - 2026-06-18

### ✨ Added

#### AZ-WARP (коммиты `Test AZ-warp`, 2026-06-17)

- **API — домены и IP-диапазоны (текстовый режим)** — `GET/PUT /api/warper/domains/text`, `GET/PUT /api/warper/ip-ranges/text`; прокси в `WarperService` и node agent.
- **API — настройки режима** — `GET /api/warper/settings/options`; переключение режима: `POST …/settings/mode/warp`, `…/mode/slave`, `…/mode/wg`; `PUT …/settings/fullvpn`, `…/settings/subnet` (списки WARP-ключей и WG-конфигов с узла).
- **API — каталог приложений** — `GET /api/warper/catalog/search`, `…/installed`, `…/show/{name}`; `POST …/catalog/add`, `…/remove`, `…/update`, `…/refresh`.
- **Node agent** — прокси warper-команд (domains, ip-ranges, settings, catalog, traffic) на удалённых узлах.
- **UI — вкладка «Каталог»** — `CatalogTab`: поиск, установленные приложения, add/remove/update, обновление кэша.
- **UI — «Домены» и «IP-диапазоны»** — компактные формы + текстовый редактор списков (`DomainsTab`, `IpRangesTab`).
- **UI — «Настройки»** — выбор режима WARP / slave / WireGuard, full VPN, subnet, MTU, log level, sing-box actions (`SettingsTab`).
- **UI — «Мониторинг» и «Трафик»** — переработанные `MonitoringTab`, `TrafficTab`, `StatusSection`; общий layout `WarperSection`.
- **UI — график трафика** — `WarperTrafficChart` (Recharts), адаптация `ChartResponsive` под warper-данные.
- **Тесты** — `test_warper_service.py` (+247 строк), расширены `test_warper_api.py`, `test_node_adapter_parity.py`.

#### После AZ-WARP

- **Узлы — массовые операции** — выбор нескольких узлов (select-all): health check, rolling update, mTLS, удаление.
- **Версия node agent** — единая константа `NODE_AGENT_VERSION` **1.1.0** (local adapter, node agent, rolling update).
- **HA replica — защита от дрейфа** — блокировка create/delete/renew/block клиентов на replica; `HaReplicaBanner`, `useHaReplicaReadonly`; роль HA в `GET /nodes/active`; на replica список клиентов — конфиги **primary**.
- **Трафик — UX мониторинга** — inline-раскрытие деталей клиента (`TrafficClientDetails` вместо `TrafficClientFocusPanel`); блок «никогда не подключались»; скрытие обслуживания OpenVPN-лога при `OPENVPN_LOG=n`.
- **Политики per-node — `client_hints`** — в `GET /api/client-access/policy-summary-by-node`: имя клиента, протокол, лимит, блокировка (UI таблицы обновлён).

### 🔄 Changed

- **Узлы — политики per-node** — блок «Политики per-node» временно скрыт со страницы **Узлы** (API и wizard в коде).

### 🐛 Fixed

- **CSP — meta csp-nonce** — корректная подстановка nonce в `<meta name="csp-nonce">` (regex callback вместо backref, иначе ломались графики warper).
- **WireGuard — онлайн-статус** — подключён только peer с handshake за последние **3 минуты** (`wireguardStatus.ts`, backend parsing).
- **HA — sync fingerprints** — исправлен расчёт отпечатков в `node_sync/fingerprints.py` (`test_node_sync_fingerprints.py`).
- **CSP — Radix Select** — nonce во viewport Select + scrollbar-стили.
- **Установка — nginx/CORS** — публичный origin при нестандартном HTTPS-порте (`nginx_public_origin_host`, `__HTTPS_REDIRECT_SUFFIX__`, CORS в install-wizard).
- **Главная — падение** — `ReferenceError: useFeatureModules is not defined` в `ConfigCardsSection`.
- **Wizard политик per-node** — сброс маршрута «Не задано» (`route_clear`); сброс лимита при пустом поле.

### 🧪 Tests

- `test_warper_service.py` — settings modes, catalog, domains/ip-ranges text, traffic.
- `test_node_sync_fingerprints.py` — отпечатки HA sync group.
- `test_http_security.py` — CSP nonce injection в meta-тег.

---

## [2.3.0] - 2026-06-16

### ✨ Added

- **Маршрутизация / CIDR — вкладка «Анализ»** — разбор лога [TCP 16-20 DPI checker](https://hyperion-cs.github.io/dpi-checkers/ru/tcp-16-20/): вставка лога, рекомендации по включению CIDR-списков; URL `?tab=analysis`; карточка быстрой навигации на странице маршрутизации.
- **API `POST /api/routing/cidr-db/analyze-dpi`** — парсер `analyze_dpi_log`: консоль checker, таблица 6 и 4 колонок; сопоставление узлов с `*-ips.txt`.
- **DPI checker suite** — `dpi_checker_suite.py`: маппинг ID узлов checker → hostname (например `SE.AKM-01` → `cdn.apple-mapkit.com`, `PL.AKM-01` → `www.mobil.com.se`).
- **Умные рекомендации** — уровни must / should / consider / skip с confidence (`high`, `medium`, `weak`, `inconclusive`); `actionable_files` только для надёжных сигналов; учёт противоречий (detected на одном узле провайдера и not detected на другом).
- **UI «Анализ»** — предупреждения (checker без VPN, detected ≠ «сайт не открывается», CIDR для split-маршрутизации); карточки узлов с hostname и ссылкой «открыть»; таблица всех узлов лога (alive, method, tcp 16-20); переход к провайдерам для actionable-списков.

### 🔄 Changed

- **Парсер DPI** — извлечение `alived: yes/no/unknown`, `method: N`, enrichment узлов полями `host`, `checker_provider`, `checker_country`.
- **Маршрутизация / CIDR — провайдеры** — широкая таблица заменена на двухколоночный grid карточек; тематические scrollbar-стили для таблиц.

### 🧪 Tests

- `test_analyze_dpi_log_marks_mixed_akamai_as_weak_must` — mixed Akamai (detected + not detected) → `confidence=weak`, `actionable=false`.

---

## [2.2.0] - 2026-06-16

### ✨ Added

- **Пользовательская документация** — простые инструкции по разделам веб-панели: [`docs/README.md`](docs/README.md), модули меню (`konfiguracii.md`, `noc-monitoring.md`, …), подразделы настроек [`docs/nastrojki/`](docs/nastrojki/README.md).
- **Редактор файлов — перенос на другие узлы** — копирование конфигурации AntiZapret с активного узла на один или несколько online-узлов: API `POST /api/edit-files/transfer` (`file_keys`, `target_node_ids` / `all_online`, `run_doall`, `content_overrides`); сервис `edit_files_transfer.py`; результат по каждому узлу в `per_node`; audit log `edit_files_transfer`. UI: кнопка **«Перенести на узлы»** в шапке страницы, диалог с выбором «все файлы» / «только открытый файл», целевых узлов и опционального doall.sh; предупреждение при несохранённых правках. Тесты: `test_edit_files_transfer.py`.
- **Маршрутизация / CIDR — UX pipeline** — пошаговый гид **Ingest → Compile → Deploy → Провайдеры** (`RoutingWorkflowGuide`, `routingWorkflow.ts`): текущий шаг, кнопка «Следующий шаг», кликабельные этапы с переходом на вкладку/якорь; карточки быстрой навигации (`RoutingSectionCards`); синхронизация вкладок с URL (`?tab=overview|providers|pipeline`); описания под вкладками; липкая навигация по этапам 1–3 на вкладке Pipeline (`#pipeline-stage-1/2/3`).
- **Маршрутизация / CIDR — провайдеры** — быстрые фильтры (все / включённые / ошибки / нужен deploy / нужна сборка); колонка CIDR объединена (**БД / Контр. / Узел**); кликабельные подсказки «нужен deploy / сборка» с переходом на Pipeline.
- **Маршрутизация / CIDR — откат runtime_backups** — панель `RuntimeBackupsPanel`: человекочитаемые даты вместо `20260616T190446Z`, таблица вместо кнопок-«простыни», сворачиваемый список, плашка «Откат выполнен» после успешного rollback.
- **CIDR deploy — apply после развёртывания** — флаг `recreate_profiles_after` в `POST /api/routing/cidr-db/deploy`; на этапе 3 кнопка **«Развернуть + doall + client.sh 7»** (deploy + doall.sh + перегенерация профилей WG/AWG).
- **CSP — nonce для динамических `<style>`** — `style-src 'nonce-…'` в заголовке (как для scripts); `<meta name="csp-nonce">` и `initCspNonce()` → `window.__webpack_nonce__` для Radix scroll-lock; директива `style-src-attr 'unsafe-inline'` для позиционирования Radix Popper.

### 🔄 Changed

- [`README.md`](README.md) — длинные блоки NOC/трафик/узлы заменены ссылками на user docs.
- [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) — карта UI ↔ user doc, актуальное дерево `docs/`.
- **Редактор файлов — UX переноса** — действие переноса вынесено из панели редактора в шапку страницы (операция на уровне узла, а не отдельного файла); по умолчанию в диалоге выбраны все файлы; переработан UI диалога (схема «источник → цели», шаги, карточки узлов, primary-кнопка, сводка результата).
- **Терминология UI** — единообразно **«узел / узлы»** вместо «нода / ноды» в редакторе файлов, CIDR Pipeline, провайдерах, deploy preview и связанных toast/backend-сообщениях (в коде по-прежнему `Node`, `node_id`).
- **Маршрутизация / CIDR — workflow** — после успешной сборки (compile) приоритет у этапа Deploy, а не у «1 провайдер ждёт сборки»; необязательные провайдеры без файла помечаются предупреждением, не блокируя deploy; корректные формы «1 провайдер / 2 провайдера / 5 провайдеров» (`pluralProviders`, `pluralFiles`).
- **Маршрутизация / CIDR — layout** — детальная панель pipeline (`PipelineStatusBar`) перенесена на вкладку **Обзор**; гид и карточки навигации — над вкладками.
- **Маршрутизация / CIDR — этап 3** — убрана кнопка **«Сгенерировать + doall»** (сборка — этап 2); отдельно **«Развернуть»** (только файлы) и **«Развернуть + doall + client.sh 7»** (полное применение на узле).

### 🗑️ Removed

- **Roadmap-документы** — `docs/Idei.md`, `docs/Etapy-prompty.md`, `docs/Backlog-otkryto.md` (задача **10.1 PostgreSQL** снята с плана: для типичного деплоя SQLite достаточен).
- **Провайдеры — кнопка «Загрузить»** — ingest CIDR только через выбор провайдеров на вкладке **Pipeline** (этап 1), не из таблицы провайдеров.

### 🐛 Fixed

- **Маршрутизация / CIDR — workflow после compile** — тост «CIDR-файлы собраны», но гид оставался на этапе 2: исправлена логика `getRoutingWorkflowState` (приоритет deploy, `optionalCompileRemaining`).
- **CSP — ошибки в консоли** — «Applying inline style violates style-src 'self'» при открытии диалогов/select (Radix): nonce на `<style>` + `style-src-attr` для inline positioning.

### 🔒 Security

- **CSP** — `style-src 'self' 'nonce-…'` для runtime `<style>` (scroll-lock); `style-src-attr 'unsafe-inline'` только для атрибутов `style` (Radix Popper); scripts — nonce без изменений.

---

## [2.1.0] - 2026-06-16

### ✨ Added

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

### 🔄 Changed

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

### 🐛 Fixed

- **Node Sync reconcile worker** — восстановлен импорт `run_node_sync_reconcile_loop` в `lifespan_workers.py` (воркер не стартовал).
- **Установка — Let's Encrypt** — при недоступном DNS/порте 80 установка продолжается без HTTPS (`NGINX_FAIL_SOFT`); подсказка про `./scripts/nginx-setup.sh`.
- **Мастер установки** — безопасные значения по умолчанию для `WIZ_TELEGRAM_*` / `WIZ_AUTO_BACKUP_*` при seed в БД.

### 🔒 Security

- **CSP** — `style-src 'self'` на основных страницах; scripts — nonce (без изменений).
- **Secrets rotation** — guided wizard с явным подтверждением `ROTATE`; без silent overwrite `.env`.

### 📦 Dependencies

- **reportlab** — 4.2.5 (weekly NOC PDF).
- **cryptography** — 44.0.0 → 46.0.3.

---

## [2.0.0] - 2026-06-16

Major release: roadmap этапы 1–8 (и большая часть 9) — prod foundation, admin productivity, multi-node, CIDR safety, Node Sync HA, self-service, ops/security. Открытые пункты roadmap — см. [docs/Backlog-otkryto.md](docs/Backlog-otkryto.md).

### ✨ Added

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

### 🔄 Changed

- **NOC — federated overview** — aggregate endpoint с кэшем; режим «Все узлы» без N+1 с фронта.
- **Lifespan** — фоновые workers стартуют через `lifespan_workers.py` с учётом feature toggles и resource profile.
- **Установка** — Node.js **20+**; deep health check до 90 с; resource profile в wizard; создание `backend/data/cidr/` до миграций.
- **Prod start** — `start.sh` пропускает `npm run build:all`, если dist/tg_mini уже собраны (`ADMINPANELAZ_FORCE_FRONTEND_BUILD=1` для принудительной пересборки).
- **Frontend — Vite 6.4.2** — `build.target: es2022`; overrides `esbuild ^0.28.1`.
- **Трафик** — убран дублирующий bar-chart «Топ клиентов (7д)»; фокус на выбранном клиенте.
- **README / SECURITY** — таблица VDS → profile, Redis для multi-worker, passkeys, health/metrics endpoints.
- **Git** — `.gitignore`: `backend/app/static/tg_mini/`, кэш Vite.
- **Обновления UI** — «Настройки → Обновления» отражает полный цикл deps + build + restart.

### 🐛 Fixed

- **Установка — CIDR БД** — `unable to open database file` на чистой установке (каталоги до `create_all`).
- **Prod start** — лишняя пересборка frontend при каждом systemd restart (~25 с без listening port).
- **npm audit** — Vite 6.4.2 + esbuild override без перехода на Vite 8.
- **UI — git pull only** — «Применить обновление» раньше не ставило deps и не пересобирало UI.

### 🔒 Security

- Passkeys optional alongside TOTP; audit stream для compliance; CSP nonce для scripts; OpenAPI и webhooks — admin-only.

---

<a id="архив-версии-1x-и-0x"></a>

<details>
<summary><strong>📦 Архив: версии 1.x и 0.x</strong> — ранние релизы миграции с AdminAntizapret</summary>

## [1.9.0] - 2026-06-15

### ✨ Added

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

### 🔄 Changed

- **NOC — UI** — убраны неинформативные графики «Статус служб» и «Трафик сессий»; все аналитические карточки (линия, столбцы, geo) в едином блоке над вкладками; согласованные цвета протоколов (OpenVPN / WireGuard).
- **NOC — вкладка VPN-клиенты** — выровнен заголовок и панель фильтров (поиск, протокол, «Только онлайн» в одну линию).
- **NOC — вкладка VPN-узел** — убран бейдж с числом сырых снимков метрик (`sample_count`) на табе; счётчик остаётся в подписи графика внутри вкладки.
- **Трафик** — страница переработана вокруг фокуса на выбранном клиенте; улучшена читаемость таблиц и адресов.
- **Recharts** — глобальные стили тултипов для тёмной темы: читаемый текст на фоне `popover`.
- **Telegram** — обработчики бота делегируют в меню/UI-модули; обновлены `docs/Telegram.md` и i18n.

### 🐛 Fixed

- **NOC — overview 500** — исправлена ошибка Pydantic при обогащении клиентов гео (`model_copy(update=...)` вместо `**model_dump()` + дублирующие поля).
- **Recharts** — нечитаемый текст в тултипах при наведении на графики (тёмный текст на тёмном фоне).
- **Журналы — подключения** — исправлен подсчёт WireGuard-пиров и общего числа на вкладке «Подключения»: учитываются только онлайн-пиры с handshake (как в NOC-мониторинге); OpenVPN подписан как «сессии».

---

## [1.8.0] - 2026-06-14

### 🗑️ Removed

- **Игровые фильтры** — полное удаление функциональности include/exclude для игровых доменов и IP (~75 игр из каталога AdminAntizapret):
  - **UI** — вкладка «Игровые фильтры» на странице маршрутизации (`GameFiltersTab`, deep link `?tab=games`).
  - **API** — `GET/POST /api/routing/game-filters`, сохранение режимов в `app_settings.game_filter_modes`.
  - **Node agent** — `POST /routing/game-filters/sync`.
  - **Backend** — модули `game_catalog.py`, `game_server_data.py`, `game_filters.py`, `game_filter_sync.py`, `pipeline/games.py`, `pipeline/games_catalog.py`, router `game_filters.py`; метод `NodeAdapter.sync_game_routes_filter`.
  - **CIDR pipeline** — синхронизация `AZ-Game-include-*` / `AZ-Game-exclude-*` при generate/deploy; поле `include_game_hosts` в `CidrDbGenerateRequest`.
  - **Константы/env** — `CIDR_AZ_GAME_*`, `CIDR_GAME_LEGACY_*`, `AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT` и связанные маркеры managed-блоков.
  - **Тесты** — `test_game_filters_sync.py`, `test_game_catalog_coverage.py`; game-related кейсы в `test_cidr_list_updater.py`.

### 🔄 Changed

- **CIDR pipeline** — generate/estimate/deploy больше не трогают игровые конфиги AntiZapret; лимит маршрутов OpenVPN всегда enforced (без env-обхода через game filter).
- **README** — убраны упоминания game filters из матрицы возможностей и чеклиста.
- **Telegram — Mini App** — inline HTML в `tg_mini.py` заменён на static React-сборку; deprecated `POST /api/tg-mini/send-config`.

### 🐛 Fixed

- **Тесты** — стабильный прогон на машинах с production `.env` (`ENFORCE_HTTPS`, `BEHIND_NGINX`): autouse-изоляция env в `conftest.py`, патч `http_security.get_settings` в `api_test_env`; исправлены ожидания в `test_profile_files`, `test_warper_service`, `test_api_rate_limit` (patch middleware import path).
- **Telegram webhook** — IP-allowlist использует `X-Real-IP` / `request.client`, без доверия к подменённому `X-Forwarded-For`.
- **Telegram Mini App** — проверка `auth_date` в `init_data`; запрет смены `telegram_id` через `PATCH /admin-notify`.
- **Telegram Mini App** — `PATCH /telegram-settings` делегирует в `maintenance.update_telegram_settings` (interactive + webhook lifecycle).
- **Telegram bot /settings** — webhook регистрируется с публичным URL из `mini_app_url`, не `panel.local`.
- **Debug** — удалена временная agent-log инструментация из `auth.py` и `LoginPage.tsx`.

### ✨ Added

- **Telegram — интерактивный бот (фазы 0–4)** — webhook `POST /api/telegram/webhook/{secret}`, IP-allowlist Telegram, rate limit; команды `/start`, `/link`, `/status`, `/configs`, `/config`, `/help`, `/settings` (admin, inline-меню настроек панели).
- **Telegram — /settings в боте** — разделы Telegram, AdminNotify, бэкапы, мониторинг, безопасность, обслуживание; FSM-ввод чисел/токена; confirm для опасных действий; `action_logs` с `source=telegram_bot`.
- **Telegram — Mini App v2** — React entry `frontend/src/tg-mini/` (Dashboard, Configs, Settings, TelegramSettings); Vite build → `backend/app/static/tg_mini/`; API: files, send (`self`|`chat`), QR-link, admin-notify и telegram-settings proxy.
- **Telegram — фаза 0** — `TelegramTab`: username, max auth age, Mini App URL, interactive bot + webhook UI, notify_on_backup; `UsersTab`: Telegram ID; Login Widget — причина отключения; send-config на `user.telegram_id`; AdminNotify при PATCH telegram settings; `GET /api/telegram/link-code`.
- **Telegram — фаза 4** — единый словарь RU `telegram_bot_i18n.py`; команды `/cidr` (статус pipeline) и `/warper` (статус AZ-WARP, если модуль включён).
- **Документация** — обновлены `docs/Telegram.md` и чеклист регрессии Telegram в `README.md`.
- **Тесты** — `test_telegram_settings.py`, `test_telegram_webhook.py` (callback_query, inline keyboard), `test_telegram_bot_settings.py`, `test_tg_mini_routes.py`, `test_tg_mini_send_config.py`.

### 📋 Migration notes

- **`app_settings.game_filter_modes`** — orphan-записи в БД можно оставить или удалить вручную; на работу панели не влияют.
- **`AZ-Game-*` на узлах** — существующие файлы в `config/` AntiZapret больше не обновляются кодом; при необходимости очистите вручную или перезапишите через AntiZapret.

---

## [1.7.0] - 2026-06-14

### ✨ Added

- **QR-коды** — для OpenVPN-профилей, не помещающихся в QR (~4.5 КБ), автоматический fallback на одноразовую ссылку скачивания; заголовки ответа `X-Qr-Content` (`profile` / `download-link`) и `X-Qr-Download-Url`.
- **UI — QR-код** — кнопка «Скопировать ссылку» в диалоге QR при режиме download-link; подсказка, что конфигурация слишком большая для прямого QR.
- **Тесты** — `test_qr_generator.py` (лимит размера, fallback на ссылку, заголовки API).
- **AZ-WARP (WARPER)** — интеграция точечной маршрутизации доменов и IPv4-подсетей через Cloudflare WARP на VPN-узлах: `WarperService` → `warper_api`, API `/api/warper/*`, endpoints node agent `/warper/*`, feature toggle `FEATURE_WARPER_ENABLED`.
- **UI — AZ-WARP** — страница `/warper` (пункт меню «AZ-WARP»): домены (добавление, импорт, синхронизация), встроенные списки Gemini/ChatGPT, IP-подсети, мониторинг (статус, трафик, логи sing-box, диагностика `doctor`), настройки (MTU, уровень логов, sing-box).
- **UI — AZ-WARP** — шапка со статусом узла и быстрым вкл/выкл; сводные карточки с переходом на вкладки; переключатели встроенных списков вместо пар кнопок «вкл/выкл».
- **Документация** — `docs/AZ_WARP_INTEGRATION_PLAN.md`, `docs/VPN_FEATURES_BACKLOG.md`.
- **Тесты** — `test_warper_service.py`, `test_warper_api.py`; parity `get_warper_*` в `test_node_adapter_parity.py`; `test_git_pull_resets_after_diverged_history` в `test_node_update.py`.

### 🐛 Fixed

- **QR-коды** — исправлена ошибка «Ошибка генерации QR» для OpenVPN/AntiZapret `.ovpn` (встроенные сертификаты превышают ёмкость QR); WireGuard/короткие профили по-прежнему кодируются целиком.
- **API client** — `fetchQrBlob`: разбор `detail` из ответа бэкенда, `credentials: 'include'`, обновление токена при 401, заголовок `X-Web-Session-Id`.
- **AZ-WARP — health** — установка определяется по `warper.sh` и `warper_api`, не только по симлинку `/usr/local/bin/warper`; в алертах — `missing_components` и подсказка переключить активный узел.
- **AZ-WARP — doctor** — при ошибках проверок API возвращает полный список результатов, а не 502 с обрезанным текстом; UI показывает сводку OK/ошибок и каждую проверку отдельной строкой.
- **AZ-WARP — настройки / IP-подсети** — `get_mode()` и fallback чтения `ip-ranges.txt` / `domains.txt` при сбое CLI; корректный парсинг встроенных списков по маркерам в `domains.txt`.
- **AZ-WARP — UI** — если WARPER не установлен на активном узле, вкладки управления скрыты; блок «Управление недоступно» с командой установки и ссылкой на узлы (без лишних API-запросов).
- **Обновление узла** — после squash/force push на `main` git pull на ноде выполняет `reset --hard origin/main` при чистом working tree; в диалоге обновления — признак расходящейся истории.
- **API client** — исправлена ошибка `body stream already read` при разборе HTTP-ошибок (однократное чтение тела ответа).

### 🔄 Changed

- **UI — AZ-WARP** — вкладки «Трафик», «Статус», «Логи» и «Диагностика» объединены в одну «Мониторинг»; улучшены таблица доменов, настройки и карточки сводки.

---

## [1.6.0] - 2026-06-11

### ✨ Added

- **CIDR — отдельная БД `cidr.db`** — таблица `provider_cidr` вынесена из `adminpanel.db` в `data/cidr/cidr.db` (`CIDR_DATABASE_URL`); при старте одноразовая миграция через ATTACH + DROP в основной БД.
- **CIDR — быстрая запись ingest** — CSV-staging и нативный bulk-import в SQLite (`cidr_csv_import.py`); каталог staging `data/cidr/staging`.
- **CIDR — частичное обновление провайдеров** — `selected_files` в `POST /api/routing/cidr-db/refresh`, `generate` и `deploy`; режим `retry_failed_mode` (`last` / `selected`) для повторной загрузки только ошибочных.
- **UI — выбор провайдеров** — компонент `ProviderFileSelection`: поиск, фильтры по категории (CDN / Облако / Хостинг), компактная сетка 4–6 колонок, итог «выбрано N · ~X CIDR»; кнопка быстрой загрузки одного провайдера на этапе 1 и во вкладке «Провайдеры».
- **vnStat на удалённых узлах** — `scripts/setup-vnstat.sh`; подсказки в мониторинге, если на активной VPN-ноде нет vnstat.
- **VPN-профили** — понятные имена файлов при скачивании (`AZ-client.ovpn`, `VPN-client.ovpn` и т.п.) для OpenVPN, WG, AWG, одноразовых ссылок и Telegram.
- **Uninstall** — симметричная очистка iptables/ufw; `--purge-all` и `--remove-backups` в меню установщика.

### 🐛 Fixed

- **CIDR ingest** — тяжёлая запись CIDR больше не блокирует основную SQLite-панель; прогресс масштабируется по числу выбранных провайдеров (не «застревает» на 5–75 % при полном refresh).
- **CIDR pipeline UI** — polling фоновых задач: таймаут, счётчик ошибок, корректное завершение при сбоях сети.
- **AWG/WG профили** — скачивание и бейджи учитывают активную вкладку; batch-загрузка различает OpenVPN и WireGuard с одним именем; точнее сопоставление файлов на узле.
- **mTLS** — включение per-node без обрыва HTTP: синхронный restart не рвёт provision-ответ; настройки пишутся в `backend/node_agent.env`; ожидание подъёма агента по HTTPS.
- **ConfigCard** — исправления отображения и работы карточек конфигурации VPN-клиентов.
- **UI** — глобальный прогресс-бар фоновых задач закреплён внизу экрана.

### 🔄 Changed

- **Бэкапы** — `BackupManager` и restore включают `data/cidr/cidr.db` (`components: cidr_db`).
- **UI — CIDR Pipeline (этап 1)** — перед «Обновить из интернета» выбираются провайдеры; динамическая подпись кнопки («1 провайдер» / «N провайдеров» / «все»); кнопка «Повторить ошибочные».
- **UI — вкладка «Провайдеры»** — скрыты технические `*-ips.txt`; категории на русском; компактный формат чисел CIDR (`32k`); кнопка «Загрузить» вместо «Ingest».
- **`.env.example`** — `CIDR_DATABASE_URL`, `CIDR_DB_STAGING_DIR`.
- **Тесты** — `test_cidr_database_migration.py`, `test_cidr_csv_import.py`; обновлены `test_backup_manager.py`, `test_cidr_db_updater_service.py`.

---

## [1.5.0] - 2026-06-10

### ✨ Added

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

### 🐛 Fixed

- **CIDR refresh** — SQLite WAL + `busy_timeout` + retry commit при `database is locked`; устранены 500 при «Обновить из интернета».
- **CIDR compile** — исправлен путь `LIST_DIR` (файлы писались в `backend/app/data/…`, UI читал `backend/data/…`); добавлен `netaddr` (ошибка «netaddr package is required»).
- **Antifilter refresh** — batch commit при сохранении ~15k CIDR; прогресс по батчам; авто-сброс зависших задач по таймауту.
- **CIDR pipeline UI** — polling задач изолирован от глобального ProgressContext; exempt rate limit для `/api/routing` и `/api/tasks`; корректное возобновление `active_task` после перезагрузки страницы.
- **Обновление узла** — перезапуск node agent после git pull через `systemctl restart adminpanelaz-node`, если unit установлен; лог в `update-restart.log`.

### 🔄 Changed

- **CIDR generate** — compile всегда на контроллере; `artifact_stamp` (hash артефактов) в result задачи; deploy на удалённые ноды через `RemoteNodeAdapter.save_provider_content`.
- **Узлы** — обновление узла только для node agent: убраны AntiZapret из `NodeUpdateDialog`, API `GET/POST /api/nodes/{id}/updates|update` и колонка `az` на странице «Узлы».
- **mTLS** — `NODE_AGENT_MTLS_ENABLED` в `.env` панели deprecated; режим соединения задаётся per-node (`nodes.mtls_enabled` в БД). Улучшены сообщения об ошибках SSL при несовпадении HTTP/HTTPS.

---

## [1.4.3] - 2026-06-09

### ✨ Added

- **`LOCAL_ANTIZAPRET_ENABLED`** — режим «только панель» в мастере не создаёт локальный узел; `sync_local_node()` синхронизирует запись при старте.
- **`openvpn_cert.py`** — чтение срока OpenVPN-сертификата с node agent (блок `<cert>` в `.ovpn`); автозаполнение `cert_expire_days` при списке конфигов и синхронизации.
- **Тесты** — `test_openvpn_cert.py`.

### 🐛 Fixed

- **Удалённые узлы** — живой health-check на `GET /api/nodes/active`; автообновление статуса в шапке (poll + visibility); предупреждение при добавлении offline-узла; подсказки в мастере/node agent.
- **Карточки клиентов** — трафик с ноды для импортированных клиентов без строки политики; срок сертификата с узла вместо «не в панели».
- **Страница `/traffic`** — падение React #130 (`EmptyState` без `icon`); таймаут загрузки 25 с; fallback статистики из БД при недоступной ноде; безопасный рендер графиков.
- **Установка** — `seed-admin-user.py` / `seed-wizard-db.py` и `install.sh` запускают seed из `backend/` (корректный путь к SQLite); исправлен subshell в `seed_wizard_db_settings`.
- **HTTP LAN** — `COOP` только по HTTPS; удалены Google Fonts из `index.html` (конфликт с CSP); иконка по умолчанию в `EmptyState`.

### 🔄 Changed

- **`TRAFFIC_SYNC_INTERVAL_SECONDS`** — значение по умолчанию `30` → `60` (prod-баланс: учёт лимитов трафика и нагрузка на SQLite/worker).
- **Мастер установки** — уточнён текст режима «только панель (управление удалёнными узлами)».

---

## [1.4.2] - 2026-06-08

### ✨ Added

- **Test suite parity audit (фаза 32)** — `test_aa_parity_audit.py`: матрица AA→AZ для всех 53 модулей AdminAntizapret + targeted tests (login captcha threshold, traffic collector rows, wg runtime subprocess errors).

### 🔄 Changed

- **Test count** — 53 modules / 414 tests (parity с AA по числу модулей; 9 AA-модулей задокументированы как N/A).
- **`MIGRATION.md`**, **`MIGRATION_PLAN.md`**, **`README.md`** — In-panel pytest → ✅.

---

## [1.4.1] - 2026-06-08

### ✨ Added

- **Scanner dwell/window UI (фаза 31)** — `scanner_window_seconds`, `block_ip_blocked_dwell`, `ip_blocked_dwell_seconds` в API и SecurityTab.
- **Tests** — `test_security_scanner_settings.py`.

### 🔄 Changed

- **`ip_restriction.py`** — runtime scanner/dwell settings читаются из AppSetting (не захардкожены).
- **`MIGRATION.md`**, **`MIGRATION_PLAN.md`**, **`README.md`** — безопасность / scanner dwell → ✅.

---

## [1.4.0] - 2026-06-08

### ✨ Added

- **Game filters exclude sync (фаза 30)** — `/routing/game-filters/sync` использует полный `sync_game_routes_filter` из `pipeline/games.py` (include + exclude, punch, `AZ-Game-*` файлы).
- **`game_filter_sync.py`** — path patching + `run_sync_game_routes_filter`; `NodeAdapter.sync_game_routes_filter` для local и remote узлов.
- **Node agent** — `POST /routing/game-filters/sync`.
- **Tests** — `test_game_filters_sync.py`.

### 🔄 Changed

- **`game_filters.py`** — только UI state (`get_game_filters_state`); упрощённый legacy sync удалён.
- **`MIGRATION.md`**, **`MIGRATION_PLAN.md`**, **`README.md`** — game filters exclude → ✅.

---

## [1.3.1] - 2026-06-08

### ✨ Added

- **Ops console menu (фаза 29)** — `scripts/adminpanel-menu.sh`: интерактивное меню и флаги `--restart`, `--update`, `--backup`, `--tests`, `--diagnose`; обёртка над `start.sh`, systemd, `site-diagnostics.sh`.
- **`scripts/backup-cli.py`** — CLI создания/восстановления бэкапа через `BackupManager` (без веб-панели).

### 🔄 Changed

- **`MIGRATION.md`**, **`README.md`** — консольное меню `adminpanel.sh` → ✅.

---

## [1.3.0] - 2026-06-08

### ✨ Added

- **VPN network guided wizard (фаза 28)** — `POST /api/settings/vpn-network/publish` запускает `scripts/nginx-setup.sh` через `BackgroundTaskService`; мастер в `VpnNetworkTab.tsx` (Nginx+LE, self-signed, direct HTTP).
- **Runtime panel port firewall** — `panel_port_firewall.py`; toggle «Блок на порту панели (iptables)» в Security tab; sync при сохранении whitelist и на startup.
- **`scripts/nginx-setup.sh`** — неинтерактивный режим (`--non-interactive`, env vars) для вызова из панели.
- **Tests** — `test_panel_port_firewall.py`, `test_ip_restriction_whitelist_firewall_gating.py`; расширен `test_vpn_network_settings.py`.

### 🔄 Changed

- **`MIGRATION.md`**, **`README.md`** — VPN-сеть и firewall panel port → ✅; install `firewall-setup.sh` ≠ runtime whitelist (документировано).

---

## [1.2.2] - 2026-06-08

### ✨ Added

- **CI / pre-commit parity (фаза 27)** — ESLint (`npm run lint`) во `frontend/`; `pip-audit` и `bandit` в CI с `continue-on-error` (advisory, как в AA); pre-commit hooks eslint + bandit (non-blocking).
- **`frontend/eslint.config.js`** — flat config (typescript-eslint, react-hooks, react-refresh).

### 🔄 Changed

- **`backend/requirements-dev.txt`** — `bandit`, `pip-audit`.
- **`MIGRATION.md`**, **`README.md`** — CI/CD, pre-commit → ✅.

---

## [1.2.1] - 2026-06-08

### ✨ Added

- **Test suite wave 2 (фаза 26)** — порт критичных AA-модулей: `test_cidr_db_updater_service`, `test_cidr_list_updater`, `test_access_remaining`, `test_db_migration_service`, `test_backup_scheduler`, `test_client_access_openvpn_block`, `test_settings_post_handlers`; сервис `access_remaining.py`, shim `cidr_list_updater.py`.
- **385 pytest** в 48 модулях (AA: 53; Jinja/Flask-only и phase-28 тесты не портируются).

### 🔄 Changed

- **`pipeline_facade` / `facade_compat`** — `PROVIDER_SOURCES` и fallback на `cidr_list_updater` для file pipeline и тестов.
- **`games.py`** — regex чтения saved game keys поддерживает маркеры AdminPanelAZ.
- **`MIGRATION.md`**, **`README.md`** — In-panel pytest → ✅.

---

## [1.2.0] - 2026-06-08

### ✨ Added

- **Diff-подсветка в редакторе файлов (фаза 25)** — порт AA `buildLightDiff` (Myers + indexed fallback); live diff относительно сохранённой версии; кнопка «Сравнить с диском» (re-fetch с узла); preview diff в диалоге «Сохранить и применить».

### 🔄 Changed

- **`MIGRATION.md`** — Diff-подсветка → ✅.

---

## [1.1.2] - 2026-06-08

### ✨ Added

- **QR max downloads (фаза 24a)** — поле «Макс. скачиваний» (1 / 3 / 5) в `SecurityTab` для `qr_download_max_downloads`.
- **`FEATURE_MAINTENANCE_ENABLED` (фаза 24b)** — toggle `maintenance` в `feature_toggles.py` и `env_defaults.sh`; guard `/api/maintenance/*` и maintenance API под `/api/settings/*`; скрытие вкладки «Обслуживание» в `SettingsNav`.
- **Тесты** — `test_feature_guards.py`: run-doall, restart-service, recreate-profiles, session-stats при отключённом maintenance.

### 🔄 Changed

- **`MIGRATION.md`** — QR-настройки → ✅, `FEATURE_MAINTENANCE` → ✅, Feature toggles → ✅.

---

## [1.1.1] - 2026-06-08

### ✨ Added

- **CIDR presets CRUD (фаза 23)** — REST API `GET/POST /api/routing/cidr-db/presets`, `PUT/DELETE /presets/{id}`, `POST /presets/{id}/reset`; Pydantic-схемы; audit `log_action`.
- **`PresetsTab`** — создание/редактирование/удаление пользовательских пресетов, сброс встроенных, multi-select провайдеров, применение из БД.
- **Тесты** — `test_cidr_db_presets.py` (12 cases), feature guard для `/presets`.

### 🔄 Changed

- **`MIGRATION.md`** — «Пресеты CIDR», «Маршрутизация / CIDR» → ✅.

---

## [1.1.0] - 2026-06-08

### ✨ Added

- **AdminNotify hooks (фаза 21)** — Telegram-уведомления при создании/удалении пользователя, блокировке/разблокировке OVPN/WG-клиента (с `node_id`/`node_name`) и входе с непривязанным TG ID (web + mini app).
- **Интеграционные тесты** — `test_admin_notify_integration.py`: user create/delete, client ban/unban, TG mini unlink, проверка toggles событий.

### 🔄 Changed

- **Telegram Login / Mini App** — вход только для пользователей с привязанным `telegram_id` (без автосоздания `tg_*` аккаунта); при непривязанном ID — `send_tg_login_unlinked`.
- **`MIGRATION.md`** — Telegram admin-уведомления → ✅.

---

## [1.0.0] - 2026-06-08

Релиз после **фазы 20** (final parity audit). Baseline переноса: AdminAntizapret **1.9.0** → AdminPanelAZ **1.0.0**.

### ✨ Added

- **Test suite wave 2** — 5 модулей из AA: `test_antizapret_backup.py`, `test_backup_manager.py`, `test_firewall_tools_check.py`, `test_site_diagnostics.py`, `test_tg_mini_init_data.py` (итого **40 modules / 240 tests**).
- **README** — секция «Production readiness»: чеклист готовности, известные пробелы, таблица 🆕 возможностей сверх AA.

### 🔄 Changed

- **`MIGRATION.md`** — parity audit: исправлены завышенные/заниженные статусы (presets CRUD 🟡, diff 🟡, temp whitelist 🟡, AdminNotify 🟡); baseline **1.0.0**; backlog актуализирован; test count 40/240.
- **Оценка готовности** в README: ~85–90% функциональности AA 1.9.0.

### 📝 Documented gaps

- AdminNotify TG-хуки: client ban/unban, user create/delete
- Временный IP whitelist UI; CIDR presets CRUD; diff в редакторе файлов
- `FEATURE_MAINTENANCE_ENABLED`; CI eslint/pip-audit advisory

---

## [0.7.3] - 2026-06-08

### ✨ Added

- **Ops CLI** — `scripts/site-diagnostics.sh` + `site-diagnostics-cli.py` (systemd, uvicorn, nginx; пути AdminPanelAZ).
- **Safe Browsing CLI** — `scripts/safe-browsing-status.py`; тест `test_safe_browsing_status_cli.py`.
- **AntiZapret backup (client.sh 8)** — `antizapret_backup.py`, `node_adapter.create_antizapret_backup`, node agent `POST /backups/antizapret`, опции в `BackupTab`.
- **Runtime backup cleanup worker** — почасовая очистка `data/cidr/runtime_backups`; toggle `RUNTIME_BACKUP_CLEANUP_ENABLED`.
- **Документация** — `docs/Telegram.md` (Login, Mini App, AdminNotify, backups).

### 🔄 Changed

- **`backup_scheduler.py`** — авто-бэкап AntiZapret + TG-доставка второго архива; worker runtime cleanup.
- **`MIGRATION.md`** — ops CLI ✅, backup client.sh 8 ✅, Telegram.md ✅, RUNTIME_BACKUP_CLEANUP ✅.

---

## [0.7.2] - 2026-06-08

### ✨ Added

- **Global API rate limiting** — `ApiRateLimitMiddleware` для `/api/*` (per-IP sliding window, memory/Redis); исключения `/api/health`, `/api/ip-blocked*`.
- **Public download rate limit** — 30 req/min per IP на `/api/public/route-download/*` (паритет AA).
- **HTTP security parity** — CORP/COOP/X-Permitted-Cross-Domain-Policies, `X-Robots-Tag` noindex, `/robots.txt`, `/.well-known/security.txt`.
- **Shared rate limit module** — `app/services/rate_limit/` (backends + `SlidingWindowLimiter`); auth/API/public-download используют общую инфраструктуру.
- **Тесты** — `test_api_rate_limit.py`; расширен `test_http_security.py` (порт AA cases).

### 🔄 Changed

- **`auth_rate_limit.py`** — рефакторинг на shared sliding-window backends (поведение без изменений).
- **`MIGRATION.md`** — rate limit login ✅, global API rate limit ✅ 🆕.

---

## [0.6.0] - 2026-06-08

### ✨ Added

- **Feature toggles parity (UI)** — шесть недостающих app_module toggles из AdminAntizapret 1.9.0: `amneziawg`, `user_management`, `action_logs`, `system_updates`, `qr_downloads`, `vpn_network` (stub).
- **Guards** — backend middleware и frontend `FeatureGuardRoute` / `SettingsNav` / dashboard для новых модулей; AWG tab отдельно от WireGuard; QR/download/one-time links под `qr_downloads`.
- **Тесты** — расширен `test_feature_guards.py` (users, action logs, updates, QR download, WG/AWG).

### 🔄 Changed

- **Журналы** — `logs_dashboard` и `action_logs` разделены: вкладки и API guards независимы.
- **MIGRATION.md** — секция Feature toggles: app_module ✅/🟡, background workers ❌ (фазы 11/16/19).

---

## [0.5.2] - 2026-06-08

### ✨ Added

- **Game filters** — полный каталог `GAME_FILTER_CATALOG` из AdminAntizapret 1.9.0 (~75 игр) в `backend/app/services/cidr/game_catalog.py`; единый источник для CIDR pipeline и API/UI.
- **UI** — поиск по каталогу на вкладке «Игровые фильтры» (`GameFiltersTab`).
- **Тесты** — `test_game_catalog_coverage.py` (asns/server_ips, LoL Riot Direct, масштаб каталога).

### 🔄 Changed

- **CIDR pipeline** — `provider_sources.py` импортирует каталог из `game_catalog.py` вместо дублирования.

---

## [0.5.1] - 2026-06-08

### ✨ Added

- **Маршрутизация — Конфиг AntiZapret** — вкладка на странице «Маршрутизация» для администраторов: загрузка и редактирование параметров `setup` через `GET/PUT /api/routing/antizapret-settings`, сохранение изменений и применение через doall.sh с подтверждением.

---

## [0.5.0] - 2026-06-08

### ✨ Added

- **AdminNotify** — Telegram-уведомления администратору: вход, операции с конфигами, изменения настроек, бэкапы, лимиты трафика, CPU/RAM; per-user доставка на `User.telegram_id` с подписками по типам событий.
- **API** — `GET/PATCH /api/settings/admin-notify`, `POST /api/settings/admin-notify/test` для управления подписками текущего администратора.
- **UI** — вкладка Telegram в настройках: секция «Уведомления администратору» с toggles по типам событий и тестом на свой Telegram ID.
- **Тесты** — `test_admin_notify.py`, `test_traffic_limit_notify.py`, `test_admin_notify_integration.py` (login → mock Telegram).

---

## [0.3.0] - 2026-06-07

### 🔄 Changed

- **Установка без TTY** — `install.sh` отказывается продолжать при pipe (`wget|curl | bash`) без явных флагов; README и `--help` описывают скачивание в файл и `sudo bash /tmp/install.sh` как рекомендуемый способ.
- **Документация one-liner** — README и `--help` установщика: основной способ `wget|curl | sudo bash` вместо `sudo bash <(wget …)` (process substitution недоступен процессу sudo); для root — `bash <(wget …)`; добавлено пояснение ошибки `/dev/fd/63`.
- **UX/UI установщика** — общий модуль `scripts/install-ui.sh`: баннер с версией, цвета (NO_COLOR/TTY), info/warn/error/success, меню и шаги мастера «Шаг N/M», сводка, прогресс длительных операций, улучшенные `--help` и экран завершения установки.
- **UX/UI установщика** — рамки и иконки переведены на ASCII (`+`, `-`, `|`, `[i]`, `[!]`) вместо Unicode box-drawing; исправлены «ромбики с ?» в PuTTY и Windows SSH при включённых ANSI-цветах.
- **Мастер установки** — убран вариант «Полный стек»; AntiZapret не входит в установку AdminPanelAZ — путь фиксирован `/root/antizapret`, без интерактивного вопроса; при отсутствии каталога — предупреждение или прерывание (для режимов с VPN).
- **Мастер установки** — каталоги состояния controller и node agent больше не спрашиваются; используются значения по умолчанию (`/var/lib/adminpanelaz`, `/var/lib/adminpanelaz-node` при systemd).

### ✨ Added

- **Флаг `--node-only`** — неинтерактивная установка только node agent на VPN-сервере (`--node-only --with-systemd`); без TTY pipe-установка требует явных флагов.
- **One-liner установка** — `install.sh` при запуске через `wget`/`curl` и pipe (`wget | sudo bash`, `curl | sudo bash`, от root — `bash <(wget …)`) автоматически клонирует репозиторий в `/opt/AdminPanelAZ` и перезапускает мастер; команды и `INSTALL_FROM_GIT` / `INSTALL_TARGET` описаны в README.
- **Удаление и переустановка в `install.sh`** — меню при запуске без аргументов (новая установка / переустановка / полное удаление / справка); флаги `--uninstall`, `--purge`, `--reinstall`; переустановка с резервной копией `.env` в `.reinstall-backup/`; делегирование в `scripts/uninstall.sh`.
- **Расширенный `scripts/uninstall.sh`** — опции `--purge`, `--remove-nginx`, `--remove-firewall`, `--remove-env`, `--remove-system-config`, подтверждение `yes`/`AdminPanelAZ`; удаление DDNS timer, nginx, ufw-правил AdminPanelAZ; данные AntiZapret не затрагиваются.

### 🐛 Fixed

- **Модальные формы и диалоги** — нативная HTML5-валидация (`required`, `type="email"` и т.д.) больше не блокирует отправку форм в модальных окнах без видимой обратной связи: `noValidate`, JS-валидация с toast-уведомлениями, единые паттерны submit в `ConfirmDialog` и `ConfirmActionDialog`, защита от закрытия диалога во время загрузки (`onOpenChange`), закрытие диалогов перед перезагрузкой данных при успехе. Затронуты NodesPage (добавление/редактирование/удаление/ротация ключей), DashboardPage, ClientActionsDialog, ConfigCardsSection, NodeUpdateDialog, EditFilesPage, ForcePasswordChange, SettingsPage, UsersTab, PersonalTab, TwoFactorTab.

---

## [0.2.0] - 2026-06-07

### ✨ Added

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

### 🔄 Changed

- **Полный UX/UI редизайн** — единый визуальный язык (карточки, заголовки, бейджи узла, состояния offline/unknown) на страницах Конфигурации, Узлы, Трафик, Журналы, Редактор файлов, NOC Мониторинг, Мониторинг сервера, Маршрутизация и Настройки.
- **ClientActionsDialog** — переработанный диалог действий с клиентом: группировка операций, иконки, подтверждения через `ConfirmDialog`, индикация прогресса.
- **Установка и документация** — README описывает единый `install.sh`, Nginx/HTTPS, DDNS, firewall, `SECURITY.md` и минимальный production `.env`; `uninstall.sh` расширен.
- Node agent version bumped to **1.1.0** (endpoint обновления).
- Срок жизни access JWT по умолчанию **30 минут** (refresh для длительной сессии).
- Расширены политики доступа, client access, tg mini и dashboard под мульти-узловую модель.
- NOC Мониторинг: вкладки «VPN-узел» и «Панель», явная привязка данных к активному узлу, предупреждения при offline/unknown.

### 🐛 Fixed

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

### 🔒 Security

- **Усиление безопасности для сетевого развёртывания** — проверка секретов в `APP_ENV=production`, rate limit на auth, HTTP security headers (middleware, CSP, HSTS, X-Frame-Options), политика паролей, аудит чувствительных действий, constant-time проверка `X-Node-Key` на node agent, опциональный IP allowlist агента; документация в `SECURITY.md`.

---

## [0.1.0] - 2025-06-07

### ✨ Added

- Экспериментальный порт AdminAntizapret на FastAPI + React (TypeScript, Vite, Tailwind, shadcn/ui).
- Controller + Nodes с node agent, CIDR/routing pipeline, бэкапы, журналы, безопасность, мониторинг.
- Production-развёртывание: `install.sh`, daemon/watchdog, systemd, раздача UI из backend в prod-режиме.
- OpenVPN management sockets, vnStat, WebSocket-мониторинг, Telegram Mini App, in-panel pytest.

</details>

[Unreleased]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.17.0...HEAD
[2.17.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.16.0...v2.17.0
[2.16.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.15.0...v2.16.0
[2.15.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.14.0...v2.15.0
[2.14.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.13.0...v2.14.0
[2.13.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.12.0...v2.13.0
[2.12.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.1.0...v2.2.0
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
