# HA Auto-Sync: план доработок

Документ описывает **разрыв между текущим поведением `sync_mode=auto` и ожидаемым**: любое изменение на **primary** должно автоматически попадать на **replica** (как при создании/удалении клиента).

Статус: **реализовано (этапы A–E + remaining §1–§5)** — backend + unit/integration-тесты + docs + UI. **Live E2E sign-off** на staging — единственный открытый хвост (integration-proxy ✅ 2026-06-19).

**Легенда:** ✅ готово · ⚠️ частично / fallback · ❌ не сделано

**Шаги и промпты:** [HA-auto-sync-remaining.md](./HA-auto-sync-remaining.md) (закрыт, кроме live E2E) · сводка: этот файл

---

## 1. Цель

При активной HA-группе с `sync_mode=auto` администратор работает **только с primary**. Все перечисленные ниже операции должны **синхронно или асинхронно** отражаться на всех replica без ручного Push full.

**Не цель этого этапа:**

- Автоматическая синхронизация **ручных правок по SSH** на сервере (вне панели).
- Замена Push full как механизма **первичного выравнивания** после создания группы или смены primary.
- Синхронизация **node-specific** файлов (например `warper-include-ips.txt` на одной replica) — они остаются локальными.

---

## 2. Текущее состояние (`auto` сегодня)

| Что | Статус | Где в коде |
|-----|--------|------------|
| Создание VPN-клиента на primary | ✅ | `client_sync.maybe_replicate_create` ← `configs.create_config`, CSV import (+ опц. политики) |
| Удаление VPN-клиента на primary | ✅ | `client_sync.maybe_replicate_delete` ← `configs.delete_config`, bulk delete |
| Блокировки, лимиты трафика, срок WG | ✅ | `policy_sync` ← `routers/client_access.py` |
| Обновление cert (PATCH config) | ✅ | `maybe_replicate_cert_renew`, `maybe_replicate_config_metadata` ← `configs.update_config` |
| Массовые операции (block/renew/delete) | ✅ | `bulk_config_ops` — delete + block/renew через `policy_sync` |
| Шаблоны клиентов | ✅ | `client_templates.apply_template` — create + `maybe_replicate_policy_op` |
| Списки доменов/IP (Настройки) | ✅ | `config_sync.maybe_replicate_config_files` ← `routers/settings.py` |
| Редактор файлов (save/batch) | ✅ | `config_sync` ← `routers/edit_files.py` |
| Перенос файлов между узлами | ⚠️ fallback | auto через `config_sync`; кнопка «Перенести на узлы» — ручной путь (`edit_files_transfer`) |
| Настройки AntiZapret (`setup`) | ✅ | `antizapret_sync.replicate_antizapret_settings` ← `PUT /antizapret-settings` |
| Применение маршрутизации (`doall.sh`) | ✅ | `enqueue_ha_routing_apply_replicas` ← `POST /routing/apply` |
| CIDR providers (compile/deploy) | ✅ | `provider_sync` ← `PUT providers`, `POST /routing/sync` |
| Политика узла по умолчанию | ✅ | `maybe_replicate_node_default_policy` ← `client_access.update_node_defaults` |
| OpenVPN disconnect | ✅ | `client_ops_sync.maybe_replicate_openvpn_disconnect` ← `client_access.openvpn_disconnect` |
| Route files (Routing UI `PUT /files/{key}`) | ✅ | `config_sync.maybe_replicate_config_files` ← `routers/routing.py` |
| Reconcile при drift | ✅ opt-in | `reconcile_worker` — Verify + incremental heal (`NODE_SYNC_AUTO_HEAL`) |
| Push full | ✅ вручную | `push_full.run_push_full` — bootstrap / disaster recovery |

**Итог:** `auto` = create/delete + политики + config files + route files + setup/apply + CIDR + disconnect + node defaults + opt-in auto-heal. Исключения: node-local WARP/warper (`CONFIG_FINGERPRINT_EXCLUDE`).

---

## 3. Целевое поведение

### 3.1. VPN-клиенты и политики доступа

| Операция | Ожидание на replica | Статус |
|----------|---------------------|--------|
| Create / delete client | Уже есть: OVPN cert / WG peer + shadow `VpnConfig` | ✅ |
| Renew OpenVPN cert | Тот же `client_name`, новый срок на всех replica | ✅ |
| Temp / permanent block, unblock | Та же политика в БД + runtime (iptables/WG) на replica | ✅ |
| Set / clear traffic limit | Те же `traffic_limit_*` + reconcile runtime | ✅ |
| WG set-expiry | Тот же `expires_at` + runtime | ✅ |
| OpenVPN disconnect | Разорвать сессию на primary **и** replica (если клиент онлайн) | ✅ |
| PATCH: description, owner | Обновить shadow `VpnConfig` на replica (метаданные панели) | ✅ |
| Bulk: block, renew, unblock | То же, что одиночные операции | ✅ |
| CSV import / template apply | Create + политики (лимит, block) + HA-репликация | ✅ |

**Принцип:** primary — источник истины для **логического клиента**; на replica — **теневой** `VpnConfig` (`ha_primary_config_id`) с тем же `client_name`.

### 3.2. Файлы AntiZapret (`/root/antizapret/config/`)

| Операция | Ожидание на replica | Статус |
|----------|---------------------|--------|
| Сохранение в «Настройках» (5 списков) | Записать те же файлы + `doall.sh` на replica | ✅ |
| Редактор файлов (один / batch) | Записать изменённые файлы + опционально `doall.sh` | ✅ |
| Изменения через Routing UI (route files) | Аналогично редактору (`config_sync`, без doall по умолчанию) | ✅ |

**Исключения из паритета (не копировать, не перезаписывать на replica):**

- `warper-include-ips.txt` и другие node-specific файлы из `CONFIG_FINGERPRINT_EXCLUDE` (`fingerprints.py`).

### 3.3. Конфигурация AntiZapret (`setup`, флаги)

| Операция | Ожидание на replica | Статус |
|----------|---------------------|--------|
| `PUT /routing/antizapret-settings` | Те же ключи в `setup` на replica | ✅ |
| `POST /routing/apply` | После сохранения — `sync + doall.sh` на всех replica (или общий orchestrated apply) | ✅ |

**Важно:** `OPENVPN_HOST` / `WIREGUARD_HOST` реплицируются (общий `shared_domain` в профилях). Node-specific: только WARP-флаги (`ANTIZAPRET_WARP`, `VPN_WARP`); warper slave — отдельно (файлы/config). См. §5.3.

### 3.4. CIDR / providers

| Операция | Ожидание | Статус |
|----------|----------|--------|
| Ручное редактирование provider file | Реплицировать файл `AP-*-include-ips.txt` | ✅ |
| `POST /routing/sync` (compile) | Compile на primary; deploy скомпилированных файлов на replica | ✅ |
| Deploy из CIDR DB | HA-replica в targets при auto через `deploy_compiled_providers_to_replicas` | ✅ (явный HA-path; default `resolve_deploy_targets` — только active node) |

### 3.5. Политика узла по умолчанию

| Операция | Ожидание | Статус |
|----------|----------|--------|
| `PUT /client-access/node-defaults/{primary_id}` | Скопировать defaults на replica **или** явно запретить редактирование defaults на replica (только primary) | ✅ репликация с primary-only guard |

Рекомендация: **реплицировать только если `node_id == primary_node_id`** группы; для replica node_id — 403.

---

## 4. Предлагаемая архитектура

### 4.1. Единая точка входа ✅

Реализовано: `backend/app/services/node_sync/replicate.py`:

```text
replicate_to_replicas(db, group, operation, payload) -> ReplicateResult
```

- Проверка `is_auto_sync_enabled(group)`.
- Итерация `get_replica_nodes(db, group)`.
- Частичный сбой → `sync_status=failed`, audit log (как в `client_sync`).
- Успех → опционально точечный Verify (fingerprint только затронутых путей).

**Не дублировать** логику в каждом роутере: роутеры вызывают один helper после успеха на primary.

### 4.2. Типы операций (enum / registry) ✅

| `operation` | Действие на replica | Статус |
|-------------|---------------------|--------|
| `client_create` | уже есть | ✅ |
| `client_delete` | уже есть | ✅ |
| `client_renew_cert` | `adapter.add_openvpn_client(name, days)` | ✅ |
| `policy_apply` | `AccessPolicyService` на replica с тем же `client_name` | ✅ |
| `policy_copy_all` | `copy_access_policies_from_node` (уже есть для Push full) | ✅ (Push full + heal) |
| `config_files_write` | `write_config_file` + `apply_config_changes` | ✅ |
| `antizapret_settings_patch` | `update_antizapret_settings` | ✅ |
| `routing_apply` | фоновая задача apply на replica | ✅ |
| `cidr_deploy_files` | существующий deploy path | ✅ |

### 4.3. Резолв shadow-клиента ✅

Реализовано: `get_shadow_configs` в `replicate.py`.

```text
primary VpnConfig.id → VpnConfig на replica WHERE ha_primary_config_id = primary.id
```

Если shadow нет (рассинхрон после сбоя) — **не создавать молча**: записать ошибку, `sync_status=failed`, предложить Push full.

Helper: `get_shadow_configs(db, group, primary_config) -> list[VpnConfig]`.

### 4.4. Репликация файлов конфигурации ✅

Реализовано: `config_sync.py` → `edit_files_transfer.run_edit_files_transfer`.

- После `save_edit_file` / `save_batch` / `settings.patch` на primary — вызвать transfer на **replica группы** с `run_doall=True` (если на primary был doall).
- `target_node_ids` = replica ids из группы, не «все online».
- Не трогать excluded files при **чтении diff**; при full-directory push — merge, не delete warper на replica.

### 4.5. Синхронность vs фон

| Класс | Режим | Причина |
|-------|-------|---------|
| Block/unblock, traffic limit | **Синхронно** в API-запросе | Админ ожидает немедленный эффект при failover |
| `doall.sh`, routing apply | **Фоновая задача** на каждой replica | Долго, уже есть task infrastructure |
| Batch import 100+ клиентов | **Очередь** | Как CSV import сейчас |
| Мелкие файлы config | Синхронно или фон — **настройка** | Default: синхронно до 30s timeout |

### 4.6. Reconcile worker (v2) ✅

Реализовано в `reconcile_worker.py` (opt-in `NODE_SYNC_AUTO_HEAL`):

1. Drift detected → попытка **incremental heal** (не full push).
2. Если heal неудачен N раз → notify + оставить `failed`.
3. **Никогда** auto Push full без явного флага (destructive).

---

## 5. Детальный бэклог по файлам

### 5.1. Backend — новые / расширить

| Файл | Задача | Статус |
|------|--------|--------|
| `node_sync/replicate.py` | Центральный диспетчер операций | ✅ |
| `node_sync/policy_sync.py` | `replicate_policy_op(primary_config, op, **kwargs)` | ✅ |
| `node_sync/config_sync.py` | Обёртка над file transfer для HA-группы | ✅ |
| `node_sync/antizapret_sync.py` | Репликация setup + apply | ✅ |
| `node_sync/provider_sync.py` | CIDR provider files + deploy после compile | ✅ |
| `node_sync/groups.py` | `get_sync_group_for_primary_or_raise`, HA guards | ✅ (`iter_replica_adapters` — в `replicate.py`) |
| `node_sync/client_ops_sync.py` | `maybe_replicate_openvpn_disconnect` | ✅ |
| `policy_import.py` | Добавить `copy_single_client_policy(source, target, client_name)` | ✅ |
| `client_sync.py` | Вынести общую обработку ошибок в replicate helper | ✅ |

### 5.2. Backend — точки встраивания (хуки)

| Файл / endpoint | Вызов после успеха на primary | Статус |
|-----------------|--------------------------------|--------|
| `routers/client_access.py` — все POST block/unblock/limit/expiry | `replicate_policy_op` | ✅ |
| `routers/configs.py` — PATCH cert, description/owner | renew + metadata sync | ✅ |
| `routers/configs.py` — bulk endpoints | по операции | ✅ |
| `routers/settings.py` — PATCH lists | `config_sync.replicate_files([...])` | ✅ |
| `routers/edit_files.py` — PUT, POST batch | `config_sync.replicate_files` | ✅ |
| `routers/routing.py` — PUT settings, POST apply | `antizapret_sync` | ✅ |
| `routers/routing.py` — providers, sync | `provider_sync` | ✅ |
| `routers/routing.py` — PUT `/files/{file_key}` | `config_sync.maybe_replicate_config_files` | ✅ |
| `services/client_templates.py` | после create — policies + replicate | ✅ |
| `services/config_csv_ops.py` | после create — policies + `maybe_replicate_policy_op` | ✅ |
| `services/bulk_config_ops.py` | block/renew/unblock | ✅ |
| `services/access_policy.py` | не менять ядро; вызывать с `node_id=replica` из policy_sync | ✅ |

### 5.3. Конфигурация и исключения ✅

- `fingerprints.CONFIG_FINGERPRINT_EXCLUDE` — документированный список HA-local files ✅
- `ANTIZAPRET_HA_SETTING_EXCLUDE` + `filter_ha_replicable_settings()` в `antizapret_params.py` ✅
- `openvpn_host` / `wireguard_host` — в scope репликации ✅
- Настройки в `config.py` ✅:
  - `NODE_SYNC_AUTO_REPLICATE_CONFIG_FILES` (default `true`)
  - `NODE_SYNC_AUTO_REPLICATE_POLICIES` (default `true`)
  - `NODE_SYNC_AUTO_HEAL` (default `false`)
  - `NODE_SYNC_REPLICATE_DOALL` (default `true`)
  - `NODE_SYNC_AUTO_HEAL_MAX_FAILURES` (default `3`)

### 5.4. Frontend

| Компонент | Задача | Статус |
|-----------|--------|--------|
| `NodeSyncGroupSection.tsx` | Обновить описание режима Auto: полный список того, что синхронизируется | ✅ |
| Уведомления | Toast при partial failure репликации («клиент заблокирован на primary, ошибка на replica X») | ✅ warning при `sync_status=failed` |
| HA badge / sync_status | Показывать детали последней ошибки репликации (не только Verify) | ✅ `last_sync_error` под badge |
| Редактор файлов | Убрать/пометить ручной «Перенос на узлы» как fallback, не основной путь в HA | ✅ `EditFilesPage.tsx` |

### 5.5. Документация ✅

| Файл | Задача | Статус |
|------|--------|--------|
| `docs/NodeSync.md` | Переписать секцию v2: что делает `auto` после доработки | ✅ |
| `docs/edit-files.md` | HA: auto-replicate vs manual transfer | ✅ |
| `docs/antizapret-config.md` | Исключения node-specific | ✅ |
| `CHANGELOG.md` | Запись при релизе | ✅ `[Unreleased]` |

---

## 6. Этапы реализации

### Этап A — Политики клиента (высокий приоритет) ✅

1. `policy_sync.py` + тесты на block/unblock/limit/expiry. ✅
2. Хуки в `client_access.py`. ✅
3. `bulk_config_ops` block/renew. ✅
4. PATCH cert + shadow metadata. ✅

**Критерий готовности:** блокировка и лимит на primary → тот же статус на replica без Push full. ✅

### Этап B — Файлы config (высокий приоритет) ✅

1. `config_sync.py` обёртка над `edit_files_transfer`. ✅
2. Хуки: `settings.py`, `edit_files.py`. ✅
3. Учёт `CONFIG_FINGERPRINT_EXCLUDE` при записи. ✅

**Критерий:** правка `include-hosts.txt` на primary → Verify `antizapret/config` совпадает (кроме excluded). ✅

### Этап C — AntiZapret setup + apply ✅

1. Whitelist ключей setup для HA. ✅ (`filter_ha_replicable_settings`)
2. Репликация `PUT antizapret-settings`. ✅
3. Цепочка: save → replicate setup → enqueue apply на каждой replica. ✅

**Критерий:** смена флага на primary → после apply одинаковое поведение на failover. ✅ (unit/integration)

### Этап D — CIDR / providers ✅

1. Аудит `resolve_deploy_targets` для HA. ✅ (`test_cidr_ha_deploy_targets.py` — default active-only; HA через `provider_sync`)
2. Репликация ручных правок provider files. ✅
3. Sync compile → deploy на все replica группы. ✅

### Этап E — Reconcile auto-heal (низкий приоритет) ✅

1. Incremental heal по типу drift (fingerprint vs clients vs policies). ✅
2. Admin notify с actionable hint. ✅ (`NODE_SYNC_AUTO_HEAL_MAX_FAILURES`)

### Этап F — Push full остаётся ✅

- Первичное выравнивание.
- Восстановление после split-brain.
- Смена состава группы / переезд primary.

---

## 7. Тестирование

### Unit ✅

- `policy_sync`: каждая операция, partial failure, нет shadow. ✅ `test_node_sync_policy_sync.py`
- `config_sync`: excluded files не перезаписываются. ✅ `test_node_sync_config_sync.py`
- `antizapret_sync`: excluded setup keys. ✅ `test_node_sync_antizapret_sync.py`, `test_antizapret_ha_settings.py`
- `provider_sync`, `replicate`, reconcile auto-heal. ✅

### Integration ✅

- `auto_group_db` fixture: операция на primary → assert adapter calls на replica (mocks). ✅
- Fingerprint match после file sync. ✅ (частично через config hooks tests)

### E2E / manual checklist ⚠️ — **live sign-off открыт** (integration-proxy ✅ 2026-06-19)

**Окружение:** dev workspace, API не поднят, второй VPN-узел отсутствует. Прогон через pytest fixtures (`sync_mode=auto`, mock adapters): **103 passed** (2026-06-19).

| # | Сценарий | Integration | Live E2E |
|---|----------|:-----------:|:--------:|
| 1 | Create OVPN + WG → peer/cert на replica | [x] | [ ] |
| 2 | Block temp → клиент не подключается после failover | [x]† | [ ] |
| 3 | Traffic limit → блок на обоих узлах | [x] | [ ] |
| 4 | `include-hosts.txt` → Verify green | [x] | [ ] |
| 5 | `warper-include-ips.txt` только на replica → Verify green | [x] | [ ] |
| 6 | Partial replica offline → `sync_status=failed`, primary OK | [x] | [ ] |
| 7 | Push full после рассинхрона → heal | [x]† | [ ] |
| 8 | Route file `include_ips` через Routing UI | [x] | [ ] |
| 9 | OpenVPN disconnect на обоих узлах | [x] | [ ] |

† `block_temp` — тот же код path, что `block_permanent` в тестах; Push full verify — mock `ready=True`.

Детали по пунктам, API/fixtures и блокеры: [HA-auto-sync-remaining.md §4](./HA-auto-sync-remaining.md#4-e2e--manual-checklist).

---

## 8. Риски и решения

| Риск | Митигация |
|------|-----------|
| `doall.sh` 5+ мин на 3 replica | Фоновые задачи + progress в UI |
| Split-brain (успех primary, fail replica) | Уже есть `sync_status=failed`; не откатывать primary |
| Node-specific WARP перезаписан | `ANTIZAPRET_HA_SETTING_EXCLUDE`; warper slave — `CONFIG_FINGERPRINT_EXCLUDE` + merge |
| Ручные правки по SSH | Reconcile drift + документация «только через primary» |
| Разные версии AntiZapret | Существующий preflight в `validate_sync_group_payload` |
| Cert index.txt race при параллельном renew | Сериализовать PKI-операции на группу (lock) |

---

## 9. Решения (зафиксировано) ✅

Детали реализации — `docs/NodeSync.md`, `CHANGELOG.md` `[Unreleased]`.

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | Owner/description на shadow | PATCH metadata на primary → обновить все shadow; guard primary-only для PATCH |
| 2 | Node default policy | Редактирование только на primary; в `auto` — репликация на replica |
| 3 | Traffic counters | Паритет лимита/блока (policy row + `AccessPolicyService`); consumed bytes — per node |
| 4 | Auto-heal | Opt-in (`NODE_SYNC_AUTO_HEAL=false`); без auto Push full |
| 5 | `manual_full` | Без auto-хуков; только Push full |
| 6 | `OPENVPN_HOST` / `WIREGUARD_HOST` | **Реплицируются** (shared domain); exclude только WARP-флаги |

---

## 10. Краткая сводка для продукта

**Было:** `auto` = create/delete клиентов.

**Сейчас:** `auto` = create/delete + политики + config/route files + setup/apply + CIDR + OpenVPN disconnect + node defaults + CSV policies + opt-in auto-heal.

**Осталось:** live E2E sign-off на staging (2 VPN-узла) — см. [§7](./HA-auto-sync-roadmap.md#7-тестирование) и [remaining §4](./HA-auto-sync-remaining.md#4-e2e--manual-checklist).

**Push full** остаётся для bootstrap и disaster recovery, но не для каждой правки `include-hosts.txt`.
