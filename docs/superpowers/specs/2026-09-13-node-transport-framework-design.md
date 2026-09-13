# Node transport framework + picker

**Дата:** 2026-09-13  
**Статус:** implemented  
**Ветка:** `feature/client-portal`  
**Подход:** вариант **A** — Transport registry + колонка `transport`; P0: `http`/`mtls`; `ssh` — stub API/UI

## Контекст

Панель ходит к VPN (`node_agent`, :9100) и proxy (`proxy_agent`, :9101) через HTTP или HTTPS+mTLS. Выбор сегодня — булев `nodes.mtls_enabled` и кнопки «Включить / Отключить mTLS», не явный picker способов связи.

Нужно:

1. Единая модель **transport** для VPN и proxy.  
2. Каркас (registry/protocol), чтобы позже добавить SSH tunnel без переписывания adapters.  
3. В P0 — picker HTTP/mTLS; SSH виден, но недоступен.

Связь с уже сделанным: link diagnostics (`expected_tls`, `node_tls_mismatch`) продолжает работать; источник TLS-ожидания переезжает на transport.

## Решения brainstorm

| Тема | Выбор |
|------|--------|
| Горизонт | Framework + picker HTTP/mTLS сейчас; SSH — следующий plugin по тому же API |
| Scope узлов | VPN **и** proxy — одно поле `transport` |
| Подход | **A** — registry + колонка `transport` |
| Stub SSH в БД | **Не писать** `ssh` в БД в P0 (400 `transport_not_implemented`) |
| Compat | `mtls_enabled` в API — **derived** от `transport == "mtls"` |

## §1. Цель и границы

**In scope (P0):**

- Колонка `nodes.transport`, миграция с `mtls_enabled`.  
- `NodeTransport` protocol + registry (`http`, `mtls`, stub `ssh`).  
- Adapters / health / link errors берут TLS/scheme из transport.  
- API: список transports + PATCH transport; enable/disable-mtls как shorthand.  
- UI: select «Способ связи» (VPN + proxy); badge/TG по `transport`.  
- Тесты миграции, registry, PATCH, adapters, FE picker.

**Out of scope:**

- Реальный SSH (туннель, ключи, jump host).  
- Reverse channel / WG mesh / gRPC / Unix socket.  
- Смена wire protocol агента (по-прежнему HTTP API поверх канала).  
- Удаление `mtls_enabled` из БД в том же PR (колонка может остаться sync’d или только derived в DTO — см. §2).

## §2. Data model

```text
nodes.transport: str  # "http" | "mtls" | "ssh"
  default: "http"
```

**Миграция (Alembic / startup migrate):**

- `mtls_enabled IS true` → `transport = 'mtls'`  
- иначе → `transport = 'http'`  
- local nodes: значение не используется UI/adapters (как сейчас «—»).

**`mtls_enabled`:**

- В **API response** всегда: `mtls_enabled = (transport == "mtls")` (не local → false для local как сейчас).  
- В **БД** на переходный период: при смене transport синхронизировать `mtls_enabled` с derived, чтобы сырой SQL/бэкапы/старые скрипты не врали. Отдельный follow-up может дропнуть колонку.

**Допустимые значения записи в БД в P0:** только `http`, `mtls`. Значение `ssh` в PATCH → отказ без записи.

## §3. Архитектура

```text
UI picker ──► PATCH /nodes/{id}/transport
                    │
                    ▼
              nodes.transport
                    │
Health / Adapters ──► get_transport(node) ──► TransportRegistry
                                              ├── HttpTransport
                                              ├── MtlsTransport  (node_mtls helpers)
                                              └── SshTransport   (raises / not registered for resolve-from-DB)
```

### Модуль

`backend/app/services/node_transport/` (или один модуль `node_transport.py` если тонкий):

| Символ | Роль |
|--------|------|
| `NodeTransport` | Protocol: `id`, `display_name`, `is_tls`, `base_scheme()`, `ssl_context()` / `client_kwargs()` |
| `HttpTransport` | `http`, `is_tls=False`, verify off / как сейчас без mTLS |
| `MtlsTransport` | обёртка над `build_node_agent_ssl_context` / `node_agent_base_scheme(mtls=True)` |
| `SshTransport` | stub: `available=False`; `connect`/factory не вызывается из adapters в P0 |
| `get_transport(node)` | resolve по `node.transport`; unknown → treat as `http` + log warning **или** fail closed — **fail closed** с `node_error` предпочтительнее для unknown |
| `list_transports()` | для `GET /nodes/transports`: id, label, available |

Существующий [`node_mtls.py`](backend/app/services/node_mtls.py) не дублировать — Mtls/Http делегируют в него.

### Call sites

- [`node_adapter.py`](backend/app/services/node_adapter.py) `RemoteNodeAdapter`  
- [`proxy_node_adapter.py`](backend/app/services/proxy_node_adapter.py)  
- [`node_manager.py`](backend/app/services/node_manager.py) (сбор adapter / expected_tls)  
- Health worker meta: `expected_tls = transport.is_tls`  
- Provision: [`node_mtls_provision.py`](backend/app/services/node_mtls_provision.py) — enable → `transport=mtls` + certs (VPN); disable → `transport=http`; proxy «отметить mTLS» — только флаг/transport без panel cert push (как сейчас)

Агенты **не** меняют версию ради P0 (канал тот же HTTP(S)).

## §4. API

### `GET /api/nodes/transports`

```json
{
  "items": [
    { "id": "http", "label": "HTTP", "available": true },
    { "id": "mtls", "label": "HTTPS + mTLS", "available": true },
    { "id": "ssh", "label": "SSH tunnel", "available": false }
  ]
}
```

(Точный path согласовать с префиксом router’а nodes.)

### `PATCH /api/nodes/{node_id}/transport`

Body: `{ "transport": "http" | "mtls" | "ssh" }`

| Запрос | Поведение |
|--------|-----------|
| `http` | Как текущий disable-mtls: сброс transport/флага; VPN — без обязательного wipe certs на агенте если уже так в disable |
| `mtls` | Как enable-mtls: VPN provision certs при необходимости; proxy — mark only |
| `ssh` | **400**, code `transport_not_implemented`, БД не менять |
| local node | **400** — transport не применим |
| тот же transport | no-op 200 |

Response: обновлённый node DTO (`transport` + derived `mtls_enabled`).

### Compat endpoints

- `POST …/enable-mtls` → внутренняя установка `transport=mtls` (та же provision-логика).  
- `POST …/disable-mtls` → `transport=http`.  

Не удалять в P0 — FE/скрипты/TG могут звать старое; новый UI зовёт PATCH.

### Node DTO

Добавить `transport: str`. Сохранить `mtls_enabled: bool` (derived).

## §5. UI

- Primary: select **«Способ связи»** на действиях/карточке для remote VPN и proxy.  
  - Опции из `GET …/transports` (ssh disabled + tooltip «Скоро»).  
- [`NodeTransportBadge`](frontend/src/components/nodes/NodeTransportBadge.tsx): по `transport` (`HTTP` / `mTLS` / при появлении ssh — `SSH`).  
- TG mini badge — то же.  
- Кнопки Вкл/Выкл mTLS: **optional shortcuts** (тонкие) или убрать, если select покрывает; предпочтение — **select primary**, shortcuts не обязательны.  
- Bulk «включить mTLS» (если есть): перевести на `transport=mtls` через тот же сервис.

Связь с блоком «Связь» (diagnostics): `expected_tls` из transport; без нового UI-блока в этом spec.

## §6. Ошибки

| Код | Когда |
|-----|--------|
| `transport_not_implemented` | PATCH `ssh` (и будущие unavailable) |
| существующие `node_*` | без изменений; TLS path через `is_tls` |

Не вводить logout на transport errors.

## §7. Тесты и критерии готовности

**Backend:** миграция mapping; `get_transport` http/mtls; PATCH http↔mtls; PATCH ssh → 400 без записи; enable/disable-mtls sync transport; adapter scheme/ssl; `expected_tls` в health meta.  
**Frontend:** picker меняет transport; badge; derived `mtls_enabled` в типах/тестах fixtures.  

**Готово когда:**

- VPN и proxy показывают один picker.  
- Переключение HTTP↔mTLS эквивалентно старому enable/disable.  
- SSH в списке, выбрать нельзя / 400.  
- Link diagnostics не регрессируют на mtls mismatch.  
- CHANGELOG Unreleased: transport framework + picker.

## Файлы (ориентир)

| Область | Файлы |
|---------|--------|
| Model / migrate | `backend/app/models.py`, alembic или `migrate.py` |
| Transport | `backend/app/services/node_transport*` |
| Provision | `node_mtls_provision.py`, routers `nodes.py` |
| Adapters | `node_adapter.py`, `proxy_node_adapter.py`, `node_manager.py` |
| FE | `types.ts`, Nodes actions/badge, `api/nodes.ts`, tg-mini Nodes |
| Docs | этот spec, CHANGELOG при реализации |

## Follow-up (не P0)

- Реальный `SshTransport`: local forward, хранение host/user/key ref, health через туннель.  
- Drop колонки `mtls_enabled` после полного cutover клиентов API.  
- Другие plugins (reverse, mesh) по тому же registry.
