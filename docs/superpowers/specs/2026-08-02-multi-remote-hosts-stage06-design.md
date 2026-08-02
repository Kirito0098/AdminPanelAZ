# Multi-remote hosts — этап 06 (диск, WG delivery, allow-ips)

**Дата:** 2026-08-02  
**Статус:** implemented  
**Ветка:** `feature/multi-remote-hosts`  
**Зависит от:** MVP 01–05 (`docs/superpowers/specs/2026-08-02-multi-remote-hosts-design.md`)  
**Продуктовый черновик:** `docs/plans/multi-remote-hosts/06-opcionalno.md`  
**Не входит:** этап 07 (прокси-узел) — отдельный design/SDD после 06.

## Цель

Три опции поверх MVP multi-remote:

| Код | Поведение |
|-----|-----------|
| **06a** | После пересборки профилей (`recreate_profiles` / `client.sh 7` из панели) — пропатчить `.ovpn` **на диске** списком `openvpn_remote_hosts` узла |
| **06b** | При **выдаче** WG/Amnezia — `Endpoint = hosts[0]` (порт из исходной строки); на диск не писать |
| **06c** | Кнопка: добавить **только первый** host списка в `allow-ips.txt` VPN-узла (идемпотентно) |

## Решения владельца

- 06a: только после recreate/`client.sh 7` из панели — **не** при каждом PUT remote-hosts
- 06b: только patch-on-delivery (не запись WG на диск)
- 06c: только `hosts[0]` (типичный RUS-прокси)
- Подход: расширить текущий multi-remote стек (не отдельные пайплайны)

## Не цели

- Этап 07: прокси-узел, агент, склейка NOC, feature toggle proxy
- Установка / запуск `proxy.sh` из панели
- Запись multi-Endpoint / WG на диск
- Авто-добавление всех hosts в allow-ips
- Изменения traffic collector

## Архитектура

```
recreate_profiles(node) ──► patch_openvpn_profiles_on_node(adapter, hosts)
delivery(.ovpn)         ──► apply_openvpn_remote_hosts (уже MVP)
delivery(WG/AWG)        ──► apply_wireguard_endpoint_host(content, hosts[0])
UI кнопка allow-ips     ──► POST …/remote-hosts/allow-first → allow-ips.txt
```

## 06a — патч `.ovpn` на диске

### Функция

`patch_openvpn_profiles_on_node(adapter, hosts: list[str]) -> dict` (счётчики / warnings):

1. Если `hosts` пуст → no-op, return.
2. Найти клиентские `.ovpn` на узле (через существующие API адаптера: список профилей / обход `client/openvpn/…` — как принято в коде, без хардкода контроллерных путей вне adapter).
3. Для каждого файла: `read` → `apply_openvpn_remote_hosts` → `write_profile_file`.
4. Ошибка на одном файле → warning, продолжить остальные (best-effort).

### Когда вызывать

**После успешного** `adapter.recreate_profiles()` на том же узле, во всех путях панели, которые инициируют пересборку, в том числе:

- `settings.recreate_profiles`
- CIDR / background tasks с `recreate_profiles`
- `node_sync.shared_domain` (после recreate на member)
- csv-import batch с `client.sh 7`
- `openvpn_profile_repair`

**Не вызывать:**

- HA Push full / restore, где `client.sh 7` **намеренно пропущен**
- PUT remote-hosts (список меняется только в БД + optional OPENVPN_HOST)

Пустой список на узле → recreate без disk-patch.

Ошибка disk-patch **не** откатывает уже выполненный recreate; отразить в логе / `warnings` ответа где уместно.

## 06b — WG/Amnezia Endpoint при выдаче

Расширить `read_profile_file_for_delivery(adapter, path, hosts)`:

1. `.ovpn` — как MVP (`apply_openvpn_remote_hosts`).
2. Если путь выглядит как WG/Amnezia (суффикс `.conf` и/или сегменты `wireguard` / `amneziawg` — согласовать с `vpn_profile_visibility`) **и** `hosts` непуст:
   - Найти строку `Endpoint = …` (регистр/пробелы устойчиво).
   - Сохранить порт из исходного Endpoint (после последнего `:` у host-части; для `[ipv6]:port` — вне MVP IPv6 remote hosts уже отклонены, но парсер порта должен не ломать обычный `host:port`).
   - Заменить на `Endpoint = {hosts[0]}:{port}`.
3. Нет строки Endpoint / пустой hosts → content без изменений.
4. Не патчить server configs, cert/HA/backup reads.

Вынести чистую функцию `apply_wireguard_endpoint_host(content: str, host: str) -> str` рядом с openvpn helpers (тот же модуль или `wireguard_remote_hosts.py` — один файл допустим, если маленький).

## 06c — кнопка allow-ips

### API

`POST /api/nodes/{node_id}/remote-hosts/allow-first` — admin only.

Поведение:

1. Загрузить `openvpn_remote_hosts`; если пусто → 400 «Сначала задайте адреса подключения».
2. `first = hosts[0]` (уже нормализованный).
3. Прочитать `allow-ips.txt` через adapter / file editor path для **этого** узла.
4. Если `first` уже есть как отдельная строка → 200 `{ "added": false, "host": first, "detail": "уже есть" }`.
5. Иначе дописать строку, сохранить; применить тот же post-save, что редактор файлов для allow-ips (`parse.sh ip` / apply), если такой шаг уже есть в панели — не изобретать новый пайплайн.
6. `action_log`; ответ `{ "added": true, "host": first }`.

### UI

В секции «Адреса подключения» (`AntizapretConfigTab`): кнопка вроде «Добавить первый адрес в allow-ips» (активна при непустом **сохранённом** списке). Toast по результату. Подсказка: обычно это IP российского прокси; панель не ставит `proxy.sh`.

## Ошибки и крайние случаи

| Случай | Поведение |
|--------|-----------|
| 06a hosts пуст | recreate без disk patch |
| 06a write fail на файле | warning, остальные файлы продолжить |
| 06b нет Endpoint | raw content |
| 06c пустой список | 400 |
| 06c дубликат | 200 added=false |
| setup.sh снова | диск снова сток до следующей пересборки из панели — описать в docs |

## Тесты

- Unit: `apply_wireguard_endpoint_host` (порт, пустой, нет Endpoint)
- Unit/integration-mock: disk patch вызывается после recreate; пустой hosts → write не зовётся
- API/mock: allow-first add / duplicate / empty list
- Regression: OpenVPN delivery tests остаются зелёными

## Документация

- `docs/antizapret-config.md` — три поведения + риски HA/`setup.sh`
- `docs/PROJECT_MAP.md` — новый endpoint / хук
- `CHANGELOG.md`
- Статус в design: после реализации → `implemented`

## Критерий готовности

Пересборка профилей → `.ovpn` на диске с multi-remote при непустом списке; скачивание WG/AWG с Endpoint=`hosts[0]`; кнопка добавляет первый host в allow-ips без дубликатов; тесты зелёные; docs обновлены.

## Следующий шаг после 06

Отдельный Superpowers-цикл (design → plan → SDD) для этапа **07** по `docs/plans/multi-remote-hosts/07-proxy-node.md`.
