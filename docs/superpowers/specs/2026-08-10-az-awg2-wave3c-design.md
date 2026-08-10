# AZ-AWG2 — волна 3c (access block + deep stats)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [wave3](2026-08-10-az-awg2-wave3.md)  
**Зависит от:** волны 1–2; 3a/3b не блокируют, но UI block на тех же карточках клиентов

## Цель

Паритет блокировок клиентов AWG2 со стоковым WireGuard и детальная статистика клиента (daily + geo через GeoIP панели).

## В scope

- Temp / permanent / unblock для `amneziawg2`
- Runtime через `awg set <iface> peer <pubkey> remove` и restore через syncconf/apply
- Отдельное хранение policy (не смешивать peers со стоковым WG)
- HA: policy replicate + reapply runtime на replica
- `GET /api/awg2/clients/{name}/stats` — daily + endpoint + geo
- UI drawer на Мониторинг / карточке клиента

## Не цели

- Новый geo-провайдер (только `geoip_local` / существующий `ip_geo`)
- Connection history UI как полный клон бота az-awg2
- Block из Telegram (веб sufficient)

## Access / block

### Runtime module

- `backend/app/services/awg2_runtime.py` (зеркало `wg_runtime.py`):
  - collect peers for `client_name` from `/etc/amnezia/amneziawg/{antizapret-awg,vpn-awg}.conf` (имена iface из `services.env`)
  - `block_client_runtime` → `awg set … peer … remove`
  - `unblock_client_runtime` → syncconf/apply from on-disk conf for affected ifaces

### Policy

- Предпочтительно: таблица `amneziawg2_access_policies` (client_name, node_id, mode, until, …) **или** обобщение access_policy с `vpn_family='amneziawg2'`
- Не использовать `WgAccessPolicy` строки для AWG2 имён вслепую (разные iface/conf)

### API

| Метод | Путь |
|-------|------|
| POST | `/api/client-access/amneziawg2/temp-block` |
| POST | `/api/client-access/amneziawg2/permanent-block` |
| POST | `/api/client-access/amneziawg2/unblock` |
| GET | `/api/client-access/amneziawg2/status` (optional list) |

Admin only; feature `awg2` required.

### HA

- После block/unblock на primary: replicate policy row + invoke runtime on replica (if installed)
- Crypto sync must not wipe policy DB; runtime reapply after import if client blocked

### UI

- Actions на `/awg2` Clients и Dashboard card для `amneziawg2` — те же UX labels, что WG

## Deep stats

### API

`GET /api/awg2/clients/{name}/stats`

```json
{
  "name": "ivan",
  "online": true,
  "endpoint": "1.2.3.4:12345",
  "handshake_age_s": 12,
  "rx_life": 0,
  "tx_life": 0,
  "daily": [{"day": "2026-08-10", "rx": 0, "tx": 0}],
  "geo": {"city": "…", "country": "…", "isp": "…"} | null
}
```

- Данные: `awg_stats.py client <name>` + live dump fallback
- Geo: `lookup_geo_local(endpoint_ip)` / panel geo helper; null if DB missing

### UI

- Click row in Monitoring → drawer with daily chart/table + geo
- Optional link from client list

## Тесты

- block removes peer via mocked `awg`; unblock restores
- policy isolation from WG clients same name on stock
- HA reapply invoked
- stats endpoint parses overview/client; geo null without DB
- feature toggle guards access routes

## Критерии готовности 3c

1. Temp/permanent/unblock AWG2 работает на primary; conf на диске сохраняется.  
2. Replica с слоем отражает block после sync/reapply.  
3. Client stats drawer показывает daily; geo заполняется при наличии MMDB.  
4. Сток WG access без регрессий.
