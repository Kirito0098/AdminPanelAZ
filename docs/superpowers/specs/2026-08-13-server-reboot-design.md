# Перезагрузка ОС сервера (панель + Telegram)

**Дата:** 2026-08-13  
**Статус:** implemented  
**Контекст:** в Обслуживании есть doall / пересоздание профилей / перезапуск VPN-служб и отдельно перезапуск **сервиса панели**; нет безопасного reboot **ОС** выбранного VPN-узла из UI и бота.

## Цель

Админ может инициировать перезагрузку ОС любого VPN-узла (`Node`) из:

- веб-панели (Настройки → Обслуживание);
- Telegram-бота (`/settings` → Обслуживание);

с двойным подтверждением, кодовой фразой `REBOOT`, задержкой **15 с** и кнопкой **Отменить**.

## Не цели

- Slash-команда `/reboot`.
- Reboot proxy-хостов вне модели `Node`.
- Настраиваемая задержка ≠ 15 с.
- Авто-reboot по алертам / мониторингу.
- Путать с «Перезапуск панели» (`adminpanelaz` systemd) или «Перезапуск службы» (VPN units).
- Реальные e2e/integration, вызывающие `systemctl reboot` / `reboot` на живой машине.

## Решения (утверждено)

| Вопрос | Выбор |
|--------|--------|
| Что перезагружаем | ОС VPN-узла (`systemctl reboot` / эквивалент) |
| Какой узел | Любой из списка `Node` (не только активный) |
| Подтверждение | Двойное + ввод фразы `REBOOT` (одинакова для всех узлов) |
| Тайминг | 15 с delay + Cancel в панели и Telegram |
| Архитектура | Pending-reboot сервис + общий API; бот и UI вызывают один API |

## Backend

### Права

Только `require_admin` (как `run_doall` / `restart_service`).

### Pending reboot

Сервис (например `app/services/server_reboot.py`):

- Не больше **одного** активного pending **на `node_id`**.
- In-memory timer/task + опциональное зеркало метаданных в `AppSetting` для диагностики.
- Если процесс панели перезапустился во время таймера: pending **не** выполняется автоматически после старта (безопасный default: считать отменённым/просроченным).

Поля pending (логически):

- `reboot_id` (uuid)
- `node_id`, `node_name`
- `scheduled_by` (username)
- `created_at`, `execute_at` (`created_at + 15s`)
- `status`: `pending` | `cancelled` | `executed` | `failed`

### API

| Method | Path | Поведение |
|--------|------|----------|
| `POST` | `/settings/reboot` | Body: `{ "node_id": int, "confirm": "REBOOT" }`. `confirm` строго `REBOOT` (case-sensitive), иначе 400. Неизвестный узел → 404. Уже есть pending на этот узел → 409. Создаёт pending, возвращает `{ reboot_id, node_id, node_name, execute_at, delay_seconds: 15, warning? }`. |
| `POST` | `/settings/reboot/{reboot_id}/cancel` | Отмена до `execute_at`; после execute/expiry → 409. |
| `GET` | `/settings/reboot/pending` | `{ "items": [ ... ] }` — все pending со `status=pending` (обычно 0–N по узлам); пустой список если нет. |

Опционально: warning в ответе schedule, если узел `offline`/`unknown` — schedule всё равно разрешён, попытка на execute.

### Выполнение

По истечении 15 с:

1. `adapter = get_adapter_for_node(node)`
2. `adapter.reboot()`
3. Аудит + admin notify (success/fail)

Команда на хосте: `systemctl reboot` (предпочтительно `--no-wall`) либо эквивалент без shell-инъекций.

### Аудит / notify

Action log keys:

- `settings_reboot_schedule`
- `settings_reboot_cancel`
- `settings_reboot_execute` (и fail — в detail / отдельный key при необходимости)

Subject: имя узла / `node_id`.  
Admin notify — по аналогии с `settings_restart_service`.

Подписи в `frontend/src/lib/actionLogLabels.ts`.

## Adapter / node agent

### `NodeAdapter`

Новый метод: `reboot() -> str` (diagnostic output, как `restart_service`).

### Local

Безопасный subprocess / systemctl без `shell=True`. После успешного вызова локальный процесс панели ожидаемо умрёт — это норма.

### Remote

HTTP к node agent: `POST /reboot` с тем же auth (API key / mTLS), что и restart service.

### Node agent

Тонкий handler → `systemctl reboot`; ответ 200/202 до обрыва соединения.

### Proxy

Вне scope: только записи `Node`.

## UI панели

**Место:** `MaintenanceTab` — destructive-карточка **«Перезагрузка сервера»** (ниже перезапуска VPN-служб), визуально и текстом отделена от `PanelRestartCard` (сервис панели).

**Поток:**

1. Выбор узла из `getNodes()` (активный помечен; при одном узле — предвыбор).
2. Диалог: имя/host, предупреждение про недоступность VPN/хоста, поле ввода; confirm активен только при точном `REBOOT`.
3. После schedule — баннер с countdown 15 с и **Отменить**.
4. Polling `GET /settings/reboot/pending` (~1 с), пока есть pending.

**Диалог:** расширить `ConfirmDialog` / `useConfirmDialog` опциональным `confirmPhrase?: string` **или** локальный диалог в карточке — не ломая существующие confirm’ы.

**Копирайт:** «перезагрузка ОС сервера».

## Telegram

**Место:** `/settings` → Обслуживание → кнопка «🔁 Перезагрузка сервера».

**Поток:**

1. Список узлов → выбор `node_id`.
2. Confirm «Точно перезагрузить *\<name\>*?» → ✅ / ❌.
3. Ввод `REBOOT` через `settings_fsm` (новое поле, напр. `mnt_reboot`).
4. Schedule через тот же API → сообщение с таймером + inline **Отменить**.
5. Cancel / execute — edit или follow-up сообщение.
6. Неверная фраза — ошибка и повтор; отмена сбрасывает FSM.

**Доступ:** `_require_admin_ctx` only.

**Документация:** обновить гайд команд / help — reboot через Обслуживание, без новой slash-команды.

## Тестирование (обязательное ограничение)

- Unit-тесты с **mock** adapter / mock subprocess / mock agent client.
- **Запрещено** в CI и ручных agent-прогонах вызывать реальный `reboot` / `systemctl reboot` на хосте разработки.
- FSM и API cancel/schedule — покрыть моками времени (`execute_at`).

## Критерий готовности

1. Панель: выбрать узел → confirm → `REBOOT` → 15 с + отмена → команда уходит в adapter.
2. Telegram: тот же путь через Обслуживание.
3. Аудит и notify на schedule/cancel/execute.
4. Нет реальных reboot в тестах.

## Связанные файлы (ориентир)

- `backend/app/routers/maintenance.py`
- `backend/app/services/node_adapter.py`, `backend/node_agent/main.py`
- `backend/app/services/telegram_bot_handlers/settings_maintenance.py`, `settings_fsm.py`
- `frontend/src/components/settings/MaintenanceTab.tsx`
- `frontend/src/api/client.ts`, `frontend/src/lib/actionLogLabels.ts`
- `frontend/src/components/telegram/TelegramBotCommandsGuide.tsx`
