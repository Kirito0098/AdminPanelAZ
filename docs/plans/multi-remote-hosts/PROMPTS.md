# PROMPTS: реализация multi-remote hosts

Копируй промпт целиком в агент. Спека: [SPEC.md](SPEC.md). Не пропускай этапы и не смешивай несколько prompts в одном заходе без необходимости.

Общий контекст для всех промптов:

> Репозиторий AdminPanelAZ. Фича «несколько адресов подключения (multi-remote)» для OpenVPN-профилей AntiZapret: упорядоченный список хостов **на узел** в БД панели (`nodes.openvpn_remote_hosts`), патч строк `remote` при выдаче файла (download / QR / Telegram / public link), без правки `/etc/openvpn/client/templates/` (их затирает `setup.sh` upstream AntiZapret-VPN). MVP — только OpenVPN. Не добавлять установку `proxy.sh`. Подробности — `docs/plans/multi-remote-hosts/SPEC.md`.

---

## Prompt 1 — Сервис патча + unit-тесты

```
Реализуй ядро патча OpenVPN multi-remote по docs/plans/multi-remote-hosts/SPEC.md §4 (только сервис + тесты, без API/UI и без колонки Node).

Сделай:
1. Модуль backend/app/services/openvpn_remote_hosts.py с функциями:
   - normalize_hosts(hosts) -> list[str] (trim, reject empty/invalid, max 8, optional dedupe)
   - validate_host(host) -> bool или raise ValueError с понятным русским текстом
   - apply_openvpn_remote_hosts(content: str, hosts: list[str] | None) -> str
2. Алгоритм apply (§4.2 SPEC): извлечь (port, proto) из существующих remote-строк; удалить remote; вставить host × ports в порядке hosts; PEM и прочее не трогать; пустой hosts/None → content unchanged; нет remote в файле → unchanged.
3. Unit-тесты на фикстурах, близких к шаблонам AZ:
   - antizapret-udp (3 remote одного host)
   - antizapret (udp+tcp remote)
   - три хоста → 3×N remote в правильном порядке
   - идемпотентность второго apply
   - FRIENDLY_NAME / <ca> блок сохранены
4. Не вызывай client.sh, не пиши на диск, не меняй frontend.

В конце кратко опиши сигнатуры и примеры тестов.
```

---

## Prompt 2 — Модель Node + API

```
Продолжи multi-remote (docs/plans/multi-remote-hosts/SPEC.md §3, §5). Сервис apply_openvpn_remote_hosts уже есть.

Сделай:
1. Колонку nodes.openvpn_remote_hosts (Text/JSON nullable) + ensure/migration в database.py в стиле проекта.
2. Admin API: GET и PUT списка для узла (например /api/nodes/{id}/remote-hosts или согласованный путь рядом с nodes). Тело: { "hosts": ["a","b","c"] }; пустой массив или null = выключить патч.
3. Валидация через normalize/validate из сервиса; 400 с detail на русском; 403 для non-admin; 404 неизвестный node.
4. action_log при успешном PUT.
5. Опционально при PUT: если hosts непуст — записать OPENVPN_HOST=hosts[0] в setup узла через существующий update_antizapret_settings (или отдельный query-флаг sync_setup_host=true). Зафиксируй выбранное поведение в комментарии/доке к эндпоинту.
6. Тесты API: write/read, invalid host, empty list, non-admin.

Не подключай ещё download-пути и UI (можно только типы schemas).
```

---

## Prompt 3 — Patch-on-delivery на всех путях выдачи

```
Подключи apply_openvpn_remote_hosts ко всем путям выдачи .ovpn (SPEC §4.1). Модель и API списка уже есть.

Сделай:
1. Единую точку: после read_profile_file (или обёртка), если файл OpenVPN (.ovpn) и у node_id конфига/активного узла есть openvpn_remote_hosts — прогнать apply.
2. Покрыть: web download, QR payload, Telegram send, Mini App download, public_download / one-time links.
3. Не патчить WireGuard/AmneziaWG в этом шаге.
4. Не писать результат обратно на диск узла (MVP — только delivery).
5. Тесты: при заданном списке download API возвращает remote для всех hosts; при null — байты/текст как на «диске» (мок read_profile_file).
6. Следи, чтобы HA/cert helpers, которые читают .ovpn только ради PEM (openvpn_cert), не ломались: либо не патчить в этих путях, либо патч не трогает PEM (уже так) — предпочти читать raw с диска для expiry.

Не делай UI списка хостов в этом шаге.
```

---

## Prompt 4 — UI «Адреса подключения»

```
Добавь админский UI для multi-remote по SPEC §2 в Конфиг AntiZapret (AntizapretConfigTab / секция «Адреса подключения»).

Сделай:
1. Упорядоченный список хостов OpenVPN для активного узла: добавить, удалить, вверх/вниз (или dnd если в проекте уже есть).
2. Загрузка/сохранение через API remote-hosts; не путать с PUT antizapret-settings setup-ключей (можно сохранять одной кнопкой секции, но два вызова API — ок).
3. Подсказка про proxy.sh и что список переживает обновление AntiZapret.
4. Поле openvpn_host (setup) оставь видимым или покажи, что первый хост списка синхронизируется в OPENVPN_HOST — в соответствии с поведением Prompt 2.
5. WireGuard: оставь одиночное поле + короткая пометка «multi-remote в MVP только для OpenVPN».
6. types + api/client.ts; не ломай остальной AntizapretConfigTab (флаги, doall apply).

После — кратко: куда кликать, чтобы задать RUS → Server1 → Server2 на узле A.
```

---

## Prompt 5 — Документация и CHANGELOG

```
Закрой поставку multi-remote документацией (код UI/API/патч уже вмержен).

Сделай:
1. docs/antizapret-config.md — раздел «Несколько адресов подключения»: сценарий RU-прокси + 2 сервера, что панель не ставит proxy.sh, что не надо править templates на диске, переживает setup.sh.
2. При необходимости одна строка в docs/uzly.md или NodeSync.md: per-node список, patch-on-delivery, HA byte-copy на диске без multi-remote.
3. CHANGELOG.md — Added/Changed пользовательским языком.
4. Обнови статус в docs/plans/multi-remote-hosts/README.md на «реализовано (дата)» если всё из MVP §10 этапы 1–4 готово; отметь что этап 5–6 опциональны.

Не начинай rewrite-on-disk (этап 5) в этом промпте.
```

---

## Prompt 6 (опционально) — Rewrite-on-disk

```
Опциональная фаза SPEC §4.3 / этап 5: после recreate_openvpn_profiles (client.sh 7) переписать .ovpn на диске узла с multi-remote.

Только если явно просят:
1. Флаг на узле или query «persist_remotes_on_disk».
2. После client.sh 7: для каждого .ovpn клиента apply + write обратно через безопасный API агента.
3. Предупреждение в UI про HA: byte-copy primary→replica разъедется; после Push full нужен persist на каждой replica своим списком.
4. Тесты + docs caveat.

Не делай без отдельного запроса владельца продукта.
```

---

## Prompt 7 (опционально) — WG Endpoint = hosts[0]

```
Опционально SPEC §4.4 вариант 2: при выдаче WG/AWG подставлять Endpoint host из openvpn_remote_hosts[0] (или отдельного wireguard списка), порт сохранить из файла.

Тесты + пометка в antizapret-config.md. Не эмулировать несколько Endpoint.
```

---

[← README плана](README.md)
