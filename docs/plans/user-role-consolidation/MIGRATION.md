# MIGRATION: viewer → user, rename ACL

Шаги выполняются в `backend/app/database.py` (`run_db_migrations`) в стиле проекта (без Alembic).

---

## 1. Колонка `can_create_configs`

```sql
-- PostgreSQL / SQLite compatible ensure-column pattern уже в проекте
ALTER TABLE users ADD COLUMN can_create_configs BOOLEAN NOT NULL DEFAULT TRUE;
```

Для существующих строк: `true` (поведение как у текущего `user`).

---

## 2. Таблица grants: `viewer_config_access` → `user_config_access`

Порядок:

1. Если есть `viewer_config_access` и нет `user_config_access`:
   - `ALTER TABLE viewer_config_access RENAME TO user_config_access;`  
     или create + `INSERT INTO user_config_access SELECT ...` + drop old.
2. Переименовать unique constraint при необходимости (`uq_user_config_group`).
3. ORM-модель: `UserConfigAccess`, `__tablename__ = "user_config_access"`.
4. В `_purge_user_before_delete` удалять из новой таблицы.

Данные grants **не** конвертировать в `owner_id`.

---

## 3. Роли `viewer` → `user`

После деплоя кода с поддержкой ACL на user:

```sql
UPDATE users
SET role = 'user',
    can_create_configs = FALSE
WHERE role = 'viewer';
```

Для PostgreSQL enum: если `UserRole` — нативный ENUM, сначала добавить/использовать значение через текстовый cast по принятому в проекте способу, затем убрать `viewer` из enum (или оставить мёртвое значение до следующего cleanup — предпочтительно удалить, если SQLite/string enum).

Проверить фактический диалект БД проекта и следовать существующим миграциям enum в `database.py`.

---

## 4. JWT / сессии

Access token содержит `"role": "viewer"`. После удаления enum:

- Старые токены могут давать 401 / ошибки парсинга роли.
- В CHANGELOG: «После обновления выполните повторный вход».

Refresh tokens можно не чистить принудительно — при refresh пользователь уже с новой ролью в БД получит новый access с `user`.

---

## 5. Удаление aliases и мёртвого кода

В фазе drop:

- `/api/system/viewer-access` endpoints
- `require_not_viewer`
- skip admin_notify на login для viewer
- UI role `viewer`, stats card, `viewerOk`
- docs mentioning Наблюдатель / Только просмотр как отдельную роль

---

## 6. Rollback (кратко)

Обратный ход сложен после drop enum. До drop:

- Можно вернуть роль `viewer` и фильтровать ACL только для viewer.
- После `UPDATE role=user` — восстановить viewer только если сохранён бэкап БД.

Рекомендация: бэкап панели перед деплоем фазы drop.

---

[← README плана](README.md) · [SPEC.md](SPEC.md)
