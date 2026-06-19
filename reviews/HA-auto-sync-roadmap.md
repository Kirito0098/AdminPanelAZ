# HA Auto-Sync: план доработок

Документ описывает **разрыв между текущим поведением `sync_mode=auto` и ожидаемым**: любое изменение на **primary** должно автоматически попадать на **replica** (как при создании/удалении клиента).

Статус: **черновик / бэклог** — реализация не начата.

---

## 1. Цель

При активной HA-группе с `sync_mode=auto` администратор работает **только с primary**. Все перечисленные ниже операции должны **синхронно или асинхронно** отражаться на всех replica без ручного Push full.

**Не цель этого этапа:**

- Автоматическая синхронизация **ручных правок по SSH** на сервере (вне панели).
- Замена Push full как механизма **первичного выравнивания** после создания группы или смены primary.
- Синхронизация **node-specific** файлов (например `warper-include-ips.txt` на одной replica) — они остаются локальными.

---

## 2. Текущее состояние (`auto` сегодня)

| Что | Реализовано | Где в коде |
|-----|-------------|------------|
| Создание VPN-клиента на primary | ✅ | `client_sync.maybe_replicate_create` ← `configs.create_config`, CSV import |
| Удаление VPN-клиента на primary | ✅ | `client_sync.maybe_replicate_delete` ← `configs.delete_config`, bulk delete |
| Блокировки, лимиты трафика, срок WG | ❌ | `routers/client_access.py` → только `AccessPolicyService` на active node |
| Обновление cert (PATCH config) | ❌ | `configs.update_config` — только primary adapter |
| Массовые операции (block/renew/delete) | ❌ частично | `bulk_config_ops` — delete реплицирует, block/renew — нет |
| Шаблоны клиентов | ❌ | `client_templates.apply_template` — create без полной репликации политик |
| Списки доменов/IP (Настройки) | ❌ | `routers/settings.py` → `get_active_adapter` |
| Редактор файлов (save/batch) | ❌ | `routers/edit_files.py` |
| Перенос файлов между узлами | ⚠️ вручную | `edit_files_transfer.run_edit_files_transfer` — отдельная кнопка/API |
| Настройки AntiZapret (`setup`) | ❌ | `routers/routing.py` `PUT /antizapret-settings` |
| Применение маршрутизации (`doall.sh`) | ❌ | `POST /routing/apply` — только active node |
| CIDR providers (compile/deploy) | ❌ | `routers/routing.py`, CIDR pipeline |
| Политика узла по умолчанию | ❌ | `client_access.update_node_defaults` |
| Reconcile при drift | ⚠️ только алерт | `reconcile_worker.py` — Verify + `sync_status=failed`, **без auto-fix** |
| Push full | ✅ вручную | `push_full.run_push_full` — полный backup/restore + import policies |

**Итог:** `auto` сейчас = **репликация жизненного цикла клиента (create/delete)**. Всё остальное требует Push full или ручного переноса.

---

## 3. Целевое поведение

### 3.1. VPN-клиенты и политики доступа

| Операция | Ожидание на replica |
|----------|---------------------|
| Create / delete client | Уже есть: OVPN cert / WG peer + shadow `VpnConfig` |
| Renew OpenVPN cert | Тот же `client_name`, новый срок на всех replica |
| Temp / permanent block, unblock | Та же политика в БД + runtime (iptables/WG) на replica |
| Set / clear traffic limit | Те же `traffic_limit_*` + reconcile runtime |
| WG set-expiry | Тот же `expires_at` + runtime |
| OpenVPN disconnect | Разорвать сессию на primary **и** replica (если клиент онлайн) |
| PATCH: description, owner | Обновить shadow `VpnConfig` на replica (метаданные панели) |
| Bulk: block, renew, unblock | То же, что одиночные операции |
| CSV import / template apply | Create + политики, как при ручном create |

**Принцип:** primary — источник истины для **логического клиента**; на replica — **теневой** `VpnConfig` (`ha_primary_config_id`) с тем же `client_name`.

### 3.2. Файлы AntiZapret (`/root/antizapret/config/`)

| Операция | Ожидание на replica |
|----------|---------------------|
| Сохранение в «Настройках» (5 списков) | Записать те же файлы + `doall.sh` на replica |
| Редактор файлов (один / batch) | Записать изменённые файлы + опционально `doall.sh` |
| Изменения через Routing UI (route files) | Аналогично, если файл в scope HA |

**Исключения из паритета (не копировать, не перезаписывать на replica):**

- `warper-include-ips.txt` и другие node-specific файлы из `CONFIG_FINGERPRINT_EXCLUDE` (`fingerprints.py`).

### 3.3. Конфигурация AntiZapret (`setup`, флаги)

| Операция | Ожидание на replica |
|----------|---------------------|
| `PUT /routing/antizapret-settings` | Те же ключи в `setup` на replica |
| `POST /routing/apply` | После сохранения — `sync + doall.sh` на всех replica (или общий orchestrated apply) |

**Важно:** часть флагов может быть node-specific (AZ-WARP, slave). Нужен **whitelist/blacklist** ключей для HA-replicate (см. §5.3).

### 3.4. CIDR / providers

| Операция | Ожидание |
|----------|----------|
| Ручное редактирование provider file | Реплицировать файл `AP-*-include-ips.txt` |
| `POST /routing/sync` (compile) | Compile на primary; deploy скомпилированных файлов на replica |
| Deploy из CIDR DB | Уже multi-node через `resolve_deploy_targets` — **проверить**, что HA-replica всегда в targets при auto |

### 3.5. Политика узла по умолчанию

| Операция | Ожидание |
|----------|----------|
| `PUT /client-access/node-defaults/{primary_id}` | Скопировать defaults на replica **или** явно запретить редактирование defaults на replica (только primary) |

Рекомендация: **реплицировать только если `node_id == primary_node_id`** группы; для replica node_id — 403.

---

## 4. Предлагаемая архитектура

### 4.1. Единая точка входа

Новый модуль, например `backend/app/services/node_sync/replicate.py`:

```text
replicate_to_replicas(db, group, operation, payload) -> ReplicateResult
```

- Проверка `is_auto_sync_enabled(group)`.
- Итерация `get_replica_nodes(db, group)`.
- Частичный сбой → `sync_status=failed`, audit log (как в `client_sync`).
- Успех → опционально точечный Verify (fingerprint только затронутых путей).

**Не дублировать** логику в каждом роутере: роутеры вызывают один helper после успеха на primary.

### 4.2. Типы операций (enum / registry)

| `operation` | Действие на replica |
|-------------|---------------------|
| `client_create` | уже есть |
| `client_delete` | уже есть |
| `client_renew_cert` | `adapter.add_openvpn_client(name, days)` |
| `policy_apply` | `AccessPolicyService` на replica с тем же `client_name` |
| `policy_copy_all` | `copy_access_policies_from_node` (уже есть для Push full) |
| `config_files_write` | `write_config_file` + `apply_config_changes` |
| `antizapret_settings_patch` | `update_antizapret_settings` |
| `routing_apply` | фоновая задача apply на replica |
| `cidr_deploy_files` | существующий deploy path |

### 4.3. Резолв shadow-клиента

Для policy-операций:

```text
primary VpnConfig.id → VpnConfig на replica WHERE ha_primary_config_id = primary.id
```

Если shadow нет (рассинхрон после сбоя) — **не создавать молча**: записать ошибку, `sync_status=failed`, предложить Push full.

Helper: `get_shadow_configs(db, group, primary_config) -> list[VpnConfig]`.

### 4.4. Репликация файлов конфигурации

Переиспользовать `edit_files_transfer.run_edit_files_transfer`:

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

### 4.6. Reconcile worker (v2)

Расширить `reconcile_worker.py` (опционально, флаг `NODE_SYNC_AUTO_HEAL`):

1. Drift detected → попытка **incremental heal** (не full push).
2. Если heal неудачен N раз → notify + оставить `failed`.
3. **Никогда** auto Push full без явного флага (destructive).

---

## 5. Детальный бэклог по файлам

### 5.1. Backend — новые / расширить

| Файл | Задача |
|------|--------|
| `node_sync/replicate.py` | Центральный диспетчер операций |
| `node_sync/policy_sync.py` | `replicate_policy_op(primary_config, op, **kwargs)` |
| `node_sync/config_sync.py` | Обёртка над file transfer для HA-группы |
| `node_sync/antizapret_sync.py` | Репликация setup + apply |
| `node_sync/groups.py` | `get_sync_group_for_primary_or_raise`, `iter_replica_adapters` |
| `policy_import.py` | Добавить `copy_single_client_policy(source, target, client_name)` |
| `client_sync.py` | Вынести общую обработку ошибок в replicate helper |

### 5.2. Backend — точки встраивания (хуки)

| Файл / endpoint | Вызов после успеха на primary |
|-----------------|--------------------------------|
| `routers/client_access.py` — все POST block/unblock/limit/expiry | `replicate_policy_op` |
| `routers/configs.py` — PATCH cert, description/owner | renew + metadata sync |
| `routers/configs.py` — bulk endpoints | по операции |
| `routers/settings.py` — PATCH lists | `config_sync.replicate_files([...])` |
| `routers/edit_files.py` — PUT, POST batch | `config_sync.replicate_files` |
| `routers/routing.py` — PUT settings, POST apply | `antizapret_sync` |
| `routers/routing.py` — providers, sync | `config_sync` / cidr deploy |
| `services/client_templates.py` | после create — policies + replicate |
| `services/bulk_config_ops.py` | block/renew/unblock |
| `services/access_policy.py` | не менять ядро; вызывать с `node_id=replica` из policy_sync |

### 5.3. Конфигурация и исключения

Расширить `fingerprints.CONFIG_FINGERPRINT_EXCLUDE` документированным списком **HA-local files**.

Добавить `ANTIZAPRET_HA_SETTING_EXCLUDE` (env или константа) для ключей setup, которые не реплицируются (WARP endpoint, slave IP и т.д.).

Настройки в `config.py`:

- `NODE_SYNC_AUTO_REPLICATE_CONFIG_FILES` (default `true` при `auto`)
- `NODE_SYNC_AUTO_REPLICATE_POLICIES` (default `true`)
- `NODE_SYNC_AUTO_HEAL` (default `false`)
- `NODE_SYNC_REPLICATE_DOALL` (default `true` — запускать doall на replica после file sync)

### 5.4. Frontend

| Компонент | Задача |
|-----------|--------|
| `NodeSyncGroupSection.tsx` | Обновить описание режима Auto: полный список того, что синхронизируется |
| Уведомления | Toast при partial failure репликации («клиент заблокирован на primary, ошибка на replica X») |
| HA badge / sync_status | Показывать детали последней ошибки репликации (не только Verify) |
| Редактор файлов | Убрать/пометить ручной «Перенос на узлы» как fallback, не основной путь в HA |

### 5.5. Документация

| Файл | Задача |
|------|--------|
| `docs/NodeSync.md` | Переписать секцию v2: что делает `auto` после доработки |
| `docs/edit-files.md` | HA: auto-replicate vs manual transfer |
| `docs/antizapret-config.md` | Исключения node-specific |
| `CHANGELOG.md` | Запись при релизе |

---

## 6. Этапы реализации

### Этап A — Политики клиента (высокий приоритет)

1. `policy_sync.py` + тесты на block/unblock/limit/expiry.
2. Хуки в `client_access.py`.
3. `bulk_config_ops` block/renew.
4. PATCH cert + shadow metadata.

**Критерий готовности:** блокировка и лимит на primary → тот же статус на replica без Push full.

### Этап B — Файлы config (высокий приоритет)

1. `config_sync.py` обёртка над `edit_files_transfer`.
2. Хуки: `settings.py`, `edit_files.py`.
3. Учёт `CONFIG_FINGERPRINT_EXCLUDE` при записи.

**Критерий:** правка `include-hosts.txt` на primary → Verify `antizapret/config` совпадает (кроме excluded).

### Этап C — AntiZapret setup + apply

1. Whitelist ключей setup для HA.
2. Репликация `PUT antizapret-settings`.
3. Цепочка: save → replicate setup → enqueue apply на каждой replica.

**Критерий:** смена флага на primary → после apply одинаковое поведение на failover.

### Этап D — CIDR / providers

1. Аудит `resolve_deploy_targets` для HA.
2. Репликация ручных правок provider files.
3. Sync compile → deploy на все replica группы.

### Этап E — Reconcile auto-heal (низкий приоритет)

1. Incremental heal по типу drift (fingerprint vs clients vs policies).
2. Admin notify с actionable hint.

### Этап F — Push full остаётся

- Первичное выравнивание.
- Восстановление после split-brain.
- Смена состава группы / переезд primary.

---

## 7. Тестирование

### Unit

- `policy_sync`: каждая операция, partial failure, нет shadow.
- `config_sync`: excluded files не перезаписываются.
- `antizapret_sync`: excluded setup keys.

### Integration

- `auto_group_db` fixture: операция на primary → assert adapter calls на replica (mocks).
- Fingerprint match после file sync.

### E2E / manual checklist

- [ ] Create OVPN + WG → на replica есть peer/cert
- [ ] Block temp → failover IP, клиент не подключается
- [ ] Traffic limit → превышение на обоих узлах
- [ ] `include-hosts.txt` → Verify green
- [ ] `warper-include-ips.txt` только на одной replica → Verify green
- [ ] Partial replica offline → `sync_status=failed`, primary не откатывается
- [ ] Push full после рассинхрона → heal

---

## 8. Риски и решения

| Риск | Митигация |
|------|-----------|
| `doall.sh` 5+ мин на 3 replica | Фоновые задачи + progress в UI |
| Split-brain (успех primary, fail replica) | Уже есть `sync_status=failed`; не откатывать primary |
| Node-specific WARP/slave перезаписан | Exclude lists + merge policy |
| Ручные правки по SSH | Reconcile drift + документация «только через primary» |
| Разные версии AntiZapret | Существующий preflight в `validate_sync_group_payload` |
| Cert index.txt race при параллельном renew | Сериализовать PKI-операции на группу (lock) |

---

## 9. Открытые вопросы (нужно решить до кодирования)

1. **Owner/description** на shadow — реплицировать всегда или только при явном PATCH?
2. **Node default policy** — реплицировать на все replica или хранить только на primary node_id?
3. **Traffic counters** — сброс лимита на primary сбрасывает на replica? (рекомендация: да, копировать policy row целиком)
4. **Auto-heal** в reconcile — включаем по умолчанию или только opt-in?
5. **manual_full** — расширять теми же хуками или оставить только Push full?

---

## 10. Краткая сводка для продукта

**Сейчас:** `auto` = create/delete клиентов.

**Нужно:** `auto` = create/delete + **все админские изменения на primary** (политики, файлы, setup, apply), с исключением node-local артефактов.

**Push full** остаётся для bootstrap и disaster recovery, но не для каждой правки `include-hosts.txt`.
