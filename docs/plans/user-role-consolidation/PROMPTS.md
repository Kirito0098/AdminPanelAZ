# PROMPTS: консолидация user / удаление viewer

Копируй промпт целиком в агент. Спека: [SPEC.md](SPEC.md). Миграция: [MIGRATION.md](MIGRATION.md).

Общий контекст:

> Репозиторий AdminPanelAZ. Фича «консолидация роли Пользователь»: перенос whitelist ACL и режима без создания с `viewer` на `user`, затем удаление роли `viewer`. Access = union(owned, whitelist); whitelist = view/download only; `can_create_configs` bool. Подробности — `docs/plans/user-role-consolidation/SPEC.md`.

---

## Prompt 1 — Модель, флаг create, rename ACL table

```
По docs/plans/user-role-consolidation/SPEC.md и MIGRATION.md реализуй backend-ядро (без удаления роли viewer пока):

1. User.can_create_configs Boolean default true + миграция в database.py.
2. UserConfigAccess / таблица user_config_access; миграция rename/copy из viewer_config_access.
3. schemas UserUpdate/UserResponse + сохранение флага в users router (admin only).
4. self_service: can_create учитывает флаг; enforce_user_can_create_config → 403.
5. Не удаляй UserRole.viewer в этом шаге.
6. Unit-тест: can_create_configs=false → can_create false / enforce 403.
```

---

## Prompt 2 — View/mutate ACL + API + TG/traffic parity

```
Продолжи консолидацию (SPEC §4–§6):

1. Хелперы can_view_config / can_mutate_config / list_accessible; wire configs router.
2. GET/PUT /users/{id}/config-access; aliases system/viewer-access.
3. tg_mini + telegram bot + traffic: тот же view ACL; mutate owner-only.
4. Frontend: Switch can_create + блок «Доп. доступ к клиентам» в UsersTab для user; API client rename.
5. Тесты: grant view ok, DELETE grant → 403.
```

---

## Prompt 3 — Миграция viewer→user + drop роли

```
По MIGRATION.md:

1. Startup migration: все role=viewer → user, can_create_configs=false.
2. Удали UserRole.viewer из backend/frontend/labels/Layout viewerOk/auth notify skip/require_not_viewer.
3. Удали aliases /system/viewer-access.
4. Обнови user docs + CHANGELOG + статус README плана.
5. Тест миграции / smoke: бывший viewer видит grants, create запрещён.
```

---

## Рекомендуемый порядок

1 → 2 → 3. После каждого этапа — тесты слоя и чеклист SPEC §8.

---

[← README плана](README.md) · [SPEC.md](SPEC.md)
