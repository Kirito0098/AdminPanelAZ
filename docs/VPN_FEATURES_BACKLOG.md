# Backlog: OpenVPN, WireGuard, AmneziaWG

> Черновик идей для развития VPN-модулей AdminPanelAZ.  
> Статус проекта на момент составления: **1.7.0**, parity с AdminAntizapret 1.9.0 ~**92–95%**.  
> Отметьте нужное (`[ ]` → `[x]`) и перенесите в задачи / CHANGELOG по мере реализации.

---

## Уже реализовано (не дублировать)

| Область | OpenVPN | WireGuard / AWG |
|---------|---------|-----------------|
| CRUD клиентов | ✅ `antizapret.py`, `node_adapter.py`, `client.sh` | ✅ |
| Профили AZ / VPN, скачивание, QR | ✅ `configs.py`, `profile_download_name.py` | ✅ отдельные вкладки WG и AWG |
| Одноразовые ссылки | ✅ `qr_download.py`, SecurityTab | ✅ |
| Временная / постоянная блокировка | ✅ `access_policy.py`, `openvpn_management.py` | ✅ + runtime `wg_runtime.py` |
| Лимиты трафика (1 / 7 / 30 дн.) | ✅ | ✅ |
| Reconcile + TG при превышении лимита | ✅ `traffic_limit_reconcile.py`, `traffic_limit_notify.py` | ✅ |
| Срок доступа | ✅ `cert_expire_days`, продление в UI | ✅ `expires_at`, `wgSetExpiry` |
| Отключение активной сессии | ✅ `openvpnDisconnect` (management socket) | — нет аналога в WG |
| Переключение UDP/TCP группы | ✅ `PUT /api/configs/openvpn-group` | — |
| Синхронизация списка с диском | ✅ `POST /api/configs/sync` | ✅ |
| Сбор трафика, графики, live-подключения | ✅ `traffic/collector.py`, `/traffic`, `/monitoring` | ✅ handshake в мониторинге |
| Публичные route-файлы (роутеры) | ✅ `GET /api/public/route-download/{router}` | — |
| Feature toggles | ✅ `openvpn`, `wireguard`, `amneziawg` | ✅ AWG использует API wireguard |
| Telegram Mini App, AdminNotify | ✅ `tg_mini.py`, `admin_notify.py` | ✅ |
| Multi-node (базово) | ✅ клиенты на **активном** узле | ✅ |

**Ключевые файлы:** `backend/app/services/access_policy.py`, `backend/app/routers/client_access.py`, `backend/app/routers/configs.py`, `frontend/src/components/dashboard/ClientActionsDialog.tsx`, `frontend/src/components/dashboard/ConfigCardsSection.tsx`, `backend/node_agent/main.py`.

---

## Идеи для добавления

### Приоритет: высокий

- [ ] **Сообщение клиенту OpenVPN: почему не подключается**  
  Сейчас при блокировке клиент видит только общий `AUTH_FAILED` в приложении OpenVPN; причина видна **только админу** в панели (`buildAccessMeta` / `block_mode`).  
  *Варианты реализации (можно комбинировать):*  
  1. **Расширить ban-hook** (`openvpn_ban_hook.py`) — файл `config/banned_clients_reasons.json` с текстом по `block_mode` (временная блокировка до даты, лимит трафика, навсегда); в `client-connect.sh` писать текст в `$auth_failed_reason_file` (OpenVPN 2.6+, если переменная доступна в hook).  
  2. **Статус-страница / API для владельца** — `GET /api/public/client-status?token=...` или в Telegram Mini App: «Доступ заблокирован: превышен лимит 10 ГБ за 7 дней». Надёжно, не зависит от клиента OpenVPN.  
  3. **TG-уведомление владельцу** при block/limit — дополнение к AdminNotify, но для `user`, не только admin.  
  *Ограничения:* многие клиенты (OpenVPN Connect, мобильные) **не показывают** кастомный текст из `client-connect`, только «Authentication failed»; истёкший сертификат — отдельная ошибка на этапе TLS, до ban-hook.  
  *Где:* `access_policy.py` (`write_banned_clients`), `openvpn_ban_hook.py`, опционально `tg_mini.py`, `public_download.py`.

- [ ] **Массовые операции на дашборде**  
  Блокировка, разблокировка, лимит трафика, удаление, продление — для выбранных клиентов.  
  *Зачем:* экономия времени при десятках/сотнях клиентов.  
  *Где:* `DashboardPage.tsx`, новый API `POST /api/client-access/bulk/...`.

- [ ] **Уведомления о скором истечении срока**  
  TG/email за N дней до expiry: сертификат OpenVPN, `expires_at` WG/AWG; алерт если клиент уже `expired`.  
  *Зачем:* меньше «случайно отключённых» клиентов.  
  *Где:* worker по аналогии с `traffic_limit_notify.py`, настройки в Settings.

- [ ] **Online / last handshake на карточке клиента**  
  Показывать статус подключения и время последнего handshake прямо в `ConfigCard`.  
  *Зачем:* не заходить на `/monitoring` для каждого клиента.  
  *Где:* данные уже частично в `/api/monitoring/overview`; расширить `VpnConfig` / policy response.

- [ ] **Self-service для роли `user` в Mini App / панели**  
  Владелец конфига: скачать свой профиль, продлить WG-срок (с лимитами), запросить новый конфиг.  
  *Зачем:* разгрузка админа.  
  *Где:* `tg_mini.py`, guards по `owner_id`, `ClientActionsDialog` (ограничить действия).

- [ ] **Выбор узла при создании клиента**  
  Не только active node — явный `node_id` при create/sync.  
  *Зачем:* полноценный multi-node без переключения активного узла.  
  *Где:* `configs.py`, `DashboardPage.tsx`, `node_manager.py`.

---

### Приоритет: средний

#### OpenVPN

- [ ] **История подключений per-client**  
  Не только live-сессии — журнал connect/disconnect за период.  
  *Где:* парсинг OpenVPN events / status log, таблица в БД, UI на карточке или `/logs`.

- [ ] **Автопродление сертификата по расписанию**  
  Worker: если до expiry ≤ N дней — вызвать renew (как в `ClientActionsDialog`).  
  *Где:* новый worker, настройки в MaintenanceTab.

- [ ] **Шаблоны при создании клиента**  
  Пресеты: срок сертификата, UDP/TCP группа, владелец, лимит трафика по умолчанию.  
  *Где:* `AppSetting` или таблица `client_templates`, форма создания в `DashboardPage`.

- [ ] **Revoke / CRL**  
  Явный отзыв сертификата с обновлением CRL (если AntiZapret / Easy-RSA это поддерживает на узле).  
  *Где:* node agent + `antizapret.py`.

- [ ] **Принудительный reconnect**  
  Kill session + опциональное ожидание переподключения (расширение `disconnect`).

#### WireGuard / AmneziaWG

- [ ] **Ротация ключей peer**  
  Regenerate keys + перевыпуск профиля без смены имени клиента.  
  *Где:* node agent `POST /clients/wireguard/{name}/rotate`, `client.sh` или wg CLI.

- [ ] **Отдельные политики для AWG**  
  Сейчас AWG = WG с другим путём профиля (`-am.conf`); при необходимости — отдельная таблица или `vpn_subtype`.  
  *Где:* `WgAccessPolicy`, `access_policy.py`, guards.

- [ ] **Настройки obfuscation AWG в UI**  
  Jc, Jmin, Jmax, S1, S2 и т.д. — если node agent может менять через AntiZapret config.  
  *Где:* `AntizapretConfigTab` или отдельная секция AWG.

- [ ] **«Мягкое» отключение WG**  
  Block runtime без удаления peer (block/unblock на node agent уже есть — улучшить UX и статусы в UI).

#### Общее

- [ ] **График трафика на карточке клиента**  
  Мини-спарклайн или модалка без перехода на `/traffic`.  
  *Где:* `traffic/chart.py`, `ConfigCard.tsx`.

- [ ] **Топ-N клиентов по трафику на дашборде**  
  Фильтр по протоколу (OVPN / WG / AWG).  
  *Где:* `DashboardPage.tsx`, агрегация из `user_traffic_stat`.

- [ ] **Экспорт CSV**  
  Список клиентов: имя, протокол, владелец, блокировка, лимит, трафик, expiry.  
  *Где:* `GET /api/configs/export`, кнопка на дашборде.

- [ ] **Миграция клиента между узлами**  
  Export policy + recreate на другой node + удаление на старом.  
  *Где:* orchestrator в `node_adapter.py`, UI wizard.

---

### Приоритет: низкий / по запросу

- [ ] **Webhook при block / unblock / limit exceeded** — интеграция с биллингом.
- [ ] **Лимит «N конфигов на пользователя»** — квота для роли `user`.
- [ ] **PIN / 2FA на скачивание per-client** — поверх глобальных QR-настроек.
- [ ] **Аудит скачиваний профилей** — кто, когда, IP (расширить action logs).
- [ ] **Расписание recreate profiles** — автоматический `client.sh 7` / MaintenanceTab.
- [ ] **Сравнение AZ vs VPN профилей** — статистика «кто на antizapret-маршрутах».
- [ ] **vnStat по VPN-интерфейсам на карточке узла** — углубление мониторинга (частично в 1.6.0).
- [ ] **Per-node feature toggles** — OpenVPN только на выбранных узлах.
- [ ] **API «создать клиента + one-time link» одним вызовом** — для внешних систем.

---

## Известные отличия от AA (не обязательно чинить)

| Область | AA | AZ | Комментарий |
|---------|----|----|-------------|
| Cleanup OpenVPN `*.log` | crontab | AppSetting + ручной POST | Нет встроенного cron-writer; период сохраняется |
| Feature-disabled page | HTML | JSON 403 | SPA — отдельная страница не нужна |
| AWG API | общий с WG | общий с WG | Отдельный toggle `amneziawg`, тот же `/client-access/wireguard` |

Источник: [`MIGRATION.md`](../MIGRATION.md) § «Оставшиеся отличия».

---

## Рекомендуемый порядок (если выбирать 3–5 пунктов)

1. Массовые операции на дашборде  
2. Уведомления о скором expiry (OVPN + WG/AWG)  
3. Online / handshake на ConfigCard  
4. Self-service в Mini App для `user`  
5. Выбор узла при создании клиента  

---

## Чеклист перед реализацией пункта

- [ ] Нужен только UI, только backend, или node agent?
- [ ] Затрагивает ли multi-node / active node?
- [ ] Нужен feature toggle?
- [ ] Нужны тесты в `backend/tests/` (паттерн: `test_wg_access_policy_service.py`, `test_feature_guards.py`)?
- [ ] Обновить [`MIGRATION.md`](../MIGRATION.md) / [`CHANGELOG.md`](../CHANGELOG.md)?

---

## Связанные документы

- [`MIGRATION.md`](../MIGRATION.md) — parity с AdminAntizapret, что уже перенесено  
- [`docs/Telegram.md`](Telegram.md) — Mini App, AdminNotify  
- [`README.md`](../README.md) — обзор модулей и feature toggles  
