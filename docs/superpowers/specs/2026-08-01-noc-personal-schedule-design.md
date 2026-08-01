# NOC: персональное расписание сводок

**Дата:** 2026-08-01  
**Статус:** implemented  
**Контекст:** ежедневная NOC-сводка сейчас уходит по env-cron `0 8 * * *` (08:00 UTC). Нужно локальное время по поясу профиля и настройка в вебе **на каждого админа**.

## Цель

Каждый администратор с включённым событием `noc_report` задаёт в панели:

- время **ежедневной** текстовой сводки;
- день недели и время **еженедельной** текстовой сводки (+ PNG, если включён env-флаг).

Время интерпретируется в **часовом поясе профиля** (`users.timezone`, иначе `users.last_client_timezone`).

## Не цели

- Персональный cron произвольной сложности (только HH:MM + день недели).
- Отдельный пояс только для NOC.
- Расписание для роли `user` (NOC — admin-only).
- Менять содержание сводки / PNG-дашборда.

## Текущее поведение (baseline)

| Что | Сейчас |
|-----|--------|
| Daily | `Settings.noc_report_daily_cron` = `0 8 * * *` (UTC) |
| Weekly | `Settings.noc_report_weekly_cron` = `0 9 * * 1` (UTC, Monday) |
| Scheduler | `noc_report_scheduler.py` — один тик, одна рассылка всем recipients |
| TZ в тексте | уже через `resolve_notify_timezone` / профиль |

## Решение

### Модель данных (`users`)

Новые поля (строки, пусто = fallback на env-cron):

| Поле | Формат | Пример | Default при миграции |
|------|--------|--------|----------------------|
| `noc_daily_time` | `HH:MM` | `11:00` | `""` (fallback env) |
| `noc_weekly_dow` | `0–6` cron-стиль (вс=0 … сб=6) **или** пусто | `1` (пн) | `""` |
| `noc_weekly_time` | `HH:MM` | `12:00` | `""` |

Персональный weekly активен только если **оба** поля `noc_weekly_dow` и `noc_weekly_time` непустые; иначе fallback на env weekly cron. Daily — если непустой `noc_daily_time`.

Рекомендуемые UI-дефолты при первом сохранении (если пользователь открыл форму и сохранил без правок): daily `11:00`, weekly пн `12:00` — эквивалент бывших 08:00/09:00 UTC для Europe/Moscow. Пока поля пустые — поведение как сейчас (env UTC-cron), чтобы не ломать чужие панели после апдейта.

### Эффективный пояс

Переиспользовать `effective_user_timezone(user)` из `notify_time.py`:

1. `users.timezone` если задан;
2. иначе `users.last_client_timezone`;
3. иначе UTC (и в UI показать предупреждение «задайте часовой пояс»).

### Scheduler

Переписать `run_noc_report_scheduler_tick`:

1. Раз в ~60 с (как сейчас).
2. Для каждого admin с `telegram_id`, `has_tg_notify_event("noc_report")`, прошедшего `filter_notify_recipients`:
   - вычислить `local_now` в эффективном поясе;
   - **daily:** если `noc_daily_time` задан и совпадает `HH:MM` → отправить **только этому** user; иначе если пусто — матчить глобальный `noc_report_daily_cron` в UTC (как сейчас), но доставка всё равно персональная (один recipient).
   - **weekly:** аналогично по `noc_weekly_dow` + `noc_weekly_time`, иначе env weekly cron.
3. Weekly image (`send_weekly_image_report`) — в том же weekly-тике, **тому же** user (не всем сразу).
4. Dedup: ключи в `AppSetting`:
   - `noc_report_daily_last_run:{user_id}` = ISO timestamp;
   - `noc_report_weekly_last_run:{user_id}` аналогично.
   Сравнение по **локальной** минуте пользователя (year/month/day/hour/minute в эффективном поясе).

Вынести `send_noc_report_to_user(db, period, user)` / параметризовать `send_noc_report(..., recipients=[user])`, чтобы не дублировать текст N раз зря, но и не слать чужим.

### API / схема

Расширить личные настройки (тот же PATCH `/settings` или `/auth/me`-adjacent personal update, что уже пишет `timezone`/`theme`):

- GET: отдавать `noc_daily_time`, `noc_weekly_dow`, `noc_weekly_time`
- PATCH: валидация `HH:MM`, dow `0–6` или `""`

Только admin может писать NOC-поля (user-роль игнорирует / 403).

### UI

**Настройки → Личные**, карточка рядом с Telegram / после часового пояса (admin only):

- «NOC сводка — расписание»
- Daily: time input
- Weekly: select дня + time input
- Хинт: «Время по вашему часовому поясу (Europe/Moscow)»
- Если пояс неизвестен — warning + ссылка на блок пояса

Глобальный блок предпросмотра в TelegramSettingsPanel без изменения (ручная отправка).

### Env / совместимость

- `NOC_REPORT_ENABLED`, interval, weekly image flags — без изменений.
- `NOC_REPORT_DAILY_CRON` / `WEEKLY_CRON` — fallback для админов с пустыми персональными полями.
- После того как админ сохранил личное время, env-cron для него не используется.

### Документация

- `docs/Telegram.md` и/или `docs/noc-monitoring.md` — коротко: где задать время.
- `docs/PROJECT_MAP.md` — поля/секция, если есть таблица личных настроек.
- CHANGELOG — Fixed/Added.

### Тесты

- Парсинг `HH:MM`, отказ на мусор.
- Матч daily в Europe/Moscow при UTC «не том» часе.
- Weekly: dow + time.
- Dedup: второй тик в ту же минуту не шлёт.
- Пустые поля → fallback на env cron (UTC).
- User без `noc_report` / не в recipient filter — skip.

## Риски

| Риск | Митигация |
|------|-----------|
| DST (смещение пояса) | Матч по локальному `HH:MM` через ZoneInfo, не заранее посчитанный UTC-cron |
| Нет last_client_timezone | Warning в UI; матч в UTC до появления пояса |
| N админов × разная минута | Ок: цикл по users раз в минуту, дёшево |
| Двойная отправка при рестарте | Per-user last_run ключи |

## Acceptance

1. Админ с поясом Moscow ставит daily `11:00` → сводка в 11:00 MSK, не в 08:00 UTC.
2. Второй админ с другим временем получает свою сводку в своё время.
3. Weekly: выбранный день+время в локальном поясе; PNG уходит вместе с weekly text этому админу.
4. Пустые поля — старое UTC-поведение из env.
5. В тексте сообщения время уже в поясе профиля (существующий пайплайн).

## Out of scope follow-ups

- Per-user enable/disable NOC schedule отдельно от `tg_notify_events.noc_report`.
- Секундная точность / окна «±N минут».
