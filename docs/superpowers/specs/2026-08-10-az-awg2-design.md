# AZ-AWG2 — волна 1 (сводный спек: срезы 1a–1c)

**Дата:** 2026-08-10  
**Статус:** draft — **выполнять по срезам**, не целиком  
**Эпик:** [`2026-08-10-az-awg2-epic.md`](2026-08-10-az-awg2-epic.md)  
**Upstream:** [blindtechnique/az-awg2](https://github.com/blindtechnique/az-awg2)

| Срез | Спек | План |
|------|------|------|
| **1a** shell | [wave1a](2026-08-10-az-awg2-wave1a-design.md) | [plan](../plans/2026-08-10-az-awg2-wave1a.md) |
| **1b** clients | [wave1b](2026-08-10-az-awg2-wave1b-design.md) | [plan](../plans/2026-08-10-az-awg2-wave1b.md) |
| **1c** Dashboard/docs | [wave1c](2026-08-10-az-awg2-wave1c-design.md) | [plan](../plans/2026-08-10-az-awg2-wave1c.md) |

Детальный монолитный план (справочник сниппетов): [`../plans/2026-08-10-az-awg2.md`](../plans/2026-08-10-az-awg2.md)

Ниже — исходное полное описание волны 1 (для контекста). Реализация только через 1a→1b→1c.

---

# AZ-AWG2 — волна 1 (вкладка + VpnConfig) [архив текста]

**Образец интеграции:** AZ-WARP (`WarperService`, `/warper`, feature toggle)  
**Далее:** срезы [2a](2026-08-10-az-awg2-wave2a-design.md)–[2c](2026-08-10-az-awg2-wave2c-design.md); эпик [wave3](2026-08-10-az-awg2-wave3.md).

## Цель


Дать админу отдельную страницу **AZ-AWG2** для управления параллельным слоем AmneziaWG 2.0 на активном VPN-узле: статус, инструкция установки, создание/удаление клиентов, скачивание `.conf` / QR / `vpn://`. Клиенты хранятся как `VpnConfig` с типом `amneziawg2` и подчиняются квотам / visibility / client-access в **веб-панели**. Роль `user` видит и скачивает свои конфиги на Dashboard.

Панель **не** устанавливает слой сама — только показывает команду (как AZ-WARP).

## Решения владельца (волна 1)

| Тема | Выбор |
|------|--------|
| MVP функций | Статус + install-prompt + CRUD клиентов + download/QR/`vpn://` |
| Навигация | Отдельный пункт меню рядом с AZ-WARP (`/awg2`), Dashboard AmneziaWG (сток) не трогаем |
| Установка | Только команда SSH (`curl … install.sh`); без remote install из UI |
| БД | `VpnType.amneziawg2` + политики/квоты как у стока |
| HA | Не в этой волне; UI-пометка; create не реплицирует |
| Доступ | Admin — страница AZ-AWG2; user — Dashboard download/create по политикам; без Mini App / Telegram |
| Подход | Warper-style модуль (`Awg2Service` + `/api/awg2/*`) + ветка в `/api/configs` |
| Feature toggle | `FEATURE_AWG2_ENABLED`, **default off** (opt-in) |
| Волны | Волна 1 = этот спек; волна 2 = HA (+ прочее) отдельным спеком |

## Не цели (волна 1)

- HA crypto-sync путей `/etc/amnezia/amneziawg` и `/opt/antizapret-awg`
- UI обфускации / `--reconfigure`
- Rich-мониторинг (`awg show`, гео-статы бота)
- TTL-клиенты, бэкап/restore слоя
- Telegram-бот панели / Mini App для AWG2
- Запуск `install.sh` / `--update` из панели (стрим)
- Изменение стоковой вкладки AmneziaWG или AZ-WARP
- Управление стоковыми WG/OpenVPN через CLI az-awg2 (это делает бот upstream; панель уже умеет сток)

## Жёсткие правила продукта

1. Слой az-awg2 ставит только админ по SSH; панель не запускает `install.sh`.  
2. `Awg2Service` не пишет в `/etc/wireguard` и `client/amneziawg` (сток AntiZapret).  
3. Имя UI/меню: **AZ-AWG2** (не «AZ-WARP»).  
4. При выключенном toggle UI/API модуля недоступны (`/api/awg2/*`, пункт меню; create `amneziawg2` — 403).  
5. Один `VpnConfig(amneziawg2)` на `client_name` на узле; create поднимает оба туннеля `antizapret` и `vpn`.  
6. HA replicate для `amneziawg2` в волне 1 **запрещён** (явный no-op / skip в client_sync).

## Контекст upstream

- CLI: `awg-client` → `client-awg.sh`  
  - `add <name> [antizapret|vpn] [--ttl …]`  
  - `del <name> [antizapret|vpn]`  
  - `list [antizapret|vpn]`  
- Клиентские файлы: `/opt/antizapret-awg/clients/{antizapret,vpn}/{svc}-{name}-am.conf` (+ артефакты QR/`vpn://` рядом, через `awg-export.py`)  
- Сервер: `/etc/amnezia/amneziawg/*.conf`, `services.env`, `obfuscation.env`  
- Overlay/код: `/opt/antizapret-awg`  
- Режим: **parallel** — штатный AntiZapret не ломается; AdminPanelAZ уже заявлен совместимым без патчей для стока

## Архитектура

```
UI /awg2 (admin)  +  Dashboard (admin/user)
        │
        ├─ /api/awg2/health|status     → Awg2Service (probe + summary)
        └─ /api/configs (vpn_type=amneziawg2)
                │
                ▼
         Awg2Service
           subprocess + flock → awg-client / client-awg.sh
           profile paths under /opt/antizapret-awg/clients
                │
                ▼
         NodeAdapter (Local | Remote :9100)
```

### Компоненты

| Компонент | Ответственность |
|-----------|-----------------|
| `backend/app/services/awg2.py` | Detect install, status, add/del/list clients, resolve profile files, install_command |
| `backend/app/routers/awg2.py` | Admin health/status endpoints |
| `backend/app/models.py` | `VpnType.amneziawg2` |
| `backend/app/routers/configs.py` | Create/delete/get/download ветка `amneziawg2` |
| `backend/app/services/node_adapter.py` (+ agent) | Parity methods для remote node |
| `backend/app/services/feature_toggles.py` | `awg2` toggle, prefixes `/api/awg2`, path `/awg2` |
| `backend/app/services/vpn_profile_visibility.py` | Protocol key `amneziawg2` |
| `frontend/.../Awg2Page.tsx` + components | Страница модуля |
| `frontend/.../Layout.tsx`, `App.tsx` | Nav + route |
| Dashboard create / cards | Тип AmneziaWG 2.0, профили отдельно от стока |

### Модель данных

- Добавить `VpnType.amneziawg2 = "amneziawg2"` (строка ≤16 символов — совместимо с `VARCHAR(16)` в миграциях).  
- Unique `(node_id, client_name, vpn_type)` позволяет то же имя, что у стокового `wireguard`.  
- Owner, description, tags, quota — как у существующих конфигов.  
- `cert_expire_days` / OpenVPN cert fields для AWG2 не используются (оставить nullable / игнорировать).

### Create / delete

**Create (`POST /api/configs`, `vpn_type=amneziawg2`):**

1. Feature toggle + visibility + quota + `can_create_configs`.  
2. Health: слой установлен, иначе 409 + install hint.  
3. HA: не вызывать `maybe_replicate_create` для этого типа (волна 1).  
4. На узле: `awg-client add <name> antizapret` и `awg-client add <name> vpn` (под flock). Частичный успех → rollback `del` уже созданного туннеля + ошибка.  
5. Insert `VpnConfig`.

**Delete:** `awg-client del` для обоих туннелей (идемпотентно, если файла нет) → delete DB row; без HA replicate.

**Import с диска:** расширить import clients: сканировать `/opt/antizapret-awg/clients/**/**-*-am.conf`, создавать orphan `VpnConfig(amneziawg2)` (owner = admin/system policy как у WG import), чтобы бот az-awg2 и панель не расходились.

### Profile delivery

- `get_profile_files` для `amneziawg2` читает conf (+ sidecar `vpn://` / qr files если есть) из `/opt/antizapret-awg/clients/…`.  
- QR: использовать существующий `prefers_download_link_qr` / pipeline как для AntiZapret WG split: если conf слишком большой для QR — download-link QR и/или `vpn://` QR из артефактов `awg-export`, без отдельной эвристики в волне 1.  
- Visibility filter: protocol key `amneziawg2` (не путать с `amneziawg`).

### Client access / блокировки

- Волна 1: **только** feature toggle, visibility, quota, create/delete/download.  
- Временная/постоянная блокировка peer AWG2 (аналог client-access WireGuard) — **вне scope**; отдельный пункт волны 2.

## API

| Метод | Путь | Роль | Описание |
|-------|------|------|----------|
| GET | `/api/awg2/health` | admin | `installed`, `missing_components`, `install_command`, node meta |
| GET | `/api/awg2/status` | admin | Best-effort: ifaces, ports from `services.env`, client counts |
| POST | `/api/configs` | admin / user* | `vpn_type=amneziawg2` |
| DELETE | `/api/configs/{id}` | … | удаление на узле + DB |
| GET | `/api/configs/{id}` | … | файлы профилей |
| Existing | download / QR endpoints | … | работают для нового типа |

\*user при `can_create_configs` + quota + visibility.

`install_command` (фиксированная строка):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh)
```

Update hint (справка, не API action):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh) --update
```

## UI

### `/awg2` (admin, toggle on)

- Hero: active node, installed badge, refresh  
- Alerts: not installed / HA note («синхронизация AWG2 на replica — волна 2»)  
- Install prompt (если не installed)  
- Tabs when installed:  
  - **Клиенты** — список `VpnConfig` amneziawg2 на узле, create/delete/download  
  - **Справка** — отличие от стокового AmneziaWG, команды install/update, ссылка на upstream README  

### Dashboard

- Create: опция «AmneziaWG 2.0» только если toggle on **и** health.installed на active node  
- Отображение профилей: отдельная маркировка / вкладка не смешивается со стоковым `amneziawg`  
- User: свои конфиги + filter visibility  

### Nav

- `Layout.tsx`: `{ to: '/awg2', label: 'AZ-AWG2', adminOnly: true, featureKey: 'awg2' }`  
- `haNodeScope`: `/awg2` как diagnostic/node-local (не group-scope), аналогично `/warper`

## Feature toggle

```text
key: awg2
env: FEATURE_AWG2_ENABLED
default: false
group: app_module
api_prefixes: /api/awg2
frontend_paths: /awg2
```

Create/delete через `/api/configs` дополнительно проверяет toggle (не только prefix middleware).

## Тесты

- `detect_awg2_installation` / missing components  
- Create/delete service с mock subprocess  
- API health: not installed → install_command  
- Toggle off → `/api/awg2/*` недоступен; create amneziawg2 → 403  
- Visibility protocol `amneziawg2`  
- Quota includes amneziawg2  
- `maybe_replicate_create` **не** вызывается для amneziawg2  
- Adapter parity Local vs Remote  
- Import orphans from client dir  
- Frontend: option hidden when not installed (unit/light)

## Документация

- `docs/awg2.md` — пользовательское руководство (как `docs/warper.md`)  
- `docs/README.md`, `docs/PROJECT_MAP.md`, `docs/konfiguracii.md` — ссылки / отличие от стока  
- `CHANGELOG.md` — Added  

## Риски

| Риск | Митигация |
|------|-----------|
| Гонка с Telegram-ботом az-awg2 | flock на CLI; import с диска |
| Путаница AmneziaWG vs AWG2 | Отдельный тип, меню, copy |
| Частичный create (один туннель) | Rollback del + ошибка |
| Огромный AllowedIPs → QR | Fallback download / vpn:// QR |
| Remote node без слоя | 409 с install_command |
| Enum/SQLite | значение `amneziawg2` в VARCHAR; проверить все `match vpn_type` |

## Волна 2+

См. [`2026-08-10-az-awg2-wave2-design.md`](2026-08-10-az-awg2-wave2-design.md). Критерий «HA skip» ниже действует **только до внедрения волны 2**.

## Критерии готовности волны 1

1. Toggle off → модуля нет в UI/API.  
2. Toggle on, слой не установлен → install-prompt, create недоступен.  
3. Слой установлен → admin создаёт клиента на `/awg2` и Dashboard; оба туннеля на диске; строка в БД.  
4. User с visibility скачивает свои профили в вебе.  
5. Сток AmneziaWG и AZ-WARP без регрессий.  
6. HA create не трогает replica для amneziawg2 (**superseded** волной 2).  
7. Тесты из раздела «Тесты» зелёные.
