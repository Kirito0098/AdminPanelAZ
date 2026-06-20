# План: суммарный трафик клиента в HA (Sync Groups)

Документ описывает реализацию отображения **агрегированного объёма трафика** для VPN-клиентов, входящих в **Node Sync Group (HA)** на странице **Мониторинг трафика**.

Связанные документы: [traffic-monitoring.md](traffic-monitoring.md), [NodeSync.md](NodeSync.md), [noc-monitoring.md](noc-monitoring.md).

---

## 1. Проблема

Сейчас страница **Мониторинг трафика** (`/traffic`) работает только с **активным узлом**:

- `GET /api/traffic/overview` → `TrafficCollectorService(db, active_node.id)`
- `GET /api/traffic/chart` → `UserTrafficSample` с `node_id = active_node`
- `GET /api/traffic/client-sessions` → `TrafficSessionState` с `node_id = active_node`

Статистика в БД хранится **per node** (`UserTrafficStatProtocol`, `UserTrafficSample`, `TrafficSessionState` — поле `node_id`).

В HA-сценарии один логический клиент (`client_name` + протокол) может потреблять трафик на **разных узлах** (failover primary ↔ replica). Администратор видит неполную картину: после переключения на replica «обнуляется» видимый объём, хотя реальный расход клиента — сумма по всем узлам группы.

В [NodeSync.md](NodeSync.md) явно зафиксировано: *consumed traffic не синхронизируется, считается per node* — это корректно для **хранения**, но **UI мониторинга** должен уметь показывать логический итог.

---

## 2. Цели

| # | Цель |
|---|------|
| G1 | В таблице трафика для HA-клиентов показывать **суммарный** объём по всем узлам Sync Group |
| G2 | График, сессии и статус «онлайн» — согласованы с агрегированными цифрами |
| G3 | Переиспользовать существующую HA-логику (`sync_group_id`, lookup из NOC) |
| G4 | Не дублировать теневые конфиги (`ha_primary_config_id`) в агрегации |
| G5 | UX: бейдж HA + понятная подпись «сумма по N узлам» |

## 3. Вне scope (первая итерация)

| # | Не делаем сейчас | Комментарий |
|---|------------------|-------------|
| N1 | Синхронизация consumed bytes между узлами | Хранение остаётся per node |
| N2 | Автоматический сброс трафика на всех узлах HA при reset | Отдельное решение (см. §8) |
| N3 | Изменение reconcile лимитов на сумму по HA | **Фаза 2** — см. §9 |
| N4 | Агрегация в Telegram-боте / PDF-отчётах | Можно добавить позже по тому же API |

---

## 4. Текущая архитектура (опорные файлы)

### Backend

| Файл | Роль |
|------|------|
| `backend/app/routers/traffic.py` | API overview / chart / sessions |
| `backend/app/services/traffic/collector.py` | `get_summary()`, `_recent_usage()` — per `node_id` |
| `backend/app/services/traffic/chart.py` | `fetch_traffic_chart()` — per `node_id` |
| `backend/app/services/traffic/sessions.py` | `fetch_client_sessions()` — per `node_id` |
| `backend/app/services/monitoring_overview.py` | `_build_ha_monitoring_lookup()` — готовый lookup HA |
| `backend/app/services/node_sync/groups.py` | `group_member_node_ids()`, `build_ha_metadata()` |
| `backend/app/services/traffic_limit.py` | `get_client_consumed_traffic_bytes(node_id=...)` — per node |
| `backend/app/schemas.py` | `TrafficClientRow`, `VpnConfigHaInfo` |

### Frontend

| Файл | Роль |
|------|------|
| `frontend/src/pages/TrafficPage.tsx` | Таблица, сводка, выбор клиента |
| `frontend/src/components/traffic/TrafficClientDetails.tsx` | График, лимит, сессии |
| `frontend/src/types.ts` | `TrafficClientRow` (без полей HA) |

### Существующий паттерн в NOC

В `monitoring_overview.py` для **live-подключений** HA-клиенты **схлопываются в одну строку** (берётся узел с max трафиком / online). Для **исторического накопленного** трафика нужна **сумма**, не `max`.

---

## 5. Предлагаемое решение

### 5.1. Общая логика

```
active_node → find_sync_group_containing_node()
  ├─ группы нет → поведение как сейчас (solo node)
  └─ группа есть → node_ids = group_member_node_ids(group)
        для каждого (client_name, protocol_type):
          агрегировать stats/samples/sessions по всем node_ids
          одна строка в overview с ha-метаданными
```

**Ключ агрегации** (как в NOC):

```python
agg_key = ("ha", sync_group_id, protocol, client_name.lower())
```

Для клиентов вне HA:

```python
agg_key = ("solo", node_id, protocol, client_name.lower())
```

### 5.2. Правила суммирования

| Поле | Правило |
|------|---------|
| `total_received`, `total_sent`, `total_*_vpn`, `total_*_antizapret` | **SUM** по узлам группы |
| `traffic_1d`, `traffic_7d`, `traffic_30d` | **SUM** samples за окно по всем узлам |
| `total_sessions` | **SUM** (сессии на разных узлах — разные записи) |
| `first_seen_at` | **MIN** по узлам |
| `last_seen_at` | **MAX** по узлам |
| `is_active` | **OR** — онлайн, если активен на **любом** узле группы |

### 5.3. Определение HA-принадлежности клиента

Переиспользовать lookup из `monitoring_overview._build_ha_monitoring_lookup()`:

- Вынести в общий модуль `backend/app/services/node_sync/ha_lookup.py` (или `traffic/ha_aggregate.py`)
- Lookup строится по `VpnConfig` с `sync_group_id` или `ha_primary_config_id`
- Теневые конфиги на replica маппятся на `sync_group_id` primary — **двойного учёта нет**

### 5.4. Сбор `active_names` для HA

Сейчас `_active_traffic_client_names()` опрашивает только **активный адаптер**.

Для HA нужно:

1. Опросить live-статус **всех online-узлов** группы (через `get_adapter_for_node`)
2. Объединить `common_name` / `client_name` в один `active_names`
3. При ошибке узла — fallback на `TrafficSessionState` для этого `node_id`

---

## 6. Изменения API / схем

### 6.1. Расширение `TrafficClientRow`

```python
class TrafficHaNodeBreakdown(BaseModel):
    node_id: int
    node_name: str
    total_bytes: int = 0
    traffic_7d: int = 0
    is_active: bool = False

class TrafficClientRow(BaseModel):
    # ... существующие поля ...
    ha: VpnConfigHaInfo | None = None
    ha_aggregated: bool = False
    ha_node_breakdown: list[TrafficHaNodeBreakdown] | None = None
```

- `ha_aggregated=True` — цифры в строке уже суммированы по группе
- `ha_node_breakdown` — опционально, для детального разбора (можно отдавать только в overview при `?breakdown=1` или всегда — решить на этапе реализации; по умолчанию — всегда в деталях клиента)

### 6.2. Расширение ответа overview

```python
class TrafficOverview(BaseModel):
    # ... существующие поля ...
    ha_context: TrafficHaContext | None = None  # если active node в группе
```

```python
class TrafficHaContext(BaseModel):
    sync_group_id: int
    group_name: str
    shared_domain: str
    node_count: int
    member_node_ids: list[int]
    aggregation_mode: str = "sum"  # для документирования контракта
```

### 6.3. Chart / sessions

Ответы chart и sessions **без смены URL**; меняется только внутренняя агрегация:

- **chart**: запрос samples по `node_id IN member_ids`, merge buckets по timestamp
- **sessions**: объединение сессий всех узлов; в breakdown по IP добавить `node_id` / `node_name`

Дополнительно в `TrafficClientSessionsResponse`:

```python
ha_aggregated: bool = False
nodes: list[TrafficSessionNodeSummary] | None = None  # счётчики per node
```

---

## 7. План работ по этапам

### Этап A — Backend: общий HA lookup для трафика

**Файлы:** новый `backend/app/services/traffic/ha_aggregate.py`, рефакторинг `monitoring_overview.py`

- [ ] Вынести `_build_ha_monitoring_lookup`, `_aggregation_key_for_client` в общий модуль
- [ ] Добавить `resolve_ha_node_ids(db, node_id) -> list[int]` — solo: `[node_id]`, HA: все member
- [ ] Добавить `aggregate_traffic_rows(rows_by_node, ha_lookup) -> list[dict]`
- [ ] Unit-тесты на merge: 2 узла, один клиент, проверка SUM и MIN/MAX дат

### Этап B — Backend: overview

**Файлы:** `collector.py`, `traffic.py`

- [ ] `TrafficCollectorService.get_summary_ha(node_ids, active_names, ...)` или параметр `node_ids: list[int]`
- [ ] `_recent_usage()` — фильтр `node_id.in_(node_ids)`
- [ ] `traffic_overview`: определить HA-контекст, собрать active_names со всех узлов
- [ ] Дедупликация строк: один `common_name + protocol` на HA-группу
- [ ] Summary (карточки вверху страницы) — по агрегированным строкам

### Этап C — Backend: chart и sessions

**Файлы:** `chart.py`, `sessions.py`, `traffic.py`

- [ ] `fetch_traffic_chart(db, node_ids: list[int], ...)` — merge time-series
- [ ] `fetch_client_sessions(db, node_ids, ...)` — merge + `node_name` в каждой сессии / IP-группе
- [ ] Роутеры передают `resolve_ha_node_ids(db, active_node.id)`

### Этап D — Frontend: таблица и детали

**Файлы:** `types.ts`, `TrafficPage.tsx`, `TrafficClientDetails.tsx`

- [ ] Типы `TrafficClientRow`, `TrafficHaContext`, `TrafficHaNodeBreakdown`
- [ ] Бейдж HA в строке таблицы (как в `MonitoringConnectionsList` / конфигах)
- [ ] Подпись: «Сумма по {node_count} узлам HA»
- [ ] В `TrafficClientDetails`: блок «По узлам» — таблица breakdown
- [ ] Баннер в шапке страницы, если `ha_context` присутствует: «Показан суммарный трафик группы …»

### Этап E — Документация

**Файлы:** `docs/traffic-monitoring.md`, `docs/NodeSync.md`, `CHANGELOG.md`

- [ ] Описать HA-агрегацию в user-facing docs
- [ ] В NodeSync — ссылка: UI суммирует, storage per node
- [ ] Changelog entry

### Этап F (опционально, фаза 2) — Лимиты трафика по HA

**Файлы:** `traffic_limit.py`, `access_policy.py`

Сейчас `get_client_consumed_traffic_bytes(..., node_id=...)` считает только один узел. Прогресс-бар лимита в `TrafficClientDetails` может расходиться с агрегированной таблицей.

- [ ] Если клиент в HA — `consumed_bytes` = сумма по `member_node_ids`
- [ ] `reconcile_all_traffic_limits` на primary проверяет суммарный consumed (или reconcile на всех узлах с одним порогом)
- [ ] Обновить [NodeSync.md](NodeSync.md): лимит применяется к логическому клиенту

**Риск:** блокировка на replica при превышении лимита, набранного на primary — нужно reconcile на всех member.

---

## 8. Сброс и обслуживание трафика

| Операция | Текущее поведение | Рекомендация |
|----------|-------------------|--------------|
| `POST /traffic/reset` | Только active node | **Фаза 1:** без изменений + предупреждение в UI при HA |
| | | **Фаза 2:** опция `scope=ha_group` — сброс на всех member (admin confirm) |
| `POST /traffic/delete-deleted-client` | active node | Аналогично — удалять stats на всех узлах группы, если клиент был HA |
| Stale indicator (`db_is_stale`) | max sample age на active node | При HA: max age **по всем узлам** группы |

---

## 9. Edge cases

| Ситуация | Поведение |
|----------|-----------|
| Активный узел — **replica** | Агрегация по всей группе (не только replica) |
| Узел группы **offline** | Его исторические stats включаются в сумму; live active — пропуск с fallback на DB |
| Клиент только на primary, не на replica | Сумма = данные primary (replica пусто) |
| `manual_full` без shadow configs | Агрегация по `sync_group_id` на primary + stats replica после Push full |
| `auto` с shadow `VpnConfig` | Lookup через `ha_primary_config_id` → без двойного счёта |
| Клиент подключён **одновременно** к двум узлам (split-brain / DNS) | Сумма может завыситься; допустимо для MVP, в docs — предупреждение |
| Один `client_name` на OpenVPN и WireGuard | Отдельные строки агрегации (ключ включает `protocol`) |
| Self-service user (не admin) | Агрегация только в рамках разрешённых клиентов; `node_ids` не расширяют видимость чужих клиентов |

---

## 10. Тестирование

### Backend (pytest)

| Тест | Сценарий |
|------|----------|
| `test_ha_aggregate_sum_two_nodes` | Один клиент, разный трафик на primary/replica → корректная сумма |
| `test_ha_aggregate_no_double_shadow` | Shadow config на replica не даёт вторую строку |
| `test_ha_active_or` | Online на replica → `is_active=True` в агрегированной строке |
| `test_solo_node_unchanged` | Без Sync Group — результат идентичен текущему |
| `test_chart_merge_buckets` | Samples с двух узлов в одном 5-min bucket суммируются |
| `test_sessions_multi_node` | Сессии содержат `node_name` |

### Ручная проверка (QA)

1. Sync Group из 2 узлов, клиент `test-ha`
2. Нагрузить трафик на primary → проверить цифру в overview
3. Failover / подключение на replica → сумма = primary + replica
4. График 7d показывает оба периода
5. Детали клиента → breakdown по узлам
6. Клиент без HA — без бейджа, поведение как раньше

---

## 11. Порядок коммитов (рекомендуемый)

```
1. refactor: extract ha_lookup shared module (+ tests)
2. feat(traffic): HA aggregation in overview API
3. feat(traffic): HA aggregation in chart + sessions
4. feat(ui): HA badge + breakdown on TrafficPage
5. docs: traffic HA aggregation
```

---

## 12. Оценка трудозатрат

| Этап | Оценка |
|------|--------|
| A — lookup + tests | ~0.5 дня |
| B — overview | ~1 день |
| C — chart + sessions | ~0.5–1 день |
| D — frontend | ~0.5–1 день |
| E — docs | ~0.25 дня |
| F — лимиты (фаза 2) | ~1–2 дня |

**Итого MVP (A–E):** ~2.5–3.5 дня.

---

## 13. Критерии готовности (Definition of Done)

- [ ] HA-клиент в таблице `/traffic` показывает суммарный объём по всем узлам группы
- [ ] Бейдж HA и пояснение в UI
- [ ] График и сессии согласованы с таблицей
- [ ] Без Sync Group поведение не изменилось
- [ ] Тесты на агрегацию проходят
- [ ] Документация обновлена
