# AZ-AWG2 — NOC + мониторинг трафика (волны 4a / 4b)

**Дата:** 2026-08-11  
**Статус:** draft  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**Подход:** третий протокол рядом с OpenVPN / WireGuard (не вливать в WG)  
**Зависит от:** волны 1–3c (особенно `get_awg2_monitoring`, access block runtime, HA crypto для AWG2)

## Решения владельца

| Тема | Выбор |
|------|--------|
| Модель | Отдельный протокол `amneziawg2` везде (NOC, traffic, history, TG) |
| Поверхности | Страницы NOC + traffic **и** TG NOC text/PNG **и** connection-history |
| Лимиты | Полный паритет с WG (set/clear + auto-block при exceed) |
| Поставка | Две волны: **4a** NOC/history/TG → **4b** traffic collector + limits |
| Гейт | `FEATURE_AWG2_ENABLED`; на узле слой установлен; иначе no-op / пустые списки |
| Traffic page | Только когда feature мониторинга трафика включён (как сейчас для OVPN/WG) |

## Общие правила (обе волны)

1. UI-имя протокола: **AWG 2.0** / **AmneziaWG 2.0** (как в Dashboard); модуль по-прежнему **AZ-AWG2**.  
2. Не писать peers AWG2 в стоковый `wireguard_peers` / `protocol_type=wireguard`.  
3. Toggle off → бинарная совместимость ответов/UI с pre-4a (лишние поля могут быть `0`/`[]`, но фильтры/серии AWG2 скрыты).  
4. Adapter/not-installed/ошибка → пустой список AWG2, без 500 из overview/collector.  
5. Online: handshake age &lt; **180s** (`AWG2_ONLINE_WINDOW_S`), как на `/awg2` Monitoring.  
6. Источник live peers: `adapter.get_awg2_monitoring()` (stats.db overview или `awg show dump` fallback).

---

## Волна 4a — NOC + connection-history + TG

**План (после утверждения spec):** `docs/superpowers/plans/2026-08-11-az-awg2-wave4a.md`

### Цель

Когда AWG2 включён и установлен, оператор видит online AWG 2.0 в NOC Мониторинг, на графиках истории подключений и в Telegram NOC-сводках.

### В scope

- `monitoring_overview` (+ federated / HA dedupe path):  
  - `amneziawg2_peers` (форма близка к WG peer / monitoring client: name, endpoint, handshake, rx/tx, online, geo, via_proxy)  
  - `connected_amneziawg2` на node summary  
  - `total_connected_amneziawg2` на overview / global dashboard summary  
- Proxy enrich для AWG2 endpoints (тот же match, что для WG), если `proxy_nodes` on  
- `connection_count_samples.amneziawg2_count` + collector/worker  
- API history charts: третья серия  
- NOC UI: фильтр протокола `amneziawg2`, счётчики, список, charts  
- Node cards / federated summary: третий счётчик  
- TG NOC text + weekly PNG: текущие и peak concurrent для AWG2  
- Docs: `docs/noc-monitoring.md` (+ кратко epic/CHANGELOG Unreleased)  
- Тесты: toggle off; installed online count; not installed empty; history column; report formatting

### Не цели (4a)

- Traffic collector / `UserTrafficSample` / сброс  
- Traffic limits / колонки в `amneziawg2_access_policies`  
- Переделка вкладки `/awg2` Monitoring  
- Изменение поведения стокового OVPN/WG кроме shared chart layout

### Архитектура (4a)

```
FEATURE_AWG2_ENABLED?
  no  → overview/history/TG без AWG2 (как сейчас)
  yes → per VPN node:
          health/installed?
            no  → peers=[], counts=0
            yes → get_awg2_monitoring()
                  → map clients → amneziawg2_peers
                  → online = handshake < 180s
                  → proxy + geo enrich (как WG)
connection_history worker:
  same gate → sample amneziawg2_count
noc_report / weekly image:
  aggregate connected + peaks (history/sessions) including amneziawg2
```

### Схема / API (4a)

| Место | Изменение |
|-------|-----------|
| `MonitoringOverview` / node summary / `GlobalDashboardSummary` | `amneziawg2_peers`, `connected_amneziawg2`, `total_connected_amneziawg2` |
| `ConnectionCountSample` | `amneziawg2_count` (migration, default 0) |
| History API points | поле `amneziawg2` (или эквивалент) |
| TG summary payload | `total_amneziawg2`, peaks, per-node |

HA dedupe: отдельный ключ протокола `amneziawg2` (не смешивать с `wireguard`), по аналогии с существующим HA aggregate для OVPN/WG.

### UI (4a)

- `ProtocolFilter`: `all` \| `openvpn` \| `wireguard` \| `amneziawg2`  
- Фильтр и серии графиков AWG2 **только если** `isEnabled('awg2')`  
- Подписи: «AWG 2.0» коротко в чипах/карточках

### Критерии готовности (4a)

1. Toggle off → NOC/TG/history визуально и по смыслу как pre-4a.  
2. Toggle on + installed + online peer → peer в overview, filter, history sample &gt; 0, TG отражает.  
3. Not installed / adapter error → пустые peers/counts, overview не 500.  
4. Proxy via_proxy enrich работает для AWG2 endpoint при включённых proxy nodes.

---

## Волна 4b — Traffic monitoring + limits

**План (после 4a):** `docs/superpowers/plans/2026-08-11-az-awg2-wave4b.md`  
**Зависит от:** 4a (желательно) + traffic feature + AWG2 access runtime (3c)

### Цель

При включённом мониторинге трафика AWG 2.0 учитывается как `protocol_type=amneziawg2` с паритетом WG, включая лимиты и auto-block.

### В scope

- Traffic collector/worker: online AWG2 clients → status rows → persist с `protocol_type=amneziawg2`  
- Chart / table / sessions / maintenance reset: scope `amneziawg2` (+ `all`)  
- HA Sync Group aggregate для `amneziawg2` (как WG), если узел в группе  
- Migration: `traffic_limit_bytes`, `traffic_limit_period_days` на `amneziawg2_access_policies`  
- `access_policy`: traffic state + reconcile `block_mode=traffic_limit` → existing AWG2 runtime block/unblock  
- API set/clear traffic limit для AWG2 (зеркало WG endpoints)  
- UI: TrafficPage бейджи/фильтр/сброс/график; ClientActionsDialog / config cards / policy display  
- Consume bytes из traffic stats по `(client, amneziawg2)`  
- Docs: `docs/traffic-monitoring.md`, CHANGELOG Unreleased  
- Тесты: collect protocol; reset scope; limit exceed → block; clear → unblock; toggle/traffic-off gates

### Не цели (4b)

- Менять `/awg2` Monitoring tab (кроме при необходимости ссылок/docs)  
- Новый geo-провайдер  
- Лимиты из Telegram-бота (веб + существующие policy surfaces достаточны, если Mini уже показывает WG limits — добавить AWG2 display)

### Архитектура (4b)

```
traffic worker (traffic feature on):
  per node:
    if awg2 enabled+installed:
      clients = get_awg2_monitoring() online
      build_status_rows(..., awg2_clients) → protocol_type=amneziawg2
    persist_snapshot

access_policy (amneziawg2):
  consumed = get_client_consumed_traffic_bytes(..., protocol amneziawg2)
  resolve_traffic_limit_state → if exceeded: block_reason=traffic_limit + runtime block
  set/clear limit → reconcile

TrafficPage / charts:
  third protocol series + reset scope when awg2 feature on
```

### Критерии готовности (4b)

1. Снапшоты пишут `amneziawg2`; таблица/график/сброс работают при traffic+awg2 on.  
2. Лимит задан → превышение → runtime block; clear/period expiry path → unblock (как WG).  
3. AWG2 toggle off или traffic off → нет новых AWG2 samples / нет UI третьего протокола.  
4. Строки AWG2 не появляются как `wireguard`.

---

## Порядок поставки

| Срез | Spec section | Plan |
|------|--------------|------|
| **4a** | этот файл § Волна 4a | `plans/2026-08-11-az-awg2-wave4a.md` |
| **4b** | этот файл § Волна 4b | `plans/2026-08-11-az-awg2-wave4b.md` |

После merge 4a можно начинать writing-plans для 4b; код 4b не смешивать в один PR с 4a без необходимости.

## Риски

| Риск | Митигация |
|------|-----------|
| Двойной учёт если имя клиента совпадает с WG | Разные `protocol_type` / отдельные peer lists |
| stats.db vs dump расхождение online | Тот же fallback, что `/api/awg2/monitoring` |
| Рост размера overview | Toggle gate; тот же объём, что `/api/awg2/monitoring` |
| History migration на существующих инсталлах | `amneziawg2_count` default 0; старые точки без серии |
| Limit reconcile гонки с temp/permanent block | Зеркало WG: priority permanent/temp vs traffic_limit как в `_wg_state` |
