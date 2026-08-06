# Multi-remote hosts (OpenVPN): несколько адресов в профиле

**Дата:** 2026-08-02  
**Статус:** implemented  
**Ветка:** `feature/multi-remote-hosts`  
**Контекст:** при скачивании `.ovpn` нужен упорядоченный список `remote` (прокси / основной / запасной), который **не стирается** обновлением AntiZapret (`setup.sh`). Подробный продуктовый план: [`docs/plans/multi-remote-hosts/`](../../plans/multi-remote-hosts/README.md).

## Цель

Админ на каждом VPN-узле задаёт **упорядоченный список** IP/доменов (0…8). При выдаче OpenVPN-профиля из панели в `.ovpn` подставляются несколько строк `remote` в этом порядке. Список хранится в БД панели.

## Не цели (вне этого MVP)

- WireGuard / AmneziaWG multi-endpoint
- Запись multi-remote на диск AZ / правка templates
- Установка или запуск `proxy.sh` из панели
- Автозапись в `allow-ips.txt`
- Изменения collector / склейка трафика без HA Sync Group
- Прокси-узел + агент / NOC real IP (этап 07 в `docs/plans/multi-remote-hosts/07-proxy-node.md`)

## Подход

**Patch-on-delivery:** файл на диске остаётся «как сделал AntiZapret»; панель патчит содержимое только при выдаче клиенту.

Альтернативы (отклонены): перепись файлов на диске (ломается `setup.sh` / HA); полные шаблоны в панели (устаревают после update AZ).

## Архитектура

```
Админ (UI) → PUT /api/nodes/{id}/remote-hosts → nodes.openvpn_remote_hosts
Клиент скачивает .ovpn → read_profile_file_for_delivery → apply_openvpn_remote_hosts → multi-remote
```

| Компонент | Ответственность |
|-----------|-----------------|
| `openvpn_remote_hosts.py` | validate / normalize / apply патч |
| колонка `Node.openvpn_remote_hosts` | хранение списка per-node |
| GET/PUT `/api/nodes/{id}/remote-hosts` | admin CRUD списка |
| `read_profile_file_for_delivery` | единая точка патча на всех каналах выдачи |
| UI «Адреса подключения» | список ↑↓ в Конфиг AntiZapret |

## Модель данных

Колонка `nodes.openvpn_remote_hosts` — Text/JSON, nullable.

| Значение | Поведение |
|----------|-----------|
| `null` или `[]` | патч выключен; API отдаёт `hosts: []` |
| непустой JSON-массив строк | порядок = приоритет OpenVPN |

Ensure/migration в `database.py` по принятому в проекте стилю.

Список **не** писать в `/root/antizapret/setup` как multi-list (сотрёт `setup.sh`).

## Сервис патча

Модуль `backend/app/services/openvpn_remote_hosts.py`:

| Функция | Поведение |
|---------|-----------|
| `validate_host(s)` | IPv4 или hostname; без пробелов и опасных символов; ошибка с русским текстом |
| `normalize_hosts(list\|None)` | trim; пустые убрать; **макс 8**; дубликат → ошибка; `None`/`[]` → `[]` |
| `apply_openvpn_remote_hosts(content, hosts)` | см. алгоритм |

### Алгоритм `apply`

1. `hosts` пуст → вернуть `content` без изменений.
2. Найти все строки `remote <host> <port> [proto]`.
3. Нет таких строк → вернуть `content`.
4. Запомнить уникальные пары `(port, proto)` в порядке первого появления.
5. Удалить все remote-строки.
6. Вставить: для каждого host из списка × каждая пара `(port, proto)`.
7. Не трогать PEM, `setenv`, cipher и т.д.
8. Повторный apply с теми же hosts → тот же текст.

Порты **не** хранятся в БД — всегда из текущего файла (после update AZ набор портов может измениться).

## API

Только **admin**:

| Method | Path | Тело / ответ |
|--------|------|----------------|
| GET | `/api/nodes/{node_id}/remote-hosts` | `{ "hosts": [...] }` |
| PUT | `/api/nodes/{node_id}/remote-hosts` | `{ "hosts": [...] }` (+ опционально `warnings`) |

### PUT

1. `normalize_hosts` → 400 с русским `detail` при ошибке.
2. Сохранить в колонку.
3. Если hosts **непуст** — best-effort `update_antizapret_settings({ openvpn_host: hosts[0] })`; ошибка setup **не** откатывает список в БД; в ответе `warnings: [...]`.
4. Если hosts **пуст** — **не трогать** `OPENVPN_HOST` (оставить как есть; патч просто выключается).
5. `action_log`.
6. 404 нет узла; 403 не admin.

## Выдача профилей

Обёртка `read_profile_file_for_delivery(...)` (имя может уточняться при реализации, смысл один):

1. `raw = adapter.read_profile_file(path)`
2. Если не `.ovpn` → `raw`
3. Загрузить `openvpn_remote_hosts` для `VpnConfig.node_id` (узел конфига)
4. `return apply_openvpn_remote_hosts(raw, hosts)`

**Подключить:** web download, QR, Telegram send, Mini App, public/one-time links.

**Не патчить:**

- чтение `.ovpn` ради сертификата / expiry
- HA copy / fingerprint / backup с диска
- WireGuard / AmneziaWG

Пустой список = файл байт-в-байт как на диске.

## UI

Секция **«Адреса подключения»** в **Конфиг AntiZapret** (`AntizapretConfigTab`), для активного узла:

- Список строк (IP или домен): добавить / удалить / ↑ / ↓ (без drag-and-drop в MVP)
- Сохранение через PUT remote-hosts (не смешивать с остальными ключами setup)
- WireGuard host — как сейчас + пометка: «Несколько адресов пока только для OpenVPN»
- OpenVPN host: синхронно показывать `hosts[0]` при непустом списке + пояснение, что первый адрес пишется в `OPENVPN_HOST`

### Подсказки (простым языком)

- Порядок сверху вниз = порядок попыток OpenVPN.
- Адресов сколько нужно (до 8); схема у каждого админа своя.
- Российский прокси ставится отдельно скриптом AntiZapret ([инструкция](https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер)); панель его **не** устанавливает и не запускает.
- Один `proxy.sh` направляет на **один** зарубежный сервер.
- Список хранится в панели и не пропадает при обновлении AntiZapret.
- IP прокси добавьте в `allow-ips.txt` на VPN-сервере.
- Трафик считается на зарубежном VPN, куда подключились; прокси в статистике панели отдельно не учитывается.

## Ошибки и крайние случаи

| Случай | Поведение |
|--------|-----------|
| Дубликат / >8 / bad host | 400, русский detail; БД не менять |
| Setup sync `OPENVPN_HOST` упал | список сохранён; `warnings` в ответе |
| Очистка списка `[]` | патч off; `OPENVPN_HOST` **не** менять |
| Нет строк `remote` в файле | content без изменений |
| Не-admin | 403 |
| Нет узла | 404 |

## Тесты

- Unit `test_openvpn_remote_hosts.py`: один host×3 порта → три hosts дают 9 remote; udp+tcp; пустой hosts; нет remote; PEM/FRIENDLY_NAME целы; идемпотентность; дубликат/9-й/плохой host → ошибка.
- API: PUT→GET; 400/403/404; `[]`; мок sync `hosts[0]`.
- Delivery: мок файла + hosts → download с remote всех hosts; без hosts → как мок; WG без изменений.

## Документация и приёмка

Обновить:

- `docs/antizapret-config.md` — раздел «Несколько адресов подключения»
- при необходимости: фраза в `traffic-monitoring.md` / `NodeSync.md`
- `docs/PROJECT_MAP.md` при новых API/секциях
- `CHANGELOG.md`
- статус в `docs/plans/multi-remote-hosts/README.md`

Ручная приёмка (минимум):

- [ ] Один узел, список из 1–3 адресов → download отражает порядок
- [ ] Очистить список → файл как у AZ; `OPENVPN_HOST` не сброшен панелью
- [ ] Два узла без HA, разные порядки
- [ ] При наличии стенда — с HA Sync Group
- [ ] Сценарий «прокси + server1 + server2»

## Связь с существующим планом

Этапы реализации по смыслу совпадают с `docs/plans/multi-remote-hosts/01`…`05`. Этот файл — утверждённый design для Superpowers (writing-plans → SDD). Этап 07 в scope **не** входит.

## Критерий готовности MVP

Админ задаёт список на узле → скачивает `.ovpn` с нужными `remote` по порядку со всех каналов выдачи; очистка списка возвращает выдачу к стоковому файлу без изменения `OPENVPN_HOST`; unit/API/delivery-тесты зелёные; user docs + CHANGELOG обновлены.
