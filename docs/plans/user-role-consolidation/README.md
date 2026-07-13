# План: консолидация роли Пользователь и удаление viewer

**Статус:** реализовано (2026-07-13)  
**Аудитория:** разработчики / агенты Cursor

Перенос функционала роли **Только просмотр** (`viewer`) в **Пользователь** (`user`): белый список чужих клиентов, доступ без владения (read-only), переключатель создания конфигов. Затем миграция существующих viewer и удаление роли из enum/UI/доков.

---

## Оглавление

| Файл | Содержание |
|------|------------|
| [SPEC.md](SPEC.md) | Продуктовая и техническая спека: ACL, флаг create, поверхности, приёмка |
| [PROMPTS.md](PROMPTS.md) | Готовые промпты для поэтапной реализации в агенте |
| [MIGRATION.md](MIGRATION.md) | Rename таблицы grants, viewer→user, удаление enum |

---

## Ключевые решения (кратко)

- Доступ: `union(owned, whitelist)` для `role=user`.
- Whitelist = **только** list / get / download / QR / one-time link. Mutate (delete/patch/block) — только владелец или admin.
- `User.can_create_configs: bool` (default `true`); не путать с `config_quota=0` (unlimited).
- Квота считается только по `owner_id`; grants квоту не едят.
- Один ACL для web, Mini App, Telegram-бота, traffic.
- `ViewerConfigAccess` → `UserConfigAccess` (`user_config_access`).
- API: `GET/PUT /users/{id}/config-access`; aliases `/system/viewer-access` до фазы drop.
- Миграция: `viewer` → `user` с `can_create_configs=false`, grants сохраняются.

Подробности — в [SPEC.md](SPEC.md). Миграция — [MIGRATION.md](MIGRATION.md). Реализация — по [PROMPTS.md](PROMPTS.md).

---

[← К оглавлению docs](../../README.md)
