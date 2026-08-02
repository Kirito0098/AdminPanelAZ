# Proxy nodes — волна 1 (toggle, модель, proxy_agent)

**Дата:** 2026-08-02  
**Статус:** implemented  
**Ветка:** `feature/multi-remote-hosts`  
**Продуктовый черновик:** `docs/plans/multi-remote-hosts/07-proxy-node.md`  
**Зависит от:** multi-remote MVP (+ stage 06 опционально)  
**Волна 2 (отдельно):** склейка NOC / GeoIP по реальному CLIENT_IP

## Цель

Дать админу, который **сам** поставил AntiZapret `proxy.sh` на RU VPS, подключить тонкий `proxy_agent` к панели: health, detect, правка DESTINATION (iptables), API mappings. Модуль скрыт за feature toggle (**default off**). Панель **никогда** не устанавливает и не запускает `proxy.sh`.

## Решения владельца (волна 1)

| Тема | Выбор |
|------|--------|
| Scope | 7.0 + 7.1 + 7.2; NOC → волна 2 |
| Агент | Отдельный `proxy_agent` (не node_agent) |
| Auth | API key (`X-Node-Key`) + optional mTLS; default port **9101** |
| Модель | `nodes.node_kind` ∈ {`vpn`,`proxy`} proxy-поля рядом / metadata |
| Подход | `ProxyNodeAdapter` + отдельный сервис |

## Не цели (волна 1)

- Установка / повторный запуск `proxy.sh` из панели
- Склейка NOC `display_address` / geo по CLIENT_IP (волна 2)
- Изменение учёта трафика на VPN-узлах
- Смешивание VPN API node_agent с прокси-машиной

## Жёсткие правила продукта

1. `proxy.sh` запускает только админ (инструкция AZ).  
2. Панель не ставит и не запускает `proxy.sh`.  
3. Панель только edit/monitor уже установленного прокси.  
4. При выключенном toggle UI/API прокси недоступны.

## Архитектура

```
Admin: proxy.sh on RU (manual)
     → enable feature proxy_nodes
     → create Node(kind=proxy) + install proxy_agent :9101
Panel ProxyNodeAdapter ──HTTP──► proxy_agent
                                 health / status / destination / mappings
```

**DESTINATION edit:** `proxy.sh` применяет **iptables** DNAT/SNAT, не конфиг-файл. Edit = найти текущий destination в nat-правилах и безопасно заменить IP; не вызывать `proxy.sh`.

## 7.0 Feature toggle

| Field | Value |
|-------|--------|
| key | `proxy_nodes` |
| env_key | `FEATURE_PROXY_NODES_ENABLED` |
| default | **false** |
| group | `app_module` |
| label | Прокси-узлы |

Пока off:

- Нет UI «добавить прокси», бейджей, карточек edit
- Create/update proxy-kind и proxy-only routes → feature guard (как другие модули)

Docs: включать только если уже используете `proxy.sh`.

## 7.1 Модель данных

Расширить `nodes`:

| Column / field | Meaning |
|----------------|---------|
| `node_kind` | `vpn` (default) \| `proxy` |
| port default for proxy | **9101** |
| `destination_ip` | optional cached/last-known DESTINATION (IPv4 string) |
| `linked_vpn_node_id` | optional FK to vpn node |

Rules:

- Proxy nodes: `is_local=false`
- `get_active_node` / activate / VPN config ops: only `node_kind=vpn`
- Creating `node_kind=proxy` requires toggle on
- Reuse existing api_key / mtls_enabled patterns

Migration: add `node_kind` VARCHAR default `'vpn'`; backfill existing rows as `vpn`.

## 7.2 proxy_agent

Package: `backend/proxy_agent/` (FastAPI), systemd unit docs/script for RU host.

Auth: `X-Node-Key` required; optional mTLS env like node_agent.

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/health` | `{ ok, version }` |
| GET | `/proxy/status` | `{ installed: bool, destination_ip: str\|null, detail?: str }` — detect iptables/proxy traces; no auto-install |
| PUT | `/proxy/destination` | body `{ destination_ip }` — rewrite DNAT/SNAT targets; validate IPv4; return new status |
| GET | `/proxy/mappings` | list of `{ client_ip, client_port?, proxy_sport?, dest_ip?, dest_port? }` from conntrack (best-effort); empty if unavailable |

Capabilities in wave 1 UI: health, status, edit destination. Mappings exposed via panel proxy API for wave 2; optional raw view in wave 1 is OK if cheap.

**Privileges:** agent needs rights to read/update nat table (document CAP_NET_ADMIN / root — follow project security norms; minimal scope).

## Panel adapter & API

- `ProxyNodeAdapter(host, port, api_key, mtls…)` wrapping agent HTTP
- Admin routes (behind toggle), e.g.:
  - CRUD nodes with `node_kind=proxy` (extend existing nodes API carefully)
  - `GET/PUT /api/nodes/{id}/proxy/status|destination`
  - `GET /api/nodes/{id}/proxy/mappings`
- 404 if node is not proxy; 403 if toggle off

## UI

When toggle on:

- Modules: switch «Прокси-узлы» + short warning
- Nodes page: add proxy node; badge «Прокси»; **no** Activate for VPN configs
- Proxy card: health, installed/not + AZ instruction link, DESTINATION field + save

When toggle off: all of the above hidden.

No «Install proxy.sh» button ever.

## Agent install (docs)

Short Russian doc: install `proxy_agent` systemd on RU **after** manual `proxy.sh`; generate API key in panel; open port 9101; optional mTLS. Separate from AntiZapret VPN node_agent install.

## Testing

- Toggle off → create proxy → 403/feature blocked
- Activate proxy node → rejected
- Adapter mocks: health, status installed/false, destination put
- Unit: DESTINATION iptables rewrite with fixtures (no live net)
- Mappings JSON shape when conntrack mocked empty/non-empty
- VPN active-node / traffic paths unchanged for `vpn` nodes

## Documentation

- `docs/uzly.md` — прокси-узлы vs multi-remote IP list
- `docs/PROJECT_MAP.md` — toggle, model, proxy_agent, APIs
- `CHANGELOG.md`
- Link to [Настроить прокси-сервер](https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер)

## Acceptance (wave 1)

- [ ] Toggle default off → proxy UI/API unavailable
- [ ] Toggle on → add proxy node, health check
- [ ] No install-proxy.sh affordance
- [ ] Agent without proxy rules → installed=false + AZ link
- [ ] Edit DESTINATION updates iptables via agent (lab/mock)
- [ ] Mappings endpoint returns structured data (possibly empty)
- [ ] Cannot activate proxy as VPN active node
- [ ] VPN traffic accounting unchanged

## Wave 2 (out of this spec)

NOC: if session `real_address` belongs to known proxy → lookup mappings → `display_address` + geo by CLIENT_IP; fallback + «через прокси» if missing; only when toggle on and proxy online.

## Критерий готовности волны 1

Toggle + model + proxy_agent + adapter + UI edit/monitor shipped and tested; docs warn that `proxy.sh` is admin-only; ready to start wave 2 NOC design.
