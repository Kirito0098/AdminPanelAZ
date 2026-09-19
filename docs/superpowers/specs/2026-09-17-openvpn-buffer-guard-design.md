# OpenVPN Buffer Guard (ENOBUFS)

> **Дефолты режима и порога** (ранее `kill_restart` / `500`) заменены спецификацией [2026-09-19-openvpn-buffer-guard-defaults-design.md](2026-09-19-openvpn-buffer-guard-defaults-design.md) (`notify` / `40` / 60 с, рекомендации по режимам, UI «Применить рекомендацию», миграция заводских `500`/`60`). Остальная логика detect/worker/kill в этом документе без изменений.

**Дата:** 2026-09-17  
**Статус:** draft (ожидает ревью)  
**Контекст:** 2026-09-17 на VPN-узле AntiZapret (`openvpn-server@antizapret-udp`, DCO, `duplicate-cn`) один клиент вызвал шторм `write UDPv4 []: No buffer space available (fd=6,code=105)`. Общий UDP-сокет OpenVPN перестал нормально отвечать; остальные клиенты не коннектились до рестарта юнита/ребута. Мелкие ENOBUFS встречались и раньше (~десятки/день), критичный каскад — при тысячах ошибок в секунду.

## Цель

В AdminPanelAZ админ может:

1. Видеть **предупреждение** о риске UDP buffer storm (ENOBUFS).
2. **Включать/выключать** защиту и выбирать **режим реакции** в UI.
3. Получать **информацию** при срабатывании (UI + Telegram AdminNotify).
4. При выбранном режиме — автоматически **кикать CN**, при необходимости **рестартить OpenVPN-юнит**, опционально **временно банить** CN.

## Не цели

- Патчи исходников OpenVPN / AntiZapret `update.sh` / `doall.sh`.
- Изменение `sndbuf`/`rcvbuf` как «лечение» (уже крупные; не первопричина каскада).
- Автоматический reboot ОС (есть отдельно; Buffer Guard его не вызывает).
- Защита WireGuard / AmneziaWG (только OpenVPN UDP/TCP server units панели).
- Полноценный SIEM / хранение сырых journal-дампов в БД.
- Slash-команды Telegram для настройки Guard (достаточно AdminNotify + UI).

## Решения (утверждено)

| Вопрос | Выбор |
|--------|--------|
| Где UI | **Конфиг AntiZapret** → вкладка **OpenVPN (панель)** (`OpenVpnPanelTab`), отдельная карточка |
| Вкл/выкл | Toggle на карточке; настройки **на узел** (`node_id`) |
| Режимы | `notify` \| `kill` \| `kill_restart` \| `kill_restart_temp_ban` |
| Дефолт режима | `notify` |
| Дефолт enabled | **выкл** (opt-in), чтобы не кикать на проде без согласия |
| Детект | Подсчёт строк `No buffer space available` в journal OpenVPN за скользящее окно |
| Виновник | CN с наибольшим числом ENOBUFS в окне; fallback — real IP:port из той же строки |
| Cooldown | Не повторять полный цикл чаще N минут на узел (дефолт 15) |
| Уведомления | Всегда при срабатывании (если Telegram AdminNotify настроен); плюс статус на карточке |
| HA / multi-node | Worker на панели опрашивает **каждый online VPN-узел** с `enabled=true` через node adapter |

## UI

Страница: Конфиг AntiZapret → `?tab=openvpn-panel`.

Карточка **«OpenVPN Buffer Guard»** (ниже remote / multihome):

1. **Warning** (всегда виден, даже если Guard выкл): кратко — ENOBUFS на общем UDP-сокете; один шумный пир может уронить коннекты всех; DCO/`duplicate-cn` усиливают риск; ребут ОС не обязателен — достаточно kill/restart юнита.
2. **Вкл/выкл** защиты для **активного узла** (как multihome привязан к выбранному узлу).
3. **Режим** (select, disabled если Guard выкл):
   - Только уведомление  
   - Кик CN  
   - Кик → если не стихло → restart OpenVPN-юнита  
   - Кик → restart → временный бан CN  
4. **Параметры** (с дефолтами, сворачиваемый блок «Дополнительно»):
   - порог ошибок за окно (дефолт **40** / **60 с**; рекомендации по режимам — см. spec 2026-09-19)
   - ожидание после kill перед escalate (дефолт **30 с**)
   - cooldown (дефолт **15 мин**)
   - срок temp ban (дефолт **60 мин**, только для режима с баном)
   - какие юниты слушать (дефолт: `antizapret-udp`, `vpn-udp`; опционально tcp)
5. **Последний инцидент** на этом узле: время, unit, CN, real address, счётчик ENOBUFS, выбранный режим, выполненные шаги, итог (`notified` / `killed` / `restarted` / `banned` / `failed` — как в `openvpn_buffer_guard_events.result`).
6. Кнопка **«Проверить сейчас»** (ручной scan, `require_admin`) — для диагностики без ожидания тика worker.

Сохранение настроек — отдельный Save на карточке (как multihome), не смешивать с remote hosts dirty-state.

## Backend

### Хранение

Таблица `openvpn_buffer_guard_settings` (1 row на `node_id`):

| Поле | Тип | Дефолт |
|------|-----|--------|
| `node_id` | FK nodes | — |
| `enabled` | bool | false |
| `mode` | enum string | `notify` |
| `threshold_count` | int | 40 |
| `window_seconds` | int | 60 |
| `escalate_after_seconds` | int | 30 |
| `cooldown_minutes` | int | 15 |
| `temp_ban_minutes` | int | 60 |
| `watch_units` | JSON list | `["antizapret-udp","vpn-udp"]` |
| `updated_at` | datetime | — |

Таблица `openvpn_buffer_guard_events` (история, retain last ~100 на узел или 30 дней):

| Поле | Смысл |
|------|--------|
| `node_id`, `created_at` | где/когда |
| `unit` | например `antizapret-udp` |
| `common_name`, `real_address` | виновник |
| `error_count`, `window_seconds` | метрика |
| `mode` | режим на момент срабатывания |
| `actions_json` | `["notify","kill",…]` |
| `result` | `notified` \| `killed` \| `restarted` \| `banned` \| `failed` |
| `detail` | короткий текст ошибки/итога |

Опционально в `AppSetting` ключ `ovpn_buffer_guard:last_tick` только для диагностики worker — не обязательно в v1.

### API (`require_admin`)

| Method | Path | Поведение |
|--------|------|----------|
| `GET` | `/openvpn-buffer-guard/settings?node_id=` | Текущие настройки (+ defaults если строки нет) |
| `PUT` | `/openvpn-buffer-guard/settings` | Upsert по `node_id` |
| `GET` | `/openvpn-buffer-guard/events?node_id=&limit=` | История инцидентов |
| `POST` | `/openvpn-buffer-guard/scan` | Body `{ node_id }`. Разовый детект; если порог превышен и enabled — выполняет режим; если disabled — только возвращает findings без действий |

Feature toggle: отдельный ключ не обязателен в v1 (карточка живёт на странице OpenVPN panel). Если позже понадобится — `openvpn_buffer_guard` в feature_toggles.

### Детект (на узле через adapter / node_agent)

Команда без shell-инъекций, например:

```text
journalctl -u openvpn-server@UNIT.service --since "-WINDOW seconds" --no-pager -o cat
```

На стороне панели/агента: подсчёт строк с `No buffer space available`; из строк вида  
`CN/udp4:IP:PORT write UDPv4 []: No buffer space available` извлечь CN и real address; выбрать top CN.

Если `journalctl` недоступен или команда упала — event `failed` + notify, без kill.  
Если журнал читается, но ENOBUFS ниже порога (в т.ч. ноль строк) — **ничего не делать** (это норма).

### Режимы

Общее: при превышении порога всегда пишется event; если Telegram AdminNotify доступен — сообщение с node, unit, CN, count, mode, actions.

| Mode | Действия |
|------|----------|
| `notify` | Только notify + event |
| `kill` | `echo kill CN` → management sock юнита (как `client.sh` / access_policy) |
| `kill_restart` | kill → ждать `escalate_after_seconds` → повторный count в коротком окне → если всё ещё ≥ порога (или ≥ 50% порога) → `systemctl restart openvpn-server@UNIT` |
| `kill_restart_temp_ban` | как `kill_restart` + добавить CN в `banned_clients` через существующий access_policy; снять бан по таймеру `temp_ban_minutes` (фоновая задача / запись `expires_at` в event и тик worker) |

Restart только того unit, где превышен порог (не всех OpenVPN сразу).

Cooldown: не запускать новый цикл на узле, пока не истечёт `cooldown_minutes` с последнего event (кроме ручного «Проверить сейчас» — ручной scan игнорирует cooldown, но пишет event с флагом `manual`).

### Worker

`run_openvpn_buffer_guard_loop` в lifespan (рядом с alert_rules):

- Интервал тика: **20 с** (конфиг env опционально).
- Для каждого online node с `enabled=true` и вне cooldown — scan всех `watch_units`.
- Ошибки одного узла не останавливают цикл.

### Интеграции (существующий код)

- Kill: management UNIX socket `/run/openvpn-server/{unit}.sock` (уже используется при delete клиента).
- Ban: `AccessPolicyService` / `banned_clients` + `ensure_openvpn_ban_check`.
- Restart: существующий restart service path настроек/обслуживания, ограниченный allowlist `openvpn-server@*`.
- Notify: AdminNotify / telegram admin channel (тот же путь, что resource alerts).

### Аудит

Action log keys: `openvpn_buffer_guard_triggered`, `openvpn_buffer_guard_kill`, `openvpn_buffer_guard_restart`, `openvpn_buffer_guard_ban`.

## Документация

- Короткий абзац в `docs/antizapret-config.md` (вкладка OpenVPN панель).
- При необходимости ссылка из `docs/nastrojki/monitoring-i-alerty.md` («связанная защита — Buffer Guard»).
- User-facing тексты на русском.

## Тесты

- Парсер ENOBUFS-строк → CN / IP (unit-тесты на фикстурах логов).
- Режимы: mock adapter — `notify` не вызывает kill; `kill` вызывает kill; `kill_restart` после escalate вызывает restart.
- Temp ban: write banned + schedule unban.
- Settings upsert / defaults / cooldown skip.
- UI не обязателен в e2e v1; backend pytest достаточно.

## Критерии готовности

1. На вкладке OpenVPN (панель) видна карточка с warning, toggle, mode, last event.  
2. При искусственном высоком count (тест/mock) срабатывает выбранный режим.  
3. Telegram (если настроен) получает сообщение о инциденте.  
4. AntiZapret git-tree / `setup` не меняются.

## Вне скоупа v1 (можно позже)

- Авто-unban UI кнопка «Снять бан Guard».
- График ENOBUFS/мин на карточке.
- Отдельный feature toggle в хабе модулей.
- Детект по `/proc/net/udp` без journal.
