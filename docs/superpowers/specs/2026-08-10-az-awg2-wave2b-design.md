# AZ-AWG2 — срез 2b (обфускация)

**Дата:** 2026-08-10  
**Статус:** implemented  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**План:** [wave2b plan](../plans/2026-08-10-az-awg2-wave2b.md)  
**Зависит от:** [2a](2026-08-10-az-awg2-wave2a-design.md) (HA sync после apply желателен)

## Цель

Вкладка **Обфускация**: показать профиль, перегенерировать, применить preset/template; после apply — regen-all, warning re-import, HA sync state.

## В scope

- CLI wrap: `awg-obfuscation --show|--regenerate|--preset … --template … --apply` + `awg-client regen-all`
- API: `GET/POST …/obfuscation`, `…/regenerate`, `…/apply`
- Adapter/agent parity
- UI tab на `/awg2`
- После apply: HA sync (helper из 2a); HA errors в warning, primary apply не откатывать

## Не цели

- Monitoring (2c), install SSE (3a)

## Критерии готовности

1. Show отражает meta/env.  
2. Apply/regen меняют профиль и пересобирают клиентские conf.  
3. UI предупреждает о re-import; HA sync best-effort.
