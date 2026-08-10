# AZ-AWG2 — срез 2c (мониторинг)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**План:** [wave2c plan](../plans/2026-08-10-az-awg2-wave2c.md)  
**Зависит от:** [1a](2026-08-10-az-awg2-wave1a-design.md) (страница); желательно после 2b для полного набора вкладок

## Цель

Вкладка **Мониторинг**: интерфейсы + overview клиентов (online/handshake/traffic). Deep client/geo — не здесь (3c).

## В scope

- `GET /api/awg2/monitoring` — ifaces + clients + `stats_available`
- Источник: `awg_stats overview` если есть `stats.db`; иначе live `awg show dump`
- Adapter/agent parity
- UI tab; refresh
- Docs/CHANGELOG куска волны 2 monitoring; help tab актуален

## Не цели

- Client drawer / daily / GeoIP (3c)
- Obfuscation (2b), HA (2a) — уже отдельно

## Критерии готовности

1. Overview или честный empty/fallback без 500.  
2. Online ≈ handshake &lt; 180s.  
3. `stats.db` не уезжает в HA archive (правило 2a).
