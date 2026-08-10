# AZ-AWG2 — волна 3b (Telegram + Mini App)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [wave3](2026-08-10-az-awg2-wave3.md)  
**Зависит от:** волны 1–2; TTL UI из 3a желателен, но Mini App create без TTL допустим, если 3a ещё не влит

## Цель

Встроить AZ-AWG2 в существующий Telegram-бот панели и Mini App по образцу AZ-WARP / configs — без второго бота az-awg2 и без ops-действий (install/обфускация) в чате.

## В scope

- Bot command `/awg2` (admin): health + short monitoring overview
- Reply keyboard / help entry рядом с AZ-WARP
- Mini App page `/awg2` (read-only): installed, ifaces summary, online count
- Mini App Configs: list/create/download/delete `amneziawg2` с visibility/quota; TTL field если API 3a есть
- Feature toggle `awg2` gates bot command + Mini App routes

## Не цели

- Obfuscation / backup / install SSE в боте
- Паритет с кнопками бота upstream az-awg2
- Peer block из TG (достаточно веба / 3c позже в вебе)

## Telegram bot

### Handler

- Файл: `backend/app/services/telegram_bot_handlers/awg2_status.py` (зеркало `warper_status.py`)
- `/awg2`: если toggle off → module disabled; else adapter `get_awg2_health` + `get_awg2_monitoring` (или status+overview)
- Текст: installed?, missing components + install hint, peer online count, top-3 traffic если есть
- Admin only

### Wiring

- `telegram_bot.py` route `/awg2`
- `telegram_bot_i18n.py`: button «AZ-AWG2», help line
- Menu registration next to warper

## Mini App

### Page

- `frontend/src/tg-mini/pages/Awg2.tsx` — read-only cards (health, monitoring summary)
- Nav entry feature-gated
- API: reuse `/api/awg2/health`, `/api/awg2/monitoring` via tg-mini fetch wrappers (admin-or-allowed per existing tg auth)

### Configs

- Extend `VpnType` in tg-mini types (already from wave 1 web)
- Create dialog option AmneziaWG 2.0 when `features.awg2` && installed (health check or feature+soft fail)
- Protocol filter badge for `amneziawg2`
- Download/QR via existing panel config endpoints
- Optional TTL select if `expires_at` / ttl supported

## Тесты

- Handler returns disabled when toggle off
- Handler formats health when installed=false
- Mini App types accept `amneziawg2`
- create config path accepts type in tg API tests if present

## Критерии готовности 3b

1. `/awg2` в боте показывает статус слоя для admin.  
2. Mini App: страница AWG2 + пользователь может скачать/создать amneziawg2 при правах.  
3. Нет install/обфускации в TG.  
4. Toggle off скрывает команду и пункт Mini App.
