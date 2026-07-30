# SPEC: несколько адресов подключения (multi-remote)

Техническая и продуктовая спецификация. Реализация — отдельно, по [PROMPTS.md](PROMPTS.md).

Upstream: [GubernievS/AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN) (`OPENVPN_HOST`, шаблоны `/etc/openvpn/client/templates/`, `proxy.sh`).

---

## 1. Проблема

| Сейчас | Нужно |
|--------|--------|
| Один `openvpn_host` / `wireguard_host` на узел в setup AZ | Упорядоченный список хостов (2–N) на узел |
| Все `remote` в `.ovpn` — один и тот же хост, разные порты | Блоки `remote` для **каждого** хоста (порты как в шаблоне AZ) |
| HA / `client.sh 7` пишут файлы as-is с диска | Выдача из панели учитывает список узла |
| Ручной edit шаблонов слетает после `setup.sh` | Настройки живут в панели и переживают update AZ |

Мотивация пользователя: RU-прокси (`proxy.sh`) + два зарубежных сервера; приоритет «свой» сервер вторым после RU, чужой — третьим.

---

## 2. Продуктовый UX

### 2.1. Где в UI

Расширить блок **Конфиг AntiZapret → Адреса подключения** (сейчас два string-поля в [`AntizapretConfigTab.tsx`](../../../frontend/src/components/routing/AntizapretConfigTab.tsx)):

- **OpenVPN — список хостов** (упорядоченный): домен или IPv4, drag-and-drop или стрелки вверх/вниз, добавить / удалить.
- Поле «основной» `OPENVPN_HOST` в setup AZ: синхронизировать с **первым** элементом списка (или отдельный toggle «писать первый хост в OPENVPN_HOST» — см. §4.3).
- Подсказка: «Порядок = приоритет OpenVPN remote. Российский прокси (`proxy.sh`) обычно первым. Список хранится в панели и не пропадает при обновлении AntiZapret.»
- WireGuard / AmneziaWG (MVP): оставить одно поле `WIREGUARD_HOST` **или** показать read-only «для WG используется первый хост списка» + disclaimer.

Активный узел в шапке определяет, **чей** список редактируется (как остальные настройки AZ на узел).

### 2.2. Кто может менять

Только **admin**. На HA-replica в режиме, где правки на replica запрещены — тот же 403, что у остальных antizapret-settings (править на primary **или** хранить список **per-node в БД панели**, не в setup AZ — предпочтительно per-node в панели, см. §3).

### 2.3. Что видит пользователь при скачивании

Пользователь / admin скачивает `.ovpn` (web, Mini App, Telegram, one-time / QR) — в файле уже multi-remote в порядке узла, с которого конфиг. QR кодирует тот же контент.

Пользователь **не** редактирует список.

### 2.4. Вне скоупа (явно)

- Установка / мониторинг / provisioning `proxy.sh` как узла панели.
- Свободный текстовый редактор шаблонов `/etc/openvpn/client/templates/*`.
- Изменение набора портов AZ (остаются как в шаблоне на диске).
- DNS failover / shared_domain — отдельная фича HA; multi-remote **дополняет**, не заменяет.

---

## 3. Модель данных

### 3.1. Предпочтительное хранение: per-node в БД панели

Не писать multi-list в `/root/antizapret/setup` (setup перезаписывается `setup.sh` и HA-репликацией ключей).

Вариант A (рекомендуется):

| Что | Где |
|-----|-----|
| Список хостов OpenVPN | колонка `nodes.openvpn_remote_hosts` — JSON array строк, порядок = приоритет |
| Список / primary WG | опционально `nodes.wireguard_remote_hosts` или только использовать `[0]` из OVPN-списка для WG Endpoint |

```json
["1.2.3.4", "5.6.7.8", "9.10.11.12"]
```

- `null` или `[]` → поведение как сейчас: один хост из `OPENVPN_HOST` setup (или IP сервера, если пусто) — **без патча**.
- Валидация: 0–N элементов; каждый — IPv4 или hostname (без пробелов, без `remote` keyword); max N например 8; дубликаты запрещены или схлопываются с предупреждением.

Вариант B (хуже): ключ в `AppSetting` с map `node_id → list` — не нужен, если есть колонка на `Node`.

### 3.2. Связь с `OPENVPN_HOST` / `WIREGUARD_HOST`

| Ситуация | Поведение |
|----------|-----------|
| Список пуст | Только setup AZ, как сегодня |
| Список непуст | Патч выдачи по списку; в setup при «Сохранить» можно писать `OPENVPN_HOST = list[0]` для совместимости с `client.sh` (имя файла, FRIENDLY_NAME, стоковые remote до патча) |
| HA shared_domain | Shared domain по-прежнему может писаться в setup всех членов; multi-remote — **отдельный** per-node override для выдачи. Если задан multi-list, он **важнее** одиночного host при патче download |

Конфликт документировать в UI: «При непустом списке скачиваемые OpenVPN-профили используют его, а не только OPENVPN_HOST».

### 3.3. Миграция

- Новая колонка + ensure в `database.py` (стиль проекта).
- Существующие узлы: `null` → без изменения поведения.
- Опциональный one-shot: если `OPENVPN_HOST` непуст — не автозаполнять список (чтобы не менять семантику молча); админ включает явно.

---

## 4. Применение к профилям (ядро)

### 4.1. Принцип: patch-on-delivery

Не полагаться на долгоживущие правки шаблонов на диске узла.

Точки выдачи контента (все должны проходить через один хелпер):

| Поверхность | Якорь |
|-------------|--------|
| Download config file (web API) | routers configs / public download |
| QR | тот же content pipeline |
| Telegram send document | `telegram_config_send.py` → `read_profile_file` |
| Mini App download | `tg_mini` + adapter |
| One-time / public links | `public_download.py` |

Единая функция (черновик API):

```python
def apply_openvpn_remote_hosts(content: str, hosts: list[str] | None) -> str:
    """If hosts empty/None — return content unchanged.
    Else replace remote-lines block according to template port/proto pattern.
    """
```

### 4.2. Алгоритм патча `.ovpn`

Текущий шаблон AZ (пример `antizapret-udp.conf`):

```
remote ${SERVER_HOST} 50443 udp4
remote ${SERVER_HOST} 504 udp4
remote ${SERVER_HOST} 443 udp4
```

После `client.sh` на диске все строки с одним хостом.

**Алгоритм (устойчивый к update AZ):**

1. Прочитать текст профиля.
2. Найти все строки вида `remote <host> <port> [proto]` (regex).
3. Извлечь **уникальный упорядоченный набор (port, proto)** из существующих remote-строк (сохранить порты/протоколы шаблона: backup ports и т.д.).
4. Удалить все найденные `remote …` строки (одним блоком или все вхождения).
5. Вставить новый блок: для каждого `host` из списка панели × каждый `(port, proto)` в том же порядке портов, что был в файле.
6. Не трогать `<ca>`, `<cert>`, `<key>`, `setenv FRIENDLY_NAME`, cipher и пр.
7. Если remote-строк не было — no-op или безопасный fallback (не ломать файл).

Идемпотентность: повторный патч того же списка даёт тот же результат.

### 4.3. Опционально: rewrite-on-disk после `client.sh 7`

Плюсы: SSH/`scp` с сервера тоже получит multi-remote; диск совпадает с выдачей.  
Минусы: ломает **байт-идентичность** `.ovpn` между HA primary/replica (сейчас Push full / crypto sync копируют файлы as-is); после `setup.sh` снова сток, пока панель не перепишет.

**Рекомендация MVP:** только patch-on-delivery.  
**Фаза 2 (opt-in):** «Записать multi-remote на диск узла» после recreate — флаг на узел, с предупреждением про HA.

### 4.4. WireGuard / AmneziaWG

В `.conf` один `Endpoint = host:port`.

MVP варианты (выбрать один в реализации, зафиксировать в CHANGELOG):

1. **Не патчить WG** — только OpenVPN multi-remote.
2. Подставлять `Endpoint` = `list[0]:<port>` (порт из существующей строки Endpoint).

Не пытаться эмулировать failover несколькими Endpoint в одном WG-файле (стандартный клиент не умеет как OpenVPN).

---

## 5. API

Черновик (в стиле проекта):

| Method | Route | Назначение |
|--------|-------|------------|
| GET | `/api/nodes/{id}/remote-hosts` или поле в существующем node/settings | Прочитать список |
| PUT | тот же | Записать список (admin) |
| GET | antizapret-settings | Можно **не** смешивать со setup-ключами; UI грузит remote-hosts отдельно |

Либо расширить ответ `GET /routing/antizapret-settings` полем `openvpn_remote_hosts` из БД панели (не с диска AZ) — удобнее для одного экрана, но чётко разделить в коде: setup keys vs panel-owned.

Валидация на write: 400 с русским detail при невалидном хосте.

Аудит: `action_log` при изменении списка.

---

## 6. HA / Node Sync

| Тема | Решение |
|------|---------|
| Где хранится список | Per-node в БД панели → у primary и replica **разные** порядки — это **желаемо** |
| Репликация setup `OPENVPN_HOST` | Как сейчас; не заменяет multi-list |
| Byte-copy `.ovpn` primary→replica | Без изменений в MVP (патч только на выдаче с активного узла) |
| Скачивание с active node = replica | Патч списком **этого** node_id |
| Push full / Verify | Не сравнивать «ожидаемый multi-remote на диске»; диск может быть стоковым |

Если позже включить rewrite-on-disk — исключить `.ovpn` remote-блок из strict fingerprint или патчить после copy на каждой replica своим списком.

---

## 7. Устойчивость к обновлению AntiZapret

| Событие | Что происходит | Multi-remote |
|---------|----------------|--------------|
| `update.sh` / timer (списки) | Шаблоны обычно не трогает | OK |
| `setup.sh` (полное обновление) | Стирает templates, `client.sh 7` | Список в БД панели цел; следующий download снова патчит |
| `client.sh 7` из панели | Пересоздаёт `.ovpn` из шаблонов | Download патчит; disk rewrite — только если фаза 2 |
| Смена портов backup в setup AZ | Меняется набор remote в шаблоне | Патч берёт port/proto **из текущего файла** — подхватывает новые порты автоматически |

Регрессия, которой избегать: хранить «полный текст шаблона» в панели — устареет при смене AZ. Хранить **только список хостов**.

---

## 8. Затронутые области кода (ориентир)

| Область | Файлы / модули |
|---------|----------------|
| Модель Node | `models.py`, `database.py` ensure |
| Сервис патча | новый `backend/app/services/openvpn_remote_hosts.py` (или рядом с `openvpn_profile_repair.py`) |
| Выдача файлов | `read_profile_file` wrappers / configs download / `public_download` / `telegram_config_send` / tg-mini |
| API | `routers/nodes.py` или `routing` + schemas |
| UI | `AntizapretConfigTab.tsx`, types, `api/client.ts` |
| Тесты | unit патча на фикстурах `.ovpn`; API write/read; download integration |
| Docs | `antizapret-config.md` — раздел «Несколько адресов»; ссылка на proxy.sh upstream |

Якоря текущего одиночного host:

- [`antizapret_params.py`](../../../backend/app/services/antizapret_params.py) — `openvpn_host` / `wireguard_host`
- [`AntizapretConfigTab.tsx`](../../../frontend/src/components/routing/AntizapretConfigTab.tsx) — секция «Адреса подключения»
- AZ: `/etc/openvpn/client/templates/*.conf`, `client.sh` → `setServerHost_FileName "$OPENVPN_HOST"`

---

## 9. Безопасность и ограничения

- Не принимать path traversal / shell metacharacters в host.
- Не выполнять произвольный текст шаблона от пользователя.
- Список виден только admin (GET); в скачанном `.ovpn` хосты **видны клиенту** — это нормально для VPN-профиля.
- Не логировать полный `.ovpn` (есть ключи) при отладке патча — только remote-блок / count.

---

## 10. Этапы поставки

| Этап | Содержание | Критерий готовности |
|------|------------|---------------------|
| **0** | Спека (этот документ) + промпты | Review |
| **1** | Модель + API + unit `apply_openvpn_remote_hosts` | Тесты зелёные |
| **2** | Patch-on-delivery на всех download-путях | Скачанный файл с 3 host |
| **3** | UI список в Конфиг AntiZapret | Админ задаёт порядок per-node |
| **4** | Docs + CHANGELOG; опционально sync `OPENVPN_HOST=list[0]` | Пользовательская инструкция |
| **5** (опц.) | Rewrite-on-disk + HA caveat | Flag в UI |
| **6** (опц.) | WG Endpoint = hosts[0] | Документировано |

---

## 11. Приёмка (чеклист)

### 11.1. Функционал

- [ ] Узел A: список RUS, A, B → download UDP-профиля содержит remote в этом порядке (порты сохранены).
- [ ] Узел B: список RUS, B, A → аналогично.
- [ ] Пустой список → файл как сгенерировал AZ (один host).
- [ ] После имитации «пересоздали профиль» (`client.sh 7`) download из панели снова multi-remote.
- [ ] QR / Telegram / public link отдают тот же патч, что web download.
- [ ] Невалидный host → 400, список не портится.
- [ ] Non-admin → 403 на PUT.

### 11.2. Регрессии

- [ ] HA Push full / verify не краснеют из‑за различия remote на диске (MVP без rewrite).
- [ ] Создание/renew клиента, CSV, templates — download по-прежнему работает.
- [ ] `FRIENDLY_NAME` и PEM-блоки не повреждены патчем.
- [ ] Профиль без строк `remote` не повреждается.

### 11.3. Документация

- [ ] `docs/antizapret-config.md` — как задать RU + два сервера.
- [ ] Явно: панель **не** ставит `proxy.sh`; только адреса в клиентском конфиге.
- [ ] Явно: не править templates на диске ради этой фичи.

---

## 12. Ответ пользователю / Fider (черновик)

> Добавим в «Конфиг AntiZapret» упорядоченный список адресов на каждый узел. В скачиваемых OpenVPN-конфигах будут несколько `remote` в заданном порядке (например RU-прокси → этот сервер → второй). Список хранится в панели, поэтому обновление AntiZapret-VPN с GitHub не сбрасывает настройку. Установку российского `proxy.sh` панель по-прежнему не делает — только подстановку IP в профиль. WireGuard в первой версии — один Endpoint (первый адрес) или без изменений.

---

[← README плана](README.md)
