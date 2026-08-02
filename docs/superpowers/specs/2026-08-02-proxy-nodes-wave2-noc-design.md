# Proxy nodes — волна 2 (склейка NOC)

**Дата:** 2026-08-02  
**Статус:** implemented  
**Ветка:** `feature/multi-remote-hosts`  
**Зависит от:** волна 1 (`docs/superpowers/specs/2026-08-02-proxy-nodes-wave1-design.md`)  
**Продуктовый черновик:** `docs/plans/multi-remote-hosts/07-proxy-node.md` §7.3

## Цель

В **NOC overview** (подключённые OpenVPN + WireGuard) показывать домашний IP клиента и geo по нему, когда сессия пришла через известный прокси-узел и маппинг с `proxy_agent` найден. Иначе — IP прокси + пометка «через прокси».

## Решения владельца

| Тема | Выбор |
|------|--------|
| Поверхности | Только monitoring overview (не traffic sessions, не Telegram NOC) |
| Match | PROXY_IP + port = `proxy_sport` → `client_ip` |
| Кэш | In-process TTL ~45 с на proxy node |
| Fallback | IP прокси + `via_proxy=true`, geo по IP прокси |
| Подход | Enrich внутри `monitoring_overview` до `lookup_ips_geo` |

## Не цели

- Traffic collector / sessions API
- Telegram NOC report
- Установка proxy.sh
- Изменение учёта трафика

## Условие активности

Склейка выполняется только если:

1. Feature toggle `proxy_nodes` **включён**, и  
2. Есть хотя бы один `node_kind=proxy` (попытка получить mappings; offline → пустой кэш).

Иначе overview без изменений относительно pre-wave2.

## Архитектура

```
monitoring_overview
  → if proxy_nodes enabled:
       load online proxy nodes
       get_cached_mappings(proxy_id)  # TTL 45s → ProxyNodeAdapter.mappings()
  → for each OVPN/WG session:
       if real_address IP ∈ proxy_ips:
          via_proxy=true
          if (ip, port) matches mapping.proxy_sport → client_ip, proxy_resolved=true
  → lookup_ips_geo(resolved client IPs or proxy IPs)
  → apply display_address / geo fields
```

Module: `backend/app/services/proxy_noc_enrich.py` (name may vary).

## Matching

1. Build set of proxy public IPs from `Node.host` for `node_kind=proxy` (normalize IPv4; skip unresolvable hostnames for match set or resolve best-effort once).  
2. Parse session endpoint via existing `parse_client_endpoint`.  
3. If `lookup_ip` not in proxy IP set → unchanged (no via_proxy).  
4. If in set → `via_proxy=true`. Look up mapping where `proxy_sport == port` (from endpoint). On hit: use `client_ip` for display + geo; `proxy_resolved=true`.  
5. On miss: keep proxy IP for display/geo; `proxy_resolved=false`.

Agent/conntrack errors: treat as empty mappings; never raise out of overview.

## Cache

- Key: proxy `node.id`  
- Value: list of mapping dicts  
- TTL: **45 seconds**  
- Process-local (no Redis required)

## Response fields

Extend enriched OpenVPN/WG client objects in overview:

| Field | Type | Meaning |
|-------|------|---------|
| `via_proxy` | bool | endpoint IP is a known proxy |
| `proxy_resolved` | bool | mapping found → home IP used |
| `display_address` / `client_ip` | str | home IP when resolved; else proxy endpoint as today |
| geo fields | | from resolved IP or proxy IP |

Optional: `proxy_node_id` when via_proxy (useful for UI). Keep YAGNI — only if FE needs it in same PR.

## UI

NOC connected-clients table: subtle mark when `via_proxy` (and optionally different style when resolved). No new page.

## Testing

- Unit match success / wrong port / non-proxy IP  
- Toggle off → no adapter calls  
- Agent failure → via_proxy + unresolved, no crash  
- Cache: second call within TTL skips HTTP  

## Docs

- `docs/noc-monitoring.md` — кратко про восстановление IP  
- `docs/uzly.md` / `docs/proxy-agent.md` — связь с волной 1  
- `CHANGELOG.md`  
- Design status → `implemented` when done  

## Acceptance

- [x] Toggle off → NOC unchanged  
- [x] Through proxy + live mapping → home IP + geo  
- [x] Through proxy + no mapping → proxy IP + via_proxy mark  
- [x] Agent down → NOC still loads  
- [x] Traffic accounting unchanged  

## Критерий готовности

Overview enrichment + tests + docs; ready for manual lab check with real proxy_agent mappings.
