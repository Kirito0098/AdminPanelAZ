# Ревью узлов и HA: найденные проблемы и предлагаемые правки

> Основан на анализе кодовой базы (2026). **Статус: правки внедрены** (2026-06-19), см. [HA-node-fix-plan.md](./HA-node-fix-plan.md).  
> Ниже — исходный анализ с отметками «реализовано / не реализовано / вне скоупа».
> Файлы-источники: `backend/app/routers/nodes.py`, `backend/app/routers/node_sync.py`,
> `backend/app/routers/configs.py`, `backend/app/services/node_manager.py`,
> `backend/app/services/node_sync/{groups,client_sync,push_full,verify,dissolve,reconcile_worker}.py`,
> `backend/app/models.py`, `backend/app/database.py`,
> `frontend/src/components/nodes/NodeSyncGroupSection.tsx`.

## Краткий итог

| # | Проблема | Серьёзность | Статус | Где |
|---|----------|-------------|--------|-----|
| 1 | Удаление узла не учитывает HA-группу | Критично | ✅ Реализовано (вариант A) | `routers/nodes.py` `delete_node` |
| 2 | `delete_node` не чистит связанные данные | Важно | ✅ Реализовано | `routers/nodes.py` / `node_manager.py` |
| 3 | `manual_full`: после dissolve клиенты replica не видны в панели | Важно | ✅ Реализовано (вариант A + B) | `config_import.py`, `push_full.py`, `configs.py` |
| 4 | `dissolve.py`: мёртвая ветка `stray_replica_configs`, неверный счётчик | Мелочь | ✅ Реализовано | `node_sync/dissolve.py` |
| 5 | Verify не обрабатывает offline primary | Мелочь | ✅ Реализовано | `node_sync/verify.py` |
| 6 | Частичный сбой auto-sync → split-brain | Наблюдение | ✅ Реализовано (уведомление) + документировано | `node_sync/client_sync.py`, `docs/NodeSync.md` |
| 7a | Трафик на replica после Push full | Важно | ✅ Реализовано | `traffic/collector.py`, `push_full.py` |
| 7b | Политики на replica после Push full | Важно | ✅ Реализовано | `policy_import.py`, `push_full.py` |
| 7c | Двойной счёт квоты user | Важно | ✅ Реализовано | `self_service.py` |

**Тесты:** `pytest` на HA-набор — **29 passed** (2026-06-19).

Подробнее про поведение **вкладок панели после dissolve** — раздел **#7** ниже.

Режимы группы:
- `manual_full` (по умолчанию) — только ручной **Push full** (файловый backup→restore).
- `auto` — `create/delete` на primary реплицируется на replica + теневые `VpnConfig` (`ha_primary_config_id`).

Для **auto** формирование и расформирование работают корректно (есть тесты `test_node_sync_dissolve.py`).

---

## 1. Критично: удаление узла не учитывает HA-группу

> **Статус: ✅ реализовано** — вариант A (`409 CONFLICT`). Тесты: `test_nodes_delete.py`.

### Симптом (было)
`delete_node` делает `db.delete(node)` без проверки членства в `NodeSyncGroup`.

- Удалили **primary** → `group.primary_node_id` указывает на несуществующий узел.
  `verify_sync_group` и `reconcile_worker` вызовут `get_adapter_for_node(None)` →
  `AttributeError` на `node.is_local`. Verify-эндпоинт → 500, reconcile-проход прерывается.
- Удалили **replica** → она остаётся в `replica_node_ids`, Verify всегда «not ready»,
  висят теневые `VpnConfig` с `node_id` удалённого узла.

### Текущий код (было)
```python
# backend/app/routers/nodes.py  (delete_node)
active_id = get_active_node_id(db)
db.delete(node)
db.commit()
```

### Предлагаемая правка (вариант A — запрет, рекомендуется) ✅ **выбран и внедрён**
Блокировать удаление узла, входящего в любую группу. Это безопаснее и понятнее для админа.

```python
from app.services.node_sync.groups import find_group_for_node

# внутри delete_node, до db.delete(node):
group = find_group_for_node(db, node.id)
if group:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Узел «{node.name}» входит в HA-группу «{group.name}». "
            f"Сначала расформируйте группу (Sync Groups → удалить)."
        ),
    )
```

### Предлагаемая правка (вариант B — авто-расформирование) ❌ **не реализовано**
Если хочется убирать узел без ручного шага — перед удалением расформировать/поправить группу:
- если узел primary → `dissolve_sync_group(db, group)` + удалить группу;
- если узел replica → убрать его id из `replica_node_ids` (а если реплик не осталось — расформировать).

Вариант A проще и предсказуемее; вариант B удобнее, но требует аккуратной обработки
теневых конфигов и пустых групп.

---

## 2. Важно: `delete_node` не чистит связанные данные

> **Статус: ✅ реализовано** — `purge_node_related` (публичная), вызов в `delete_node`.  
> **Не реализовано:** `PRAGMA foreign_keys=ON` в SQLite — отдельная задача (вне скоупа).

### Симптом (было)
Для локального узла есть очистка `_purge_node_related` (VpnConfig, traffic, policies, samples),
а роутерный `delete_node` (удалённого узла) — только `db.delete(node)`.
FK в SQLite **не включён** (`database.py` ставит лишь `journal_mode=WAL` и `busy_timeout`,
без `PRAGMA foreign_keys=ON`), поэтому остаются «осиротевшие» строки.
На Postgres тот же код упадёт `IntegrityError` (у `VpnConfig.node_id` нет `ondelete=CASCADE`).

### Эталон очистки (уже есть в коде)
```python
# backend/app/services/node_manager.py
def _purge_node_related(db: Session, node_id: int) -> None:
    for model in (VpnConfig, TrafficSessionState, UserTrafficStatProtocol,
        WgAccessPolicy, OpenVpnAccessPolicy, NodeResourceSample, UserTrafficSample):
        db.query(model).filter(model.node_id == node_id).delete(synchronize_session=False)
```

### Предлагаемая правка ✅ **внедрена**
В `delete_node` перед `db.delete(node)` вызвать ту же очистку:

```python
from app.services.node_manager import _purge_node_related  # или вынести в публичную функцию

active_id = get_active_node_id(db)
_purge_node_related(db, node.id)
db.delete(node)
db.commit()
```

> Опционально: переименовать `_purge_node_related` в `purge_node_related` (без подчёркивания),
> раз она используется из роутера. ✅ **сделано**

> Дополнительно стоит включить `PRAGMA foreign_keys=ON` в `_set_sqlite_pragmas`, чтобы
> рассинхрон ловился на уровне БД (но тогда нужны явные cascade/очистки везде — отдельная задача). ❌ **не сделано**

---

## 3. Важно: `manual_full` — после расформирования клиенты replica не видны в панели

> **Статус: ✅ реализовано** — вариант A (импорт после Push full) + вариант B (подсказки в UI/docs).  
> **Не реализовано:** вариант C (HA-бейдж в `manual_full`).

### Симптом (было)
В режиме `manual_full` (по умолчанию):
- `Push full` копирует файлы (PKI/WG/config) на replica, но **не создаёт `VpnConfig`** для replica
  и не проставляет `sync_group_id` конфигам primary
  (поля `sync_group_id`/`ha_primary_config_id` ставятся только в `client_sync.py`, т.е. в auto).
- `dissolve_sync_group` в этом режиме отвязывать нечего → вернёт `0/0`.
- После dissolve активируем replica → `_scoped_config_query` (группы нет) ищет `VpnConfig`
  по `node_id == replica.id` → **пусто**, хотя клиенты есть на диске replica.

Восстановление возможно вручную: **Конфигурации → Синхронизировать** (`/configs/sync`),
который как раз станет доступен (пока группа есть, `require_ha_primary_for_client_ops` его блокирует на replica).
Но это **не автоматически**.

Связанное следствие: HA-бейдж `_ha_info_for_config` показывается при `sync_group_id` у конфига.  
✅ **Вариант C:** в `manual_full` primary-конфиги получают `sync_group_id` (без теней на replica); бейдж и единый список primary работают как в `auto`.

### Варианты правки

**Вариант A (минимальный, рекомендуется для UX):** ✅ **внедрён**
В конце `run_push_full` (или в `dissolve_sync_group`) импортировать клиентов replica с диска в `VpnConfig`,
переиспользуя логику из `/configs/sync` (вынести её в сервис `import_clients_from_disk(db, node_id)`).
Тогда после Push full replica имеет полноценные записи в панели, и dissolve уже ничего не ломает.

Псевдокод нового сервиса (вынести общий код из `configs.py::sync_from_antizapret`):
```python
def import_clients_from_disk(db: Session, node: Node, owner_id: int) -> int:
    adapter = get_adapter_for_node(node)
    imported = 0
    for name in adapter.list_openvpn_clients():
        if not _exists(db, node.id, name, VpnType.openvpn):
            db.add(VpnConfig(node_id=node.id, client_name=name,
                             vpn_type=VpnType.openvpn, owner_id=owner_id,
                             cert_expire_days=resolve_openvpn_cert_days_remaining(adapter, name)))
            imported += 1
    for name in adapter.list_wireguard_clients():
        if not _exists(db, node.id, name, VpnType.wireguard):
            db.add(VpnConfig(node_id=node.id, client_name=name,
                             vpn_type=VpnType.wireguard, owner_id=owner_id))
            imported += 1
    db.commit()
    return imported
```
Вызвать после успешного restore каждой replica в `run_push_full`.

**Вариант B (без изменения данных, только честное UX):** ✅ **внедрён** (дополнение к A)
- На странице узлов/групп показать подсказку: «После расформирования на replica выполните
  Конфигурации → Синхронизировать, чтобы импортировать клиентов в панель».
- Поправить `docs/NodeSync.md`: HA-бейдж и авто-видимость работают только в `auto`.

**Вариант C (унификация):** ✅ **реализовано** (`node_sync/manual_link.py`)
В `manual_full` тоже помечать конфиги primary `sync_group_id` (без теней),
чтобы HA-бейдж работал единообразно. Тогда `dissolve` должен лишь снимать `sync_group_id`
с primary-конфигов, а импорт replica остаётся отдельной задачей (см. A).

---

## 4. Мелочь: мёртвая ветка `stray_replica_configs` в `dissolve.py`

> **Статус: ✅ реализовано** — фильтр `VpnConfig.node_id == group.primary_node_id`. Тесты: `test_dissolve_detaches_stray_replica_config`.

### Симптом (было)
```python
# backend/app/services/node_sync/dissolve.py
primary_configs = db.query(VpnConfig).filter(
    VpnConfig.sync_group_id == group.id,
    VpnConfig.ha_primary_config_id.is_(None),   # без фильтра по node_id → берёт всё
).all()
for config in primary_configs:
    config.sync_group_id = None
...
stray_replica_configs = db.query(VpnConfig).filter(
    VpnConfig.sync_group_id == group.id,        # уже сброшено выше → autoflush вернёт пусто
    VpnConfig.ha_primary_config_id.is_(None),
    VpnConfig.node_id != group.primary_node_id,
).all()
```
Первый запрос уже забрал все конфиги группы с `ha_primary_config_id IS NULL` (включая не-primary)
и сбросил им `sync_group_id`. Поэтому `stray_replica_configs` после autoflush пуст — ветка не работает.
Плюс `primary_configs_detached` считает и не-primary конфиги → статистика вводит в заблуждение.

### Предлагаемая правка ✅ **внедрена** (первый вариант)
- Ограничить первый запрос `VpnConfig.node_id == group.primary_node_id` (тогда stray-ветка
  действительно отработает для «осиротевших» replica-конфигов и счётчики станут точными);
- ~~Либо удалить ветку `stray_replica_configs` как недостижимую и переименовать счётчик.~~

Пример (точные счётчики):
```python
primary_configs = db.query(VpnConfig).filter(
    VpnConfig.sync_group_id == group.id,
    VpnConfig.ha_primary_config_id.is_(None),
    VpnConfig.node_id == group.primary_node_id,   # <— добавить
).all()
```

---

## 5. Мелочь: Verify не обрабатывает offline primary

> **Статус: ✅ реализовано** — `ready: false`, summary «primary offline или не найден». Тесты: `test_node_sync_verify.py`.

### Симптом (было)
```python
# backend/app/services/node_sync/verify.py
primary_adapter = get_adapter_for_node(db.get(Node, group.primary_node_id))
primary_ovpn = set(primary_adapter.list_openvpn_clients())   # упадёт, если primary offline
```
Для replica есть аккуратная проверка `node.status == online` и graceful-mismatch, для primary — нет.
Если primary offline (но не удалён) — сетевые вызовы бросят исключение, не перехваченное в функции →
Verify 500, reconcile-проход прерывается.

### Предлагаемая правка ✅ **внедрена**
До чтения primary проверить наличие узла и статус, вернуть `ready=False` с понятной причиной:
```python
primary_node = db.get(Node, group.primary_node_id)
if not primary_node or primary_node.status != NodeStatus.online:
    result = {
        "ready": False,
        "shared_domain": group.shared_domain,
        "primary_node_id": group.primary_node_id,
        "replicas": [],
        "summary": "primary offline или не найден",
    }
    group.last_verify_at = datetime.utcnow()
    group.last_verify_result = json.dumps(result, ensure_ascii=False)
    db.commit()
    return result
```

---

## 6. Наблюдение: частичный сбой auto-sync (split-brain)

> **Статус: ✅ реализовано** — `log_action("ha_replicate_partial_failure")` в `client_sync.py` (при `audit_log_enabled`).  
> Ограничение split-brain по-прежнему документировано в `docs/NodeSync.md`; логика репликации не менялась.

В `replicate_client_create` при ошибке на части реплик `primary_config` всё равно получает
`sync_group_id`, ставится `sync_status=failed`; клиент создан на primary и части реплик.
Восстановление — повторный Push full. Это **документировано** в `docs/NodeSync.md`
как ограничение split-brain. ~~Отдельная правка не обязательна; при желании —
добавить admin-уведомление о частичном сбое прямо из `replicate_client_create`.~~ ✅ **добавлено** (action log).

---

## 7. Вкладки панели после расформирования HA

> **Статус:** справочный раздел. Часть наблюдений **закрыта правкой #3**; остальное — ожидаемое поведение или **отдельные задачи** (см. таблицу ниже).

Проверка: как разделы панели ведут себя после `delete_sync_group` → `dissolve_sync_group` + удаление
`NodeSyncGroup`. Ниже — ожидаемое поведение, нюансы и актуальный статус после внедрения правок.

### Общее сразу после dissolve

| Эффект | Почему |
|--------|--------|
| HA-баннер «replica — только просмотр» исчезает | `activeNodeHa` снова `null` (`NodeContext` → `GET /nodes/active`) |
| Кнопки create/delete/block снова активны на любом узле | `useHaReplicaReadonly()` → `false` |
| Синхронизация между узлами прекращается | группа удалена, `maybe_replicate_*` не вызывается |
| HA-бейджи на карточках клиентов пропадают | `_ha_info_for_config` смотрит на `sync_group_id`, после dissolve он `null` |

Узлы становятся **независимыми**: каждая вкладка смотрит на **активный узел** (или на все узлы в
федеративном мониторинге), без HA-агрегации.

### По вкладкам

#### Конфигурации / Dashboard

**Режим `auto`:** теневые конфиги replica становятся самостоятельными (`ha_primary_config_id = null`).
При переключении активного узла список показывает только клиентов **этого** узла — корректно для
независимых нод.

**Режим `manual_full` (по умолчанию):** ~~на replica в БД часто **нет** `VpnConfig`~~  
После **Push full** клиенты импортируются в `VpnConfig` на replica (#3, вариант A) → после dissolve вкладка **не пустая**, если Push full выполнялся.  
Fallback: **Конфигурации → Синхронизировать** (`POST /configs/sync`) — если Push full не делали или нужен повторный импорт.

Во время HA при активном replica список показывал конфиги **primary** (`_scoped_config_query` в
`configs.py`). После dissolve на том же активном replica список **резко сужается** — не баг dissolve,
а смена логики отображения.

#### Мониторинг

- **Все узлы** (`scope=all`): HA-дедупликация (`_build_ha_monitoring_lookup` в `monitoring_overview.py`)
  перестаёт работать → один клиент на двух нодах может отображаться **дважды** (если подключён к обоим
  IP). Для независимых нод это ожидаемо.
- **Активный узел:** данные с адаптера активной ноды — корректно.
- Сводка по нодам, ресурсы, сравнение — без HA-логики, по `node_id` — корректно.

#### Трафик

Всё привязано к **активному узлу** (`get_active_node` в `routers/traffic.py`): overview, chart,
active-clients, never-connected, deleted-clients.

`never-connected` берёт конфиги с `ha_primary_config_id IS NULL` на текущем `node_id`
(`traffic/maintenance.py`). После dissolve в **auto** — ок. В **manual_full** на replica — ✅ после Push full
есть `VpnConfig` и снимок трафика (`collect_traffic_snapshot_for_node`).

Исторические счётчики (`UserTrafficStatProtocol` и др.) остаются **по каждому узлу отдельно** — при
переключении узла данные свои; это правильно.

#### Политики доступа (блокировки, лимиты)

Политики в БД: `OpenVpnAccessPolicy` / `WgAccessPolicy` с полем `node_id`. Dissolve **не копирует**
политики с primary на replica.

После dissolve:
- на **primary** — как было;
- на **replica** — только записи для `node_id` replica (часто пусто, даже если клиенты на диске есть).

После Push full блоки на диске могли совпасть, а в панели на replica — нет.  
✅ **Исправлено:** политики копируются с primary при Push full (`copy_access_policies_from_node`).

**Узлы → сводка политик** (`policy-summary-by-node`) — по каждой ноде отдельно, корректно.

#### Warper, Routing, Server Monitor, Edit Files, Antizapret Config

Работают через `get_active_node` + адаптер, без HA-логики. После dissolve: переключили активный узел
→ данные с него. Корректно.

#### Теги конфигов, шаблоны клиентов

Привязаны к `node_id` активного узла. После dissolve — свои теги/шаблоны на каждой ноде (общих между
нодами не будет). Корректно для независимых нод.

#### Логи

- **Журнал действий** — глобальный, HA не влияет.
- **Логи OpenVPN/AntiZapret** — с активного узла. После dissolve — с выбранного узла. Корректно.

#### Telegram / self-service (роль `user`)

Квота считает конфиги **по всем узлам**, исключая только тени (`ha_primary_config_id IS NULL`):

```python
# backend/app/services/self_service.py — count_user_configs
.filter(VpnConfig.owner_id == user_id, VpnConfig.ha_primary_config_id.is_(None))
```

После dissolve в **auto** один и тот же клиент на primary и replica — **две записи** в БД.  
✅ **Исправлено:** `count_user_configs` считает уникальные пары `(client_name, vpn_type)` — квота не удваивается.

### Сводная таблица (актуально после правок)

| Вкладка | После dissolve (`auto`) | После dissolve (`manual_full`) | Статус |
|---------|-------------------------|--------------------------------|--------|
| Конфигурации | OK, свои клиенты на каждой ноде | OK, если был Push full (#3); иначе Sync | ✅ #3 закрывает |
| Dashboard | OK | То же | ✅ #3 закрывает |
| Мониторинг (все узлы) | OK, без HA-дедупа | OK | ✅ ожидаемо |
| Трафик | OK на каждой ноде | OK после Push full (снимок + VpnConfig) | ✅ |
| Политики / блокировки | Свои на каждой ноде | Копируются с primary при Push full | ✅ |
| Warper / Routing / Monitor / Files | OK по активному узлу | OK | ✅ ожидаемо |
| Узлы | OK, группы нет | OK | ✅ ожидаемо |
| Логи | OK | OK | ✅ ожидаемо |
| Квота user | Dedupe по client+type | То же | ✅ |

### Вывод по вкладкам (актуально)

После расформирования узлы **несгруппированы**, синхронизации нет, вкладки смотрят на активный узел.
**«Корректно» ≠ «как было в HA»:**

1. **`manual_full` / Конфигурации** — ✅ закрыто #3 (импорт после Push full).
2. **`manual_full` / Трафик** — ✅ после Push full снимок трафика с replica (`collect_traffic_snapshot_for_node`).
3. **Политики** — ✅ копируются с primary на replica при Push full (`copy_access_policies_from_node`).
4. **Мониторинг (все узлы)** — ✅ дубликаты подключений — ожидаемо для независимых нод.
5. **Квота user** — ✅ dedupe по `(client_name, vpn_type)` в `count_user_configs`.

Связь с пунктом **#3**: вариант A (`import_clients_from_disk` после Push full) закрывает пустые **Конфигурации** на replica в `manual_full`; политики, трафик-статистика и квота — отдельные задачи.

---

## Сводка: что реализовано, что нет

| Пункт | Статус |
|-------|--------|
| #1 вариант A — запрет delete в HA | ✅ |
| #1 вариант B — авто-dissolve перед delete | ❌ |
| #2 `purge_node_related` в `delete_node` | ✅ |
| #2 `PRAGMA foreign_keys=ON` в SQLite | ❌ (отдельная задача) |
| #3 вариант A — `import_clients_from_disk` после Push full | ✅ |
| #3 вариант B — подсказки UI + `docs/NodeSync.md` | ✅ |
| #3 вариант C — HA-бейдж в `manual_full` | ✅ |
| #4 фильтр `node_id` в `dissolve.py` | ✅ |
| #5 graceful offline primary в Verify | ✅ |
| #6 action log при частичном сбое репликации | ✅ |
| #7 трафик на replica после dissolve | ✅ | `collect_traffic_snapshot_for_node` после Push full |
| #7 политики на replica | ✅ | `copy_access_policies_from_node` после Push full |
| #7 двойной счёт квоты user | ✅ | `count_user_configs` — dedupe по `(client_name, vpn_type)` |

---

## Рекомендуемый порядок внедрения ✅ **выполнен**

1. **#1** (запрет удаления узла в группе) — ✅
2. **#2** (очистка данных при удалении узла) — ✅
3. **#3** (видимость клиентов replica после dissolve) — ✅ вариант A + B
4. **#5** (graceful offline primary в Verify) — ✅
5. **#4** (чистка `dissolve.py`) — ✅
6. **#6** — ✅ (action log)
7. **#7** (трафик, политики, квота) — ✅ (2026-06-19)

Детали реализации и чеклист: [HA-node-fix-plan.md](./HA-node-fix-plan.md).
