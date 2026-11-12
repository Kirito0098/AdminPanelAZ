# ADR-001. AdminPanelAZ: слои, границы и точки связности

> Дубликат ADR из индекса `codebase-memory` (`manage_adr`), чтобы документ версионировался
> в репозитории. Карта проекта — [`PROJECT_MAP.md`](PROJECT_MAP.md).

## Статус

Принято · 2026-11-03 · по графу `opt-AdminPanelAZ`: 19 435 узлов, 80 732 связи, ветка `release/2.26.6`.
Пересматривать при смене слоёв или границ модулей, а не при каждой фиче.

## Контекст

Панель администрирования VPN-сервера AntiZapret: FastAPI + React SPA + Telegram-бот и Mini App +
агенты узлов (node/proxy), установка через `install.sh` и `scripts/`. В кодовой базе ~1 100 файлов
кода (579 Python, 420 TypeScript, 84 Bash), 1 078 маршрутов, 1 391 связь `TESTS` (165 тест-файлов).
Документ фиксирует фактическую структуру, чтобы не переоткрывать её в каждой сессии.

## Решение: как устроено

### Поток

```
React SPA (Vite) ──┐
TG Mini App ───────┼─→ Nginx ─→ FastAPI :8000 (backend/app) ─→ adminpanel.db / cidr.db
TG Bot (webhook) ──┘                    │
                                        └─→ node_agent :9100 / proxy_agent :9101 (mTLS)
```

### Слои бэкенда

- `backend/app/main.py` — сборка приложения; `routers/` — HTTP (1 078 узлов `Route`);
- `services/` — домен: `node_manager`, `node_adapter`, `antizapret*`, `awg2*`, `access_policy`,
  `client_names`, `config_provisioning`, `frontend_assets`, `cidr/pipeline`, фоновые воркеры;
- `models.py` + `database.py` — SQLAlchemy, `adminpanel.db`; `cidr_models.py` + `cidr_database.py` —
  отдельная `cidr.db`;
- `auth.py`, `middleware/`, `api_rate_limit` — аутентификация (JWT/2FA/passkey), лимиты, права.

### Слои фронтенда

`src/api/http.ts` (`apiFetch`) → хуки и страницы → `components/ui` (базовые компоненты).
Кластер frontend: 800 узлов, cohesion 0.956 — самая связная часть системы.

### Скрипты (Bash)

`nginx-common` — ядро (fan-in 97, 0 исходящих), `nginx-setup` и `full-update` — точки входа,
`python-runtime` и `site-diagnostics` — листья. `full-update` дополнительно вызывает
`adminpanel-menu` (41) и `nginx-common` (13).

## Точки связности

Сознательные концентраторы; обход — не оптимизация, а смена контракта.

| Символ | fan-in | Роль |
|---|---|---|
| `frontend.src.api.http.apiFetch` | 358 | единственный HTTP-клиент фронта |
| `backend.app.config.get_settings` | 187 | доступ к конфигурации |
| `node_manager.get_active_node` | 144 | выбор активного узла |
| `node_manager.get_active_adapter` | 132 | выбор адаптера узла |
| `RemoteNodeAdapter._request` | 132 | единственная точка запросов к узлу |
| `components.ui.badge.Badge` | 142 | базовый UI-компонент |

Внутри `provision_config` используется `get_adapter_for_node(node)`, а **не** `get_active_adapter`:
провижининг идёт на конкретный узел.

## Известный долг (зафиксировано, не чинится попутно)

Циклы по `CALLS` (6 пар):

1. `streamTicket.scheduleReconnect` ↔ `connect`
2. `backups.create_backup` ↔ `_create_backup_with_optional_telegram`
3. `cidr.pipeline.db_service._download_text` ↔ `_download_text_impl`
4. `frontend_assets.FrontendAssets.get_response` ↔ `_file`
5. `useRoutingPage.refreshCidrDb` ↔ `runRefreshCidrDb`
6. `dns_servers.apply_dns_servers` ↔ `_replicate_to_replicas`

Слепые зоны графа: каталог `deploy/` (8 nginx-шаблонов) в индекс не входит — читать напрямую;
частично разобраны `frontend/src/types.ts`, `backend/pytest.ini`, `schema_2_25_1.sql`,
`full-update.sh` и два test-скрипта.

## Последствия

- Проверки добавляются на границах доверия (HTTP-схемы Pydantic, ответы агентов, webhook
  Telegram, файлы с диска, вывод внешних команд), внутри — доверие типам и схемам.
- Правка в концентраторах (`apiFetch`, `get_settings`, `node_manager`, `RemoteNodeAdapter._request`)
  требует прогона затронутых тестов, а не только линтера.
- Циклы трогаем только если задача уже задевает эти функции.
- Тесты — только на критических узлах (auth/2FA/JWT, публичная раздача конфигов, webhook,
  nginx/firewall/systemd/install, бэкапы, агенты, VPN-клиенты, лимиты).
