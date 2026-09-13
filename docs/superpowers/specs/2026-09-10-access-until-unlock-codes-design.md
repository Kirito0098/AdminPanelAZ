# Access until + Unlock codes

**Дата:** 2026-09-10  
**Статус:** approved (design dialogue)  
**Контекст:** длинные OpenVPN-сертификаты (часто 3650д) не должны быть единственным рычагом «подписки». Нужна серверная дата отключения и самообслуживание продления через unlock-ключи (панель, TG-бот, mini app, ввод на клиентском портале).

## Цель

1. Админ задаёт **срок доступа** (`access_until`) независимо от срока сертификата.  
2. По наступлении даты клиент **блокируется** на узле без порчи PKI.  
3. Админ выдаёт **универсальный unlock-код** (single/multi); клиент вводит его на портале и получает разблокировку + продление доступа.  
4. Генерация кодов доступна из **панели, Telegram-бота и mini app**.

## Зафиксированные решения

| Вопрос | Выбор |
|--------|--------|
| Scope v1 | Срок доступа + unlock-коды + панель + TG + mini app |
| Привязка кода | Универсальный (любой клиент с portal token) |
| Эффект redeem | Unblock + `access_until = max(now, current) + grant_days` |
| Multi-use | Один `client_name` — один redeem на код; другие клиенты могут ещё |
| Протоколы кода | Задаёт админ при генерации |
| Сертификат | Остаётся длинным; не продлевается unlock-кодом |
| Ввод кода клиентом | Только публичный портал `/p/{token}` |

## Разделение понятий

| Поле | Смысл | UI |
|------|--------|-----|
| `cert_expires_at` | PKI notAfter | Вторично / «сертификат» |
| `access_until` | Когда доступ должен закончиться | Главный «Истекает» на портале и в карточке |
| `block_*` | Фактическая блокировка на узле | Статус «Заблокирован» / reason |

`access_until = null` → бессрочный доступ (не путать с отсутствием cert expiry).

## Модель данных

### Access policy (расширение)

Добавить `access_until: datetime | null` в:

- `openvpn_access_policy`
- `wg_access_policy`
- `amneziawg2_access_policies`

Семантика:

- Воркер: если `access_until <= now` и клиент ещё не в состоянии `access_expired` → применить permanent-style блок с `block_reason=access_expired` (не temp с авто-снятием).
- Ручная разблокировка админом снимает блок; `access_until` меняется отдельным действием.
- Существующий WG `expires_at` / TTL: в v1 **мапится или мигрирует** в `access_until` для единообразия (явный note в плане: не плодить два поля без причины; предпочтительно использовать/переименовать смыслом «доступ», не ломая API резко — см. совместимость ниже).

### Unlock codes

Таблица `unlock_codes`:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | PK | |
| `code` | unique string | Человекочитаемый код |
| `grant_days` | int > 0 | Дней продления |
| `protocols` | JSON/CSV | Подмножество `openvpn`, `wireguard`, `amneziawg2` |
| `mode` | `single` \| `multi` | |
| `max_redemptions` | int | Для `single` = 1 |
| `code_expires_at` | datetime \| null | Срок жизни кода |
| `created_by_user_id` | FK \| null | |
| `created_at` | datetime | |
| `revoked_at` | datetime \| null | |

Таблица `unlock_code_redemptions`:

| Колонка | Тип |
|---------|-----|
| `id` | PK |
| `code_id` | FK |
| `client_name` | string |
| `node_id` | int (scope primary HA) |
| `redeemed_at` | datetime |
| Unique | `(code_id, client_name)` |

## Потоки

### Отложенная блокировка

```
Admin sets access_until
  → Worker poll
  → access_until <= now
  → block on node + block_reason=access_expired
```

Идемпотентно. Не снимает и не перетирает ручной `manual_permanent`, если доступ ещё не истёк; если доступ истёк — `access_expired` имеет приоритет для «подписочного» сценария (деталь: при конфликте manual vs access — access expiry всё равно блокирует; manual unblock без сдвига `access_until` приведёт к повторной блокировке следующим тиком воркера — админ должен продлить доступ или сбросить `access_until`).

### Redeem

```
Client opens /p/{token}
  → POST redeem { code }
  → validate code (exists, not revoked, not expired, redemptions < max, client not already redeemed)
  → for each protocol in code.protocols that client has:
       unblock + access_until = max(now, access_until) + grant_days
  → record redemption
```

Если ни один протокол из кода не пересекается с конфигами клиента → ошибка «код не подходит к вашим протоколам».

### Генерация

- **Панель:** CRUD кодов + «Задать доступ» на клиенте.  
- **TG bot:** команда/кнопка создания с параметрами (или пресеты).  
- **Mini app:** экран генерации на тех же auth API.  
- Клиентский ввод кода в TG/mini app — **вне v1**.

## API (черновик)

**Auth**

- `PATCH /api/client-access/{protocol}/{client_name}/access-until` `{ access_until: iso|null }`
- `GET/POST /api/unlock-codes`
- `POST /api/unlock-codes/{id}/revoke`

**Public (portal host)**

- `POST /api/public/portal/{token}/redeem` `{ code: string }`  
  → `{ ok, access_until, protocols_applied, grant_days }` или 4xx с `detail`

**Feature toggle:** `access_unlock` (или `unlock_codes`) — default true рядом с client portal; при off: redeem 403, UI скрыт.

## UX

- Создание клиента: длинный cert + опционально «Доступ до».  
- Карточка: статус доступа; действия «Доступ до…», «Unlock-ключ».  
- Портал: «Истекает» = ближайший `access_until` по протоколам клиента; форма «Ключ продления».  
- Ошибки redeem: неверный / отозван / истёк / лимит / уже использован вами / нет пересечения протоколов / rate limit.

## Совместимость

- OpenVPN portal status: приоритет `access_until` над «Бессрочно» при живом cert.  
- WG TTL / `expires_at`: в implementation plan явно выбрать — alias на `access_until` или dual-read на переходный период.  
- Существующие temp `block_until` (авто-разблок) **не** использовать для access expiry.

## Тесты

- Worker: access_until → block reason `access_expired`; повторный тик no-op.  
- Redeem формула D; unique `(code, client)`; single vs multi; revoke; code expiry.  
- Протокольный фильтр кода; portal host guard; feature off.  
- Rate limit redeem.

## Вне scope v1

Оплата/биллинг, авто-рассылка ключей клиенту в TG, QR оплаты, перевыпуск сертификата при redeem, redeem без portal token, self-service в mini app.

## Критерии готовности

- Админ может выставить `access_until`; после даты клиент не коннектится, cert валиден.  
- Админ создаёт single/multi код с протоколами из панели, TG и mini app.  
- Клиент на портале вводит код → unblock + продление по D; повтор тем же client_name на тот же код — отказ.  
- Портал не показывает «Бессрочно», если задан `access_until` или истекший доступ.
