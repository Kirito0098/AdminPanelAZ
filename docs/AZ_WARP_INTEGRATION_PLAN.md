# План интеграции AZ-WARP (WARPER) в AdminPanelAZ

> Точечная маршрутизация доменов и IPv4-подсетей через Cloudflare WARP / Slave / WireGuard  
> на VPN-узлах с [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN).  
> Upstream: [Liafanx/AZ-WARP](https://github.com/Liafanx/AZ-WARP)

Документ описывает поэтапный план: установка WARPER на узлах, backend (Controller + Node Agent), UI во вкладке «Маршрутизация», тесты и rollout.

---

## Целевая архитектура

WARPER **не поднимает отдельный публичный HTTP-сервис**. Управление идёт через существующий Node Agent; веб-панель AZ-WARP **не устанавливается**.

```
React (WarperPage `/warper` — отдельный пункт меню)
    ↓ JWT (admin)
FastAPI Controller  /api/warper/*
    ↓ NodeAdapter (local / remote)
Node Agent :9100    /warper/*  (+ X-API-Key / mTLS)
    ↓ sys.path → /root/warper/py
warper_api.WarperAPI  →  warper CLI  →  sing-box + kresd
```

Аналогия с уже реализованным:

| Существующее | WARPER (новое) |
|--------------|----------------|
| `AntiZapretService` → `client.sh` | `WarperService` → `warper_api` |
| `GET/PUT /api/routing/antizapret-settings` | `GET/POST/DELETE /api/warper/...` |
| `node_agent` `/routing/antizapret-settings` | `node_agent` `/warper/...` |
| `AntizapretConfigTab.tsx` | `WarperPage.tsx` + компоненты `components/warper/*` |

---

## Предварительные условия на узле

### Установка WARPER (ops, вне кода панели)

На каждом VPN-узле с AntiZapret (root):

```bash
curl -fsSL https://raw.githubusercontent.com/Liafanx/AZ-WARP/main/install.sh | bash
```

Рекомендуемые ответы installer’у:

| Вопрос | Ответ |
|--------|--------|
| Gemini / ChatGPT в domains.txt | **n** (если не нужны сразу) |
| Веб-панель WARPER | **n** |
| Режим | WARP / Slave / WG — по задаче |

Проверка:

```bash
warper doctor
warper status
test -f /root/warper/py/warper_api/__init__.py && echo OK
```

### Совместимость с AntiZapret

| Параметр в `/root/antizapret/setup` | WARPER |
|-------------------------------------|--------|
| `ANTIZAPRET_WARP=n` | ✅ доменная маршрутизация WARPER работает |
| `ANTIZAPRET_WARP=y` | ❌ конфликт — WARPER не активен |
| `VPN_WARP=n` | ✅ можно включить FullVPN WARP-резолвинг в WARPER |
| `VPN_WARP=y` | ✅ совместимо (AntiZapret через WARPER, FullVPN через встроенный WARP) |

После изменения доменов/CIDR клиентам **OpenVPN** нужно переподключиться; **WG/AWG** — пересборка профиля (новые маршруты в `route-ips.txt` / fake-подсеть).

### Multi-node

- WARPER ставится **на каждый узел** отдельно.
- Controller обращается к **активному узлу** через `get_active_adapter(db)` (как маршрутизация и конфиг AntiZapret).
- В UI показывать `node_id` / `node_name` в ответах API (паттерн `AntizapretSettingsResponse`).

---

## Feature toggle

Добавить модуль (зависит от `routing`, но можно отключать отдельно):

| Поле | Значение |
|------|----------|
| `key` | `warper` |
| `env_key` | `FEATURE_WARPER_ENABLED` |
| `group` | `app_module` |
| `api_prefixes` | `("/api/warper",)` |
| `frontend_paths` | `("/warper",)` — отдельный пункт sidebar |

**Файл:** `backend/app/services/feature_toggles.py`

Опционально: в `node_health` / health payload добавить `warper_installed: bool`, `warper_active: bool` для баннера «WARPER не установлен на узле».

---

## Backend — фаза 1: WarperService (Node Agent)

### Новый модуль

**`backend/app/services/warper.py`**

- Проверка наличия: `/usr/local/bin/warper`, `/root/warper/py/warper_api/`.
- Lazy-import `WarperAPI` с `sys.path.insert(0, "/root/warper/py")`.
- Обёртка над методами с маппингом `WarperResult` → dict / HTTPException.
- `WarperNotInstalledError` → 503 с понятным текстом.
- Конфликт `ANTIZAPRET_WARP=y` → 409 + подсказка отключить в «Конфиг AntiZapret».

Минимальный набор методов (MVP):

```python
get_status() -> dict
is_installed() -> bool
doctor() -> list[dict]
toggle() / enable() / disable()
list_domains() -> list[dict]
add_domain(domain: str) -> dict
remove_domain(domain: str) -> dict
sync_domains() -> dict
enable_list(name: str) / disable_list(name: str)  # gemini, chatgpt
list_ip_ranges() -> list
add_ip_range(cidr: str) / remove_ip_range(cidr: str)
sync_ip_ranges() -> dict
get_traffic(period: str) -> dict
get_logs(lines: int) -> list
get_mode() / set_mode_warp(...) / set_mode_slave(...) / set_mode_wg(...)
set_mtu(mtu: int) / set_log_level(level: str)
catalog_search(query: str) / catalog_add(name: str) / catalog_remove(name: str)
```

Переиспользовать логику адаптации из upstream `web/web_api.py` (bulk add, валидация доменов) по мере необходимости — **не копировать Flask**, только бизнес-правила.

### Node Agent endpoints

**`backend/node_agent/main.py`** — префикс `/warper`:

| Method | Path | Описание |
|--------|------|----------|
| GET | `/warper/health` | installed, active, version, conflict_antizapret_warp |
| GET | `/warper/status` | полный статус JSON |
| GET | `/warper/doctor` | диагностика |
| POST | `/warper/toggle` | вкл/выкл |
| GET | `/warper/domains` | список |
| POST | `/warper/domains` | `{ "domain": "..." }` |
| DELETE | `/warper/domains/{domain}` | удаление |
| POST | `/warper/domains/sync` | sync + patch DNS |
| POST | `/warper/domains/lists/{name}` | `{ "enable": true }` — gemini/chatgpt |
| GET | `/warper/ip-ranges` | список CIDR |
| POST | `/warper/ip-ranges` | `{ "cidr": "..." }` |
| DELETE | `/warper/ip-ranges/{cidr}` | URL-encoded CIDR |
| POST | `/warper/ip-ranges/sync` | |
| POST | `/warper/ip-ranges/mode` | `{ "mode": "antizapret"|"all_vpn"|"all" }` |
| POST | `/warper/ip-ranges/export` | `{ "enable": true }` — экспорт в AntiZapret |
| GET | `/warper/traffic` | query `period=today|week|month|all` |
| GET | `/warper/logs` | query `lines=200` |
| GET | `/warper/settings/mode` | текущий режим |
| PUT | `/warper/settings/mode/warp` | `{ "key_source": "system"|... }` |
| PUT | `/warper/settings/mode/slave` | server, port, password |
| PUT | `/warper/settings/mode/wg` | `{ "conf_path": "..." }` |
| PUT | `/warper/settings/mtu` | `{ "mtu": 1420 }` |
| PUT | `/warper/settings/log-level` | `{ "level": "info" }` |
| PUT | `/warper/settings/fullvpn-resolve` | `{ "enable": bool }` |
| GET | `/warper/catalog/search` | query `q=` |
| GET | `/warper/catalog/installed` | |
| POST | `/warper/catalog/{name}` | add |
| DELETE | `/warper/catalog/{name}` | remove |
| POST | `/warper/singbox/{action}` | start \| stop \| restart |

Все маршруты — за `verify_api_key` (как остальной agent).

---

## Backend — фаза 2: NodeAdapter + Controller

### NodeAdapter

**`backend/app/services/node_adapter.py`**

- Абстрактные методы `warper_*` в `NodeAdapter`.
- `LocalNodeAdapter` → `WarperService`.
- `RemoteNodeAdapter` → `_request("GET|POST|...", "/warper/...")`.

Обновить **`backend/tests/test_node_adapter_parity.py`** — таблица `REMOTE_ADAPTER_ENDPOINTS` для новых методов.

### Pydantic schemas

**`backend/app/schemas.py`** (или `schemas/warper.py`):

- `WarperHealthResponse`
- `WarperStatusResponse`
- `WarperDomainItem`, `WarperDomainCreate`
- `WarperIpRangeCreate`, `WarperTrafficResponse`
- `WarperCatalogItem`
- обёртки с `node_id`, `node_name` где нужно

### Controller router

**`backend/app/routers/warper.py`**

```python
router = APIRouter(prefix="/warper", tags=["warper"])
```

- `require_admin` на mutating endpoints; `get_current_user` на read-only (или всё admin — как antizapret-settings).
- `get_active_adapter(db)`, `get_active_node(db)`.
- Feature guard: модуль `warper` (middleware по `/api/warper`).

**`backend/app/main.py`:** `app.include_router(warper.router, prefix="/api")`

---

## Frontend — фаза 3: UI

### Размещение — отдельная страница (рекомендуется)

**Почему не вкладка в `/routing`:** на странице «Маршрутизация / CIDR» уже **7 вкладок** (Обзор, Провайдеры, CIDR Pipeline, Пресеты, Файлы, Игровые фильтры, Конфиг AntiZapret). WARPER — отдельная подсистема (sing-box, fake-IP, точечные домены), логически смежная, но не часть CIDR pipeline. Восьмая вкладка перегружает UI, особенно на мобильном.

**Решение:** отдельная страница **`/warper`** и пункт в sidebar (после «Маршрутизация / CIDR»):

| Файл | Назначение |
|------|------------|
| `frontend/src/pages/WarperPage.tsx` | страница-контейнер, header + внутренние Tabs |
| `frontend/src/components/warper/*.tsx` | DomainsTab, IpRangesTab, StatusSection, … |
| `frontend/src/App.tsx` | `<Route path="warper" element={<FeatureGuardRoute feature="warper">…` |
| `frontend/src/components/Layout.tsx` | `{ to: '/warper', label: 'WARPER', icon: Globe, featureKey: 'warper', adminOnly: true }` |

**Связь с маршрутизацией (без дублирования UI):**

- В `AntizapretConfigTab` — ссылка «Управление WARPER →» на `/warper` (рядом с toggles `ANTIZAPRET_WARP` / `VPN_WARP`).
- На `WarperPage` — alert при конфликте `ANTIZAPRET_WARP=y` со ссылкой на `/routing` (вкладка antizapret-config через hash или просто текст «Конфиг AntiZapret»).
- Опционально: карточка-виджет на `RoutingOverviewTab` «WARPER: active / N доменов» → link `/warper` (read-only, без CRUD).

**Альтернатива (не рекомендуется):** вкладка в `/routing` — только если сознательно не хотите расширять sidebar.

### API client

**`frontend/src/api/client.ts`:**

```typescript
getWarperHealth()
getWarperStatus()
getWarperDomains()
addWarperDomain(domain: string)
removeWarperDomain(domain: string)
syncWarperDomains()
// ... ip-ranges, traffic, settings, catalog
```

**`frontend/src/types.ts`:** типы ответов WARPER.

### Структура страницы (внутренние вкладки)

На **`WarperPage`** — свой `Tabs` (не путать с перегруженным `/routing`):

Рекомендуемый MVP UI:

| Секция | Содержимое | Приоритет |
|--------|------------|-----------|
| **Статус** | версия, active, outbound_mode (warp/slave/wg), sing-box, fake-subnet, конфликт `ANTIZAPRET_WARP` | P0 |
| **Домены** | таблица + поиск, add/remove, bulk textarea, sync, toggles Gemini/ChatGPT | P0 |
| **IP-подсети** | список CIDR, add/remove, sync, режим маршрутизации, экспорт в AntiZapret | P1 |
| **Трафик** | today/week/month, мини-карточки ↑↓ (как в AZ-WARP web) | P1 |
| **Настройки** | MTU, log level, FullVPN resolve, переключение режима WARP/Slave/WG | P2 |
| **Каталог** | search + add/remove tiktok и др. | P2 |
| **Логи** | последние N строк sing-box, фильтр level | P2 |
| **Диагностика** | кнопка «Запустить doctor», вывод как StatusPanel | P1 |

Переиспользовать компоненты:

- `StatusPanel`, `ConfirmDialog`, `Spinner`, `Badge`, `Button`, `Input`, `Tabs`
- паттерн загрузки/ошибок из `AntizapretConfigTab.tsx`
- `useNode()` — перезагрузка при смене активного узла

### UX-предупреждения

1. **Конфликт WARP:** если `ANTIZAPRET_WARP=y` — красный alert + ссылка на `/routing` (Конфиг AntiZapret).
2. **После sync domains / ip:** toast «Клиентам OVPN нужно переподключение; WG/AWG — обновить конфиг».
3. **Узел без WARPER:** «Установите AZ-WARP на узле `{node_name}`» + команда curl install.
4. **Feature disabled:** пункт меню скрыт; API 403; `FeatureGuardRoute` на `/warper`.

---

## Тесты — фаза 4

| Файл | Что проверять |
|------|----------------|
| `backend/tests/test_warper_service.py` | mock `WarperAPI`, not installed, conflict warp |
| `backend/tests/test_warper_api.py` | controller endpoints + auth + feature guard |
| `backend/tests/test_node_adapter_parity.py` | новые warper_* методы |
| `backend/tests/test_feature_guards.py` | `FEATURE_WARPER_ENABLED=false` |

Fixtures: не требовать реальный WARPER в CI — мокать `WarperService` / subprocess.

---

## Документация и changelog — фаза 5

- [`CHANGELOG.md`](../CHANGELOG.md) — запись о модуле WARPER.
- [`MIGRATION.md`](../MIGRATION.md) — строка «AZ-WARP / WARPER UI» (🆕 относительно AdminAntizapret).
- [`README.md`](../README.md) — кратко в таблице модулей + ссылка на этот план.
- [`docs/VPN_FEATURES_BACKLOG.md`](VPN_FEATURES_BACKLOG.md) — перенести пункт из идей в «реализовано» после MVP.

---

## Рекомендуемый порядок реализации

### MVP (1–2 итерации)

- [ ] `WarperService` + `/warper/health`, `/status`, domains CRUD + sync
- [ ] NodeAdapter local/remote
- [ ] Controller `/api/warper/*` (MVP endpoints)
- [ ] Feature toggle `warper`
- [ ] UI: страница `/warper` — статус + домены + doctor
- [ ] Тесты service + API + feature guard

### v1.1

- [ ] IP-подсети + traffic
- [ ] Конфликт `ANTIZAPRET_WARP` в UI и API
- [ ] Health на карточке узла / routing overview

### v1.2

- [ ] Настройки режима (WARP/Slave/WG), MTU, catalog
- [ ] Логи sing-box в UI
- [ ] Bulk import доменов/CIDR

### Backlog (по запросу)

- [ ] Per-node WARPER (выбор узла, не только active) — как в backlog multi-node
- [ ] Деплой/проверка WARPER через Node Agent (detect only, не auto-install)
- [ ] Webhook при смене списка доменов
- [ ] AdminNotify: «WARPER doctor failed»

---

## Чеклист перед merge

- [ ] WARPER на тестовом узле без веб-панели AZ-WARP
- [ ] `ANTIZAPRET_WARP=n`, `warper doctor` OK
- [ ] Local node: add domain → sync → проверка с клиента AntiZapret
- [ ] Remote node: те же операции через Node Agent
- [ ] Feature toggle off → 403 API, пункт меню скрыт
- [ ] `pytest` + `npm run build` + eslint без регрессий
- [ ] Нет новых открытых портов на узле (только 9100 agent как раньше)

---

## Связанные документы

- [AZ-WARP README](https://github.com/Liafanx/AZ-WARP/blob/main/README.md)
- [AZ-WARP Python API](https://github.com/Liafanx/AZ-WARP/blob/main/docs/python-api.md)
- [`MIGRATION.md`](../MIGRATION.md) — архитектура Controller + Node Agent
- [`docs/CIDR_PIPELINE_VARIANT_A.md`](CIDR_PIPELINE_VARIANT_A.md) — паттерн фаз и файлов
- [`docs/VPN_FEATURES_BACKLOG.md`](VPN_FEATURES_BACKLOG.md)

---

## Краткая справка: ключевые файлы проекта для правок

| Слой | Файлы |
|------|--------|
| Service | `backend/app/services/warper.py` |
| Node Agent | `backend/node_agent/main.py` |
| Adapter | `backend/app/services/node_adapter.py` |
| API | `backend/app/routers/warper.py`, `backend/app/schemas.py`, `backend/app/main.py` |
| Feature | `backend/app/services/feature_toggles.py` |
| Tests | `backend/tests/test_warper_*.py`, `test_node_adapter_parity.py` |
| UI | `frontend/src/pages/WarperPage.tsx`, `frontend/src/components/warper/*`, `Layout.tsx`, `App.tsx` |
| Client | `frontend/src/api/client.ts`, `frontend/src/types.ts` |
