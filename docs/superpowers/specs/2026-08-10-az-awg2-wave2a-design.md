# AZ-AWG2 — срез 2a (HA crypto-sync)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**План:** [wave2a plan](../plans/2026-08-10-az-awg2-wave2a.md)  
**Зависит от:** [1c](2026-08-10-az-awg2-wave1c-design.md)  
**Родитель:** [wave2](2026-08-10-az-awg2-wave2-design.md)

## Цель

Failover-паритет для AWG2: create/delete на primary копирует состояние на replica (byte-copy + runtime apply). Replica без слоя → ошибка с install_command.

## В scope

- `export_state_archive` / `import_state_archive` / `apply_runtime` в `Awg2Service`
- Adapter + agent endpoints
- `sync_amneziawg2_state_from_primary` в `vpn_state_sync`; ветка в `sync_vpn_crypto_from_primary` и `sync_all_*`
- Снять HA skip волны 1 в `configs` / `maybe_replicate_*`
- Инвертировать тесты «replicate not called»
- UI: убрать «HA позже»; предупреждение если replica без слоя (help / banner)
- Docs: NodeSync note про paths / exclude `stats.db`

## Не цели

- Obfuscation UI (2b), monitoring (2c), remote install (3a)

## Критерии готовности

1. Create в HA-группе → files+peers на replica при установленном слое.  
2. Replica без слоя → replicate error + install_command.  
3. Сток WG HA без регрессий.
