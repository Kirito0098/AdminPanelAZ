# AZ-AWG2 — срез 1b (клиенты + VpnConfig)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**План:** [wave1b plan](../plans/2026-08-10-az-awg2-wave1b.md)  
**Зависит от:** [1a](2026-08-10-az-awg2-wave1a-design.md)

## Цель

Admin на `/awg2` создаёт/удаляет/скачивает клиентов AWG 2.0 через `awg-client`; в БД — `VpnConfig(amneziawg2)`. HA **не** реплицирует.

## В scope

- `VpnType.amneziawg2`; `require_vpn_type` / visibility protocol `amneziawg2`
- `Awg2Service` add/del (оба туннеля + rollback), list, `get_profile_files`
- Adapter/agent: add/del/list/profiles
- `POST/DELETE /api/configs` ветка `amneziawg2`; 409 если слой не установлен
- HA skip в `configs` + `maybe_replicate_*`
- Import orphans из `/opt/antizapret-awg/clients` + stale-safe
- UI: вкладка **Клиенты** на `/awg2` (create/delete/download)
- Тесты service CRUD, create API, HA skip, import

## Не цели

- Dashboard tab / user self-service create (→ 1c)
- HA enable (→ 2a), obfuscation/monitoring (→ 2b/2c)

## Критерии готовности

1. Create → оба туннеля на диске + строка БД; partial fail → rollback.  
2. Delete → файлы и БД убраны.  
3. Download/QR через существующий pipeline.  
4. `maybe_replicate_create` **не** вызывается.  
5. Import с диска не сносит AWG2 как «stale WG».
