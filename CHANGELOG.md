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

> **Кратко:** NOC в Telegram — расширенные сводки, еженедельный PNG-дашборд вместо PDF, предпросмотр и тест каждого типа уведомления; вход в панель — IP и устройство в TG; мониторинг трафика/сервера — TB, доля, live CPU, графики ресурсов.

### ✨ Added

#### NOC — Telegram-сводки и PNG-дашборд

- **Ежедневная/еженедельная текстовая сводка** — трафик за период с Δ; CPU/RAM/Диск (среднее и пик); lag сбора; блокировки по лимиту; сессии OVPN/WG (среднее и пик); топ клиентов; алерты; CIDR; офлайн-узлы (`noc_report.py`, `resource_metrics.py`).
- **Еженедельный PNG-дашборд** — одна картинка в TG вместо PDF: KPI-карточки, таблица узлов, bar chart топ клиентов, инциденты и CIDR (`noc_report_image.py`, `sendPhoto` в `telegram.py`).
- **Bundled-шрифты** — Liberation Sans/Mono и DejaVu в `backend/static/fonts/`; резолвер `image_fonts.py` (кириллица без «квадратиков»).
- **Предпросмотр NOC** — кнопки «Ежедневная сводка» / «Еженедельная сводка» / «Еженедельная картинка»; `POST /settings/admin-notify/test-noc-report`, `test-noc-image` (алиас `test-noc-pdf`).
- **Тест каждого TG-уведомления** — кнопка Send у каждого переключателя «О чём сообщать»; `POST /settings/admin-notify/test-event`.

#### TG — уведомление о входе

- **Устройство и IP входа** — парсинг User-Agent (`user_agent_format.py`); строки «IP входа» и «Устройство» в `login_success` / `login_failed`; для Telegram Login — `Telegram`.

#### Мониторинг сервера — история ресурсов

- **Графики CPU / RAM / Диск** — на странице «Сервер» под live-карточками: история за 1 / 7 / 30 дней (`ResourceHistoryCharts`, `GET /api/monitoring/resource-history`); снимки ~раз в минуту фоновым worker.
- **Load average** — второй график в том же блоке, если в истории есть `load_1`.

#### Мониторинг трафика — производительность БД

- **Составной индекс** `(node_id, created_at)` на `user_traffic_sample` — ускоряет агрегацию окон 1д / 7д / 30д; миграция при старте панели (`models.py`, `database.py`).

### 🔄 Changed

#### NOC — Telegram

- **Env weekly image** — `NOC_REPORT_WEEKLY_IMAGE_*` (алиасы `NOC_REPORT_WEEKLY_PDF_*`); scheduler отдаёт PNG, не PDF.
- **UI настроек Telegram** — блок предпросмотра NOC и подписи под «картинку» вместо PDF.

#### TG — формат входа

- **Сообщение «Успешный вход»** — отдельные строки: пользователь → IP входа → устройство → время (без «Вошёл в панель ·»).

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

[Unreleased]: https://github.com/Kirito0098/AdminPanelAZ/compare/v2.8.0...HEAD
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
