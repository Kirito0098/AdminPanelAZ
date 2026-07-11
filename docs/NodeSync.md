# Node Sync / HA (AntiZapret failover)

## Сценарий

Один домен (`vpn.example.com`), два A-записи (primary IP + replica IP). Клиент переключается между IP только если PKI (`/etc/openvpn/easyrsa3`), WireGuard peers и клиенты совпадают на обоих серверах.

## MVP (этап 5.1–5.3)

- **Sync Group** — primary + 1+ replica, shared domain
- **Push full** — `client.sh 8` на primary → transfer → restore на replica (как `setup.sh`). Дополнительно копирует непустые `OPENVPN_HOST` / `WIREGUARD_HOST` из `setup` primary на каждую replica **перед** restore, чтобы перегенерированные профили (`client.sh 7`) получили правильный хост.
- **Verify** — списки OVPN/WG клиентов + checksums PKI/WG/config

## API

| Method | Route |
|--------|-------|
| GET/POST | `/api/nodes/sync-groups` |
| GET/PUT/DELETE | `/api/nodes/sync-groups/{id}` |
| POST | `/api/nodes/sync-groups/{id}/setup` |
| POST | `/api/nodes/sync-groups/{id}/push-full` |
| POST | `/api/nodes/sync-groups/{id}/apply-shared-domain` |
| POST | `/api/nodes/sync-groups/{id}/verify` |
| GET | `/api/nodes/sync-groups/{id}/status` |

Node agent: `POST /backups/antizapret/restore`, `GET /backups/antizapret/download`, `GET /backups/antizapret/fingerprints`.

## Ограничения

- DNS панель не настраивает — второй IP добавляется у регистратора вручную **после Verify ready=true**
- Оба сервера должны быть установлены одинаковым `setup.sh`
- Push full **destructive** на replica
- Split-brain: изменения только на primary; при failed sync — `sync_status=failed`, Push full или (в `auto`, opt-in) incremental auto-heal
- **`manual_full`** (по умолчанию) — полное выравнивание через **Push full**; клиенты на replica попадают в панель после Push full (импорт в БД + политики + снимок трафика). HA-бейдж на primary — **да** (`sync_group_id`, без теней на replica). **Create / delete / renew OVPN на primary** дополнительно копируют **crypto-состояние** (WG conf + профили, easyrsa3) на replica — один профиль работает на обоих IP; shadow `VpnConfig` и прочая auto-репликация политик/файлов — **нет**. После расформирования группы на replica: **Конфигурации → Синхронизировать**
- **`auto`** — см. раздел [v2 — HA auto-sync](#v2--ha-auto-sync-этапы-ac) ниже

## v2 — HA auto-sync (этапы A–C)

### Режимы `sync_mode`

| Режим | Поведение | Когда использовать |
|-------|-----------|-------------------|
| **`manual_full`** (по умолчанию) | Авто-репликация политик/файлов **отключена**. Выравнивание — **Push full**. Create/delete/renew клиента на primary **копирует crypto** (WG + OVPN PKI) на replica без shadow `VpnConfig`. | Первая настройка HA, редкие правки, split-brain recovery |
| **`auto`** | Изменения на **primary** автоматически реплицируются на все **online** replica группы. Primary — источник истины; на replica — теневые `VpnConfig` (`ha_primary_config_id`) с тем же `client_name`. | Повседневная работа: админ правит только primary |

**Shadow-связи (`ha_primary_config_id`):**

- **Push full** выравнивает ключи и файлы на диске replica; shadow-связи в БД нужны панели для event-driven операций (delete, block, metadata, renew).
- После **Push full**, **HA Setup** или переключения группы на **`auto`** выполняется автоматическое связывание существующих клиентов primary ↔ replica по `(client_name, vpn_type)`.
- Клиенты, созданные через панель уже в режиме `auto`, получают shadow при create.
- Если shadow ещё нет (редкий edge case), **delete** на primary дополнительно копирует crypto-состояние на все replica (fallback, как в `manual_full`).
- Клиенты только на replica без пары на primary не удаляются автоматически — Verify покажет drift; устранение: Push full с primary.

**Операционные правила (оба режима):**

- Работайте с HA **только на primary** (на replica create/delete/renew/block, правки defaults, **редактор файлов**, **маршрутизация**, **списки доменов/IP в настройках** — **403**).
- Правки по SSH вне панели → drift; устранение: Push full или (в `auto`, opt-in) incremental auto-heal.
- После split-brain, смены primary или состава группы — **Push full**.
- DNS панель не настраивает — второй A-record добавляется у регистратора **после Verify ready=true**.

### Что реплицируется в `sync_mode=auto`

#### VPN-клиенты и политики доступа

| Операция | Replica |
|----------|---------|
| Create / delete client | Копия crypto-состояния primary: `/etc/wireguard/*.conf` + **те же файлы профилей** WG/AWG (PrivateKey/PSK) или `/etc/openvpn/easyrsa3/` + `client.sh 7` + restart OpenVPN (OVPN); shadow `VpnConfig` |
| Renew OpenVPN cert | Копия easyrsa3 с primary + перегенерация профилей; тот же `client_name`, новый срок |
| Temp / permanent block, unblock | Та же политика в БД + runtime (iptables/WG) |
| Set / clear traffic limit | Те же `traffic_limit_*` + reconcile runtime |
| WG set-expiry | Тот же `expires_at` + runtime |
| OpenVPN disconnect | Разрыв сессии на primary и replica (если клиент онлайн) |
| PATCH: description, owner | Обновление shadow `VpnConfig` (метаданные панели) |
| Bulk: block, renew, unblock | Как одиночные операции |
| CSV import / template apply | Create + политики (лимит, block) из CSV или шаблона |
| Node default policy | `PUT …/node-defaults/{primary_id}` → копия на replica (**только primary**, на replica node_id — 403) |

**Consumed traffic (байты)** — **не** синхронизируются; считаются per node. Паритет — лимит, блок и policy row.

> **Мониторинг трафика** при этом умеет показывать **суммарный** объём логического клиента по всем узлам группы (UI-агрегация, хранение остаётся per node). Лимит трафика по-прежнему проверяется по каждому узлу отдельно. См. [traffic-monitoring.md](traffic-monitoring.md).

#### Файлы AntiZapret (`/root/antizapret/config/`)

| Операция | Replica |
|----------|---------|
| Списки в «Настройках» (домены/IP) | Те же файлы + опционально `doall.sh` |
| Редактор файлов (один / batch) | Изменённые файлы + опционально `doall.sh` |
| Routing UI (route files: include/exclude/forward/drop IPs) | Те же файлы на replica без `doall.sh` по умолчанию |
| Routing UI (provider files) | Аналогично, если файл в scope HA |

См. [edit-files.md](edit-files.md) — auto vs ручной перенос.

#### Конфигурация AntiZapret (`setup`)

| Операция | Replica |
|----------|---------|
| `PUT /routing/antizapret-settings` | Те же ключи `setup` (см. исключения ниже) |
| `POST /routing/apply` | Фоновый apply (`doall.sh`) на каждой replica |

См. [antizapret-config.md](antizapret-config.md).

#### CIDR / providers

| Операция | Replica |
|----------|---------|
| Ручное редактирование provider file | Файл `AP-*-include-ips.txt` |
| `POST /routing/sync` (compile) | Deploy скомпилированных файлов на replica группы |

### Исключения (не копировать / не перезаписывать)

| Область | Исключение | Где задано |
|---------|------------|------------|
| Config files | `warper-include-ips.txt` и др. node-local файлы | `CONFIG_FINGERPRINT_EXCLUDE` в `fingerprints.py` |
| Setup (`/root/antizapret/setup`) | `ANTIZAPRET_WARP`, `VPN_WARP` | `ANTIZAPRET_HA_SETTING_EXCLUDE` |
| Setup | **`OPENVPN_HOST` / `WIREGUARD_HOST` реплицируются** (общий `shared_domain`) | — |

### Apply shared domain (`POST …/apply-shared-domain`)

Записывает `shared_domain` группы в `OPENVPN_HOST` и `WIREGUARD_HOST` в `/root/antizapret/setup` на **primary и всех replica**, затем на каждом узле выполняет `doall.sh` (apply_config_changes) + `client.sh 7` (recreate_profiles), чтобы новый хост попал в перегенерированные профили клиентов. Фоновая задача `node_sync_shared_domain`; ошибка на одном узле не прерывает остальные (partial failure → `sync_status=failed`, детали в `last_sync_error`). Вызывается при **HA Setup** (если включён toggle «Сразу настроить» при создании), при изменении `shared_domain` в группе, а также вручную кнопкой «Домен → узлы». Создание группы **без** Setup **не** применяет домен автоматически.
| Verify / Push full | Excluded config не ломают паритет fingerprint `antizapret/config` | `fingerprints.py` |

### Partial failure

- Primary **не откатывается** при ошибке на одной replica.
- `sync_status=failed`, `last_sync_error` — детали; audit `ha_replicate_partial_failure`.
- UI: warning-toast при `sync_status=failed` (polling auto-групп) или при `warnings` в API.
- **Auto-heal** (opt-in, `NODE_SYNC_AUTO_HEAL=true`): reconcile worker пытается incremental heal (`crypto_sync` / `policy_sync` / `config_sync` / `antizapret_sync`); **никогда** auto Push full. После N неудач — notify + `failed`.

### Reconcile worker

- Периодический Verify всех групп (`NODE_SYNC_RECONCILE_*`, default каждые 600 с).
- Drift → `sync_status=failed` + admin notify (в `auto` + auto-heal — notify после N неудачных heal).
- Push full остаётся для bootstrap и disaster recovery.

### Dashboard HA badge

- Одна карточка клиента (logical primary), badge «HA: domain (N узл.)».
- Список configs при активном узле в группе — primary.
- В `auto` — теневые `VpnConfig` на replica; в `manual_full` — только `sync_group_id` на primary.

### Настройки `NODE_SYNC_*` (`.env`)

| Переменная | Default | Назначение |
|------------|---------|------------|
| `NODE_SYNC_RECONCILE_ENABLED` | `true` | Периодический reconcile worker |
| `NODE_SYNC_RECONCILE_INTERVAL_SECONDS` | `600` | Интервал reconcile |
| `NODE_SYNC_AUTO_REPLICATE_CONFIG_FILES` | `true` | Auto: репликация config files с primary |
| `NODE_SYNC_AUTO_REPLICATE_POLICIES` | `true` | Auto: репликация политик доступа |
| `NODE_SYNC_REPLICATE_DOALL` | `true` | Запускать `doall.sh` на replica после file sync |
| `NODE_SYNC_AUTO_HEAL` | `false` | Opt-in incremental heal после drift |
| `NODE_SYNC_AUTO_HEAL_MAX_FAILURES` | `3` | Notify после N неудачных heal |

### Связанные документы

- [edit-files.md](edit-files.md) — редактор файлов, HA auto vs manual transfer
- [antizapret-config.md](antizapret-config.md) — setup, `ANTIZAPRET_HA_SETTING_EXCLUDE`
