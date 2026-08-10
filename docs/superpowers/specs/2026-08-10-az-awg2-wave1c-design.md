# AZ-AWG2 — срез 1c (Dashboard + docs)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [az-awg2-epic](2026-08-10-az-awg2-epic.md)  
**План:** [wave1c plan](../plans/2026-08-10-az-awg2-wave1c.md)  
**Зависит от:** [1b](2026-08-10-az-awg2-wave1b-design.md)

## Цель

Пользователь и admin работают с AWG 2.0 там же, где со стоком: Dashboard create/карточки, visibility, скачивание. Документация волны 1 готова.

## В scope

- Dashboard: опция «AmneziaWG 2.0» если toggle + health.installed
- Protocol tab / маркировка `amneziawg2` отдельно от стокового AmneziaWG
- Visibility/quota UX согласованы с 1b
- `docs/awg2.md` + ссылки README / PROJECT_MAP / konfiguracii + CHANGELOG
- Help tab на `/awg2`: отличие от стока и AZ-WARP; «HA — позже (2a)»

## Не цели

- HA, obfuscation, monitoring, TG, TTL

## Критерии готовности

1. User с visibility создаёт/скачивает свои AWG2 конфиги в вебе.  
2. Сток AmneziaWG tab не смешивается с 2.0.  
3. Docs описывают модуль и SSH-установку.
