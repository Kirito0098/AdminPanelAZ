# AZ-AWG2 — срез 1a (shell модуля)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**План:** [wave1a plan](../plans/2026-08-10-az-awg2-wave1a.md)  
**Родительский спек:** [wave1](2026-08-10-az-awg2-design.md)

## Цель

Появился модуль AZ-AWG2 в панели: его можно включить, открыть `/awg2`, увидеть установлен ли слой, получить команду установки. **Клиентов ещё нет.**

## В scope

- `FEATURE_AWG2_ENABLED` / toggle `awg2` (default off)
- `Awg2Service.detect` / `get_health` / `get_status` (status может быть тонким)
- `GET /api/awg2/health`, `GET /api/awg2/status`
- NodeAdapter + node_agent parity для health/status
- Router mount, Layout nav, `App` route + `FeatureGuardRoute`
- `Awg2Page`: hero + install-prompt + пустое/справка «клиенты в следующем срезе»
- `haNodeScope`: `/awg2` не group-scope
- Минимальные unit/API тесты health + toggle

## Не цели

- `VpnType.amneziawg2`, create/delete, Clients tab, Dashboard (→ 1b/1c)
- HA, obfuscation, monitoring, TG

## Критерии готовности

1. Toggle off → пункта меню и `/api/awg2/*` нет.  
2. Toggle on, слой нет → install-prompt с командой curl.  
3. Toggle on, слой есть (mock) → health `installed=true`.  
4. Сток WG / AZ-WARP без регрессий.
