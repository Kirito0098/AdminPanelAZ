# SPEC: видимость VPN-профилей для пользователей

Техническая и продуктовая спецификация. Реализация — отдельно, по [PROMPTS.md](PROMPTS.md).

---

## 1. Проблема

Сейчас всем пользователям с доступом к конфигам доступны одни и те же варианты профилей (в пределах глобальных feature-toggles): OpenVPN (UDP+TCP / UDP / TCP), WireGuard, AmneziaWG, маршруты AZ и VPN.

Админу нужна **рулёжка каталога**: одному пользователю — только AZ + VPN UDP; другому — AZ + VPN UDP + WG + AWG. Плюс **умолчание на всех** и **исключения** на отдельных пользователей.

---

## 2. Продуктовый UX

### 2.1. Умолчание (для всех `role=user`)

Место: **Настройки → Пользователи** (или блок self-service рядом с «Квота конфигов по умолчанию»).

UI: чекбоксы / группы по осям:

- Маршруты: **AZ**, **VPN**
- OpenVPN: **UDP+TCP**, **UDP**, **TCP**
- Протоколы: **OpenVPN**, **WireGuard**, **AmneziaWG**

Сохранение → `AppSetting` `user_visible_vpn_profiles_default`.

### 2.2. Исключение на пользователя

В карточке пользователя (UsersTab):

- Переключатель **«Как умолчание»** / **«Своя политика»**
- При «Своя политика» — те же чекбоксы
- Пустое/наследование → `User.visible_vpn_profiles = null`
- Своя → JSON полной политики (не diff от default)

### 2.3. Поведение для пользователя

В web / Mini App / боте пользователь **не видит** запрещённые:

- варианты в create (OpenVPN vs WG/AWG);
- файлы профилей (AZ/VPN, UDP/TCP);
- фильтры протоколов, где они есть;
- чипы OpenVPN-группы — только среди разрешённых `openvpn_groups`.

Админ (`role=admin`) политику не применяет: полный каталог (с учётом feature-toggles).

---

## 3. Модель данных

### 3.1. JSON-политика

```json
{
  "routes": ["az", "vpn"],
  "protocols": ["openvpn", "wireguard", "amneziawg"],
  "openvpn_groups": ["udp_tcp", "udp", "tcp"]
}
```

| Поле | Допустимые значения | Смысл |
|------|---------------------|--------|
| `routes` | `az`, `vpn` | AntiZapret vs полный VPN |
| `protocols` | `openvpn`, `wireguard`, `amneziawg` | Тип файлов на диске |
| `openvpn_groups` | `udp_tcp`, `udp`, `tcp` | Папки OpenVPN (см. ниже) |

**Умолчание «из коробки»** (если setting отсутствует): все значения всех осей разрешены — поведение как сейчас.

### 3.2. Маппинг на текущий код

| Политика | Код сегодня |
|----------|-------------|
| `az` | variants `antizapret`, `antizapret-udp`, `antizapret-tcp`; WG/AWG path с antizapret |
| `vpn` | variants `vpn`, `vpn-udp`, `vpn-tcp`; WG/AWG path с vpn |
| `udp_tcp` | `GROUP_UDP\TCP` → variants `antizapret`, `vpn` ([`public_routes.py`](../../../backend/app/constants/public_routes.py)) |
| `udp` | `GROUP_UDP` → `antizapret-udp`, `vpn-udp` |
| `tcp` | `GROUP_TCP` → `antizapret-tcp`, `vpn-tcp` |
| `openvpn` | `VpnType.openvpn`, файлы `.ovpn` |
| `wireguard` | protocol `wireguard`, `-wg.conf` |
| `amneziawg` | protocol `amneziawg`, `-am.conf` (не отдельный `VpnType`) |

Якоря:

- [`backend/app/services/antizapret.py`](../../../backend/app/services/antizapret.py) — `get_profile_files`
- [`backend/app/services/openvpn_group.py`](../../../backend/app/services/openvpn_group.py) — фильтр OVPN-группы
- [`backend/app/services/telegram_profile_ui.py`](../../../backend/app/services/telegram_profile_ui.py) — подписи AZ/VPN, ovpn/wg/awg
- [`backend/app/services/self_service.py`](../../../backend/app/services/self_service.py) — паттерн default + override (`config_quota`)

### 3.3. Хранение

| Что | Где |
|-----|-----|
| Умолчание | `AppSetting.key = "user_visible_vpn_profiles_default"`, value = JSON string |
| Исключение | колонка `users.visible_vpn_profiles` (`Text` / JSON, nullable) |

Паттерн resolve (как квота):

```
if user.role == admin:
    return FULL_POLICY  # все оси, затем ∩ feature toggles
if user.visible_vpn_profiles is not None:
    return parse(user.visible_vpn_profiles)
return parse(AppSetting default) or FULL_POLICY
```

Override — **полная замена**, не merge с default.

### 3.4. Валидация

- Только известные ключи и значения; неизвестные → 400 / truncate to known.
- Пустые массивы допустимы, но UX должен предупреждать («пользователь не увидит ни одного профиля»).
- `openvpn` в `protocols` без `openvpn_groups` → эффективных OVPN-файлов нет (эквивалент скрытию OpenVPN).
- WG/AWG игнорируют `openvpn_groups` (группы только для OpenVPN).

---

## 4. Правило фильтрации файла профиля

Для каждого элемента `profile_files` (поля `protocol` / `variant` / path):

1. Определить `protocol_key` ∈ {`openvpn`,`wireguard`,`amneziawg`}.
2. Определить `route` ∈ {`az`,`vpn`} (как `is_az_profile` / `file_route_label`).
3. Если OpenVPN — определить `group` ∈ {`udp_tcp`,`udp`,`tcp`} по variant.
4. Разрешить файл, если:
   - `protocol_key ∈ policy.protocols`, и
   - `route ∈ policy.routes`, и
   - (не OpenVPN) **или** `group ∈ policy.openvpn_groups`.

Дополнительно: пересечение с feature-toggles (`openvpn` / `wireguard` / `amneziawg` modules).

### 4.1. Создание конфига (`VpnType`)

| Запрос create | Условие |
|---------------|---------|
| `openvpn` | `openvpn ∈ protocols` и `openvpn_groups` не пуст (и feature openvpn) |
| `wireguard` | `wireguard ∈ protocols` **или** `amneziawg ∈ protocols` (как сейчас: один create → оба набора файлов на диске), с учётом toggles |

Если разрешён только `amneziawg` без `wireguard` — create `wireguard` разрешён, но в выдаче файлов остаются только `-am.conf` (и наоборот).

---

## 5. Поверхности применения

| Поверхность | Что фильтровать |
|-------------|-----------------|
| Web API list/detail configs | `profile_files` после enrichment; OpenVPN group API — только разрешённые группы |
| Web create | варианты типа в UI + `require` на backend |
| Web OpenVPN group chips | subset of `openvpn_groups` |
| Mini App `/tg-mini/configs` + files | те же фильтры |
| Mini App create | те же create guards |
| Telegram bot configs menu | фильтры ovpn/wg/awg и список файлов |
| Публичные QR / download links | **не** режем по политике владельца (ссылка уже выдана); опционально уточнить в реализации — по умолчанию **не менять** публичные роуты |

Viewer: если смотрит чужой конфиг по grant — применять политику **viewer**, не владельца (viewer видит только то, что ему разрешено скачивать).

---

## 6. Граничные случаи

| Случай | Поведение |
|--------|-----------|
| Админ | Политика не применяется |
| `visible_vpn_profiles = null` | Наследовать default |
| Пустой allowlist | Create недоступен; список файлов пуст; бот/Mini App показывают понятное сообщение |
| Уже существующий OVPN-конфиг, а OVPN скрыт | Карточка конфига остаётся (владение), но файлы/действия скачивания по скрытым вариантам не отдаются; если все файлы скрыты — пустой список файлов |
| Сменили default | Все с `null` сразу получают новый каталог |
| Feature toggle выключил WG | Даже если политика разрешает `wireguard`, файлов WG нет |
| Конфликт с сохранённой OpenVPN group пользователя | Если текущая group запрещена — fallback на первую разрешённую из `openvpn_groups` (или default среди разрешённых) |

---

## 7. API (целевое)

Минимальный набор (имена можно уточнить при реализации):

| Метод | Назначение |
|-------|------------|
| `GET /api/settings/user-vpn-visibility-default` | Читать default (admin) |
| `PUT /api/settings/user-vpn-visibility-default` | Писать default (admin) |
| `PATCH /api/users/{id}` | поле `visible_vpn_profiles: object \| null` |
| `GET /api/configs/quota` или `/me` / settings | отдать **effective** policy текущему пользователю для UI |

Ответ effective policy нужен фронту, чтобы не гадать чекбоксы create/tabs.

---

## 8. Критерии приёмки

### Пример A

Policy: `routes=[az,vpn]`, `protocols=[openvpn]`, `openvpn_groups=[udp]`.

- Create: только OpenVPN; нет WG/AWG.
- Файлы: только `*-udp.ovpn` для AZ и VPN; нет базовых `.ovpn`, `*-tcp.ovpn`, `-wg.conf`, `-am.conf`.
- Web / Mini App / бот — одинаковый каталог.
- Админ с тем же сервером видит всё.

### Пример B

Policy: `routes=[az,vpn]`, `protocols=[openvpn,wireguard,amneziawg]`, `openvpn_groups=[udp]`.

- Create: OpenVPN и WireGuard/AmneziaWG.
- OVPN файлы: только UDP; WG и AWG AZ/VPN — видны.
- Нет UDP+TCP и TCP OVPN.

### Умолчание + исключение

1. Default = полный каталог.
2. Пользователь U1 → override как A → видит A.
3. Пользователь U2 с `null` → видит полный каталог.
4. Меняем default на A → U2 видит A; U1 без изменений (свой override).
5. Сброс U1 на «Как умолчание» → снова следует default.

---

## 9. Вне скоупа этой фичи

- Отдельный `VpnType` для AmneziaWG в БД.
- Изменение семантики feature-toggles.
- Политика видимости для admin.
- Переписывание публичных route-файлов (Keenetic и т.п.) под per-user policy.

---

## 10. Связанные пользовательские доки (после реализации)

Обновить:

- [`docs/nastrojki/polzovateli.md`](../../nastrojki/polzovateli.md) — умолчание и исключения.
- [`docs/konfiguracii.md`](../../konfiguracii.md) — что видит пользователь.
- При необходимости [`docs/Telegram.md`](../../Telegram.md) — фильтры бота.

До merge кода пользовательские гайды **не** менять (см. Prompt 5 в PROMPTS).

---

[← README плана](README.md)
