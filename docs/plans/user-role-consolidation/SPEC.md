# SPEC: консолидация роли Пользователь и удаление viewer

Техническая и продуктовая спецификация. Миграция данных — [MIGRATION.md](MIGRATION.md). Реализация — по [PROMPTS.md](PROMPTS.md).

---

## 1. Проблема

Сейчас две overlapping-роли:

| Роль | Смысл |
|------|--------|
| **Пользователь** (`user`) | Владеет своими конфигами, может создавать (квота), нет белого списка чужих |
| **Только просмотр** (`viewer`) | Белый список клиентов, без создания; web grants не работают в Mini/боте |

Админ не может собрать «пользователь без создания + доп. доступ к чужим клиентам» без отдельной роли. Квота `0` сейчас означает **unlimited**, а не «нельзя создавать».

Нужно: одна роль `user` с флагами и ACL; роль `viewer` удалить.

---

## 2. Продуктовый UX

### 2.1. Карточка пользователя (Настройки → Пользователи)

Только для `role=user` (после drop viewer — для всех non-admin):

1. **Telegram ID**
2. **Может создавать конфигурации** — Switch (`can_create_configs`)
3. **Квота конфигов** — число; disabled/hint если create выключен
4. **Доп. доступ к клиентам** — чекбоксы VPN-клиентов (белый список `config_group`)
5. **Видимость VPN-профилей** — как сейчас (`visible_vpn_profiles`)

Роли в picker: **Администратор** | **Пользователь**. Пункта «Только просмотр» нет.

### 2.2. Поведение для пользователя

| Действие | Свои (`owner_id`) | По whitelist |
|----------|-------------------|--------------|
| Список / карточка | да | да |
| Скачивание / QR / one-time link | да | да |
| Удаление / patch / block / renew | да | **нет** |
| Создание нового | если `can_create_configs` и квота | — |

Админ — полный доступ без ACL/флага.

### 2.3. Навигация

Non-admin (бывший user и бывший viewer): **Конфигурации**, **Мониторинг трафика**, **Мой профиль** (как у текущего user). Без NOC, журналов, маршрутизации и т.д.

---

## 3. Модель данных

### 3.1. User

| Поле | Тип | Default | Смысл |
|------|-----|---------|--------|
| `can_create_configs` | `Boolean` | `true` | Разрешено создавать VPN-конфиги |
| `config_quota` | `Integer?` | `null` | Лимит owned-конфигов (семантика без изменений) |
| `visible_vpn_profiles` | `Text?` | `null` | Политика вариантов профилей (ортогонально ACL) |

### 3.2. UserConfigAccess

Таблица `user_config_access` (бывшая `viewer_config_access`):

| Колонка | Смысл |
|---------|--------|
| `user_id` | FK → users |
| `config_group` | Имя клиента или префикс (как сейчас) |
| unique `(user_id, config_group)` | |

Matching (без изменений семантики):

```
client_name.lower() == grant.lower()
OR client_name.lower().startswith(grant.lower())
```

### 3.3. Роли

Целевое: `UserRole = admin | user`.  
`viewer` удаляется после миграции ([MIGRATION.md](MIGRATION.md)).

---

## 4. Resolve ACL

```
def can_view_config(user, config, db):
    if user.role == admin: return True
    if config.owner_id == user.id: return True
    return matches_any_grant(user.id, config.client_name, db)

def can_mutate_config(user, config):
    if user.role == admin: return True
    return config.owner_id == user.id
```

Create:

```
can_create = user.can_create_configs and (quota unlimited or used < limit)
# admin: always (existing)
```

Квота `used` — только configs с `owner_id == user.id` (и HA-primary dedupe как сейчас).

`visible_vpn_profiles` применяется к **действующему** пользователю при выдаче `profile_files` (и для grant-доступа тоже).

---

## 5. Поверхности

| Поверхность | View ACL | Mutate | Create flag |
|-------------|----------|--------|-------------|
| Web `/api/configs` | да | да | да |
| Mini App `/tg-mini` | да | owner-only | да |
| Telegram bot | да | owner-only | да |
| Traffic / client_access scope | owned ∪ grant names | — | — |
| Публичные QR/links | без изменений | — | — |

---

## 6. API

| Метод | Назначение |
|-------|------------|
| `PATCH /api/users/{id}` | `can_create_configs: bool` |
| `GET /api/users/{id}/config-access` | `{ user_id, config_groups: string[] }` admin |
| `PUT /api/users/{id}/config-access` | replace-all grants admin |
| `GET /api/configs/quota` | `can_create` учитывает флаг |

Временные aliases (до фазы drop):  
`GET/PUT /api/system/viewer-access*` → те же handlers.

Ответ пользователя /me и list users включает `can_create_configs`.

---

## 7. Граничные случаи

| Случай | Поведение |
|--------|-----------|
| Пустой whitelist, нет owned | Пустой список конфигов |
| Grant на префикс | Несколько клиентов; mutate всё равно запрещён |
| Create выключен, квота большая | Create 403 / кнопки disabled |
| Create включен, квота исчерпана | Как сейчас |
| Удаление user | Purge `user_config_access` |
| Смена роли admin→user | Флаг и grants по усмотрению админа; defaults: create=true, grants=[] |
| Старый JWT с `role=viewer` | После drop enum — перелогин |

---

## 8. Критерии приёмки

1. User A, `can_create_configs=false`, grants=[`client-x`]: видит `client-x` в web/Mini/боте; скачивает; **не** может DELETE; кнопки create скрыты/disabled; POST → 403.
2. User B владеет `client-y`, grant на `client-x`: видит оба; delete только `client-y`.
3. User без grant и не owner → 403 на get/download чужого.
4. После миграции бывший viewer: `role=user`, `can_create_configs=false`, те же grants, UI без роли «Только просмотр».
5. Админ видит всё, create без ограничений по флагу.
6. Traffic для user с grant показывает трафик grant-клиентов.

---

## 9. Вне скоупа

- Перенос ownership при миграции (grants остаются grants).
- Отдельная роль «наблюдатель» после drop.
- Изменение семантики `config_quota <= 0` (unlimited) — не трогать в этой фиче.
- Публичные download routes.

---

## 10. Связанные пользовательские доки (после реализации)

- [`docs/README.md`](../../README.md) — таблица ролей
- [`docs/nastrojki/polzovateli.md`](../../nastrojki/polzovateli.md)
- [`docs/konfiguracii.md`](../../konfiguracii.md)
- [`docs/PROJECT_MAP.md`](../../PROJECT_MAP.md)
- [`SECURITY.md`](../../../SECURITY.md)
- [`CHANGELOG.md`](../../../CHANGELOG.md)

---

[← README плана](README.md)
