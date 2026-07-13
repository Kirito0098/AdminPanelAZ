# PROMPTS: реализация видимости VPN-профилей

Копируй промпт целиком в агент. Спека: [SPEC.md](SPEC.md). Не пропускай этапы и не смешивай несколько prompts в одном заходе без необходимости.

Общий контекст для всех промптов:

> Репозиторий AdminPanelAZ. Фича «видимость VPN-профилей»: JSON-политика с осями `routes` (`az`/`vpn`), `protocols` (`openvpn`/`wireguard`/`amneziawg`), `openvpn_groups` (`udp_tcp`/`udp`/`tcp`). Global default в `AppSetting` `user_visible_vpn_profiles_default`; per-user override в `User.visible_vpn_profiles` (`null` = inherit). Override — полная замена. Админ без ограничений. Feature-toggles — потолок. Паттерн как квота в `backend/app/services/self_service.py`. Подробности — `docs/plans/vpn-profile-visibility/SPEC.md`.

---

## Prompt 1 — Backend: модель, resolve, тесты

```
Реализуй backend-ядро видимости VPN-профилей по docs/plans/vpn-profile-visibility/SPEC.md (только модель + resolve + тесты, без UI и без фильтрации эндпоинтов).

Сделай:
1. Константы FULL_POLICY и ключ SETTING_VISIBLE_VPN_PROFILES_DEFAULT = "user_visible_vpn_profiles_default".
2. Парсер/валидатор JSON-политики (routes, protocols, openvpn_groups) — неизвестные значения отбрасывать или 400 на write API.
3. Колонку User.visible_vpn_profiles (Text/JSON nullable) + миграция/ensure в database.py по принятому в проекте стилю.
4. Функции:
   - resolve_visible_vpn_profiles(db, user) -> policy dict
   - profile_file_allowed(policy, *, protocol, variant, path) -> bool
   - can_create_vpn_type(policy, vpn_type, feature_flags) -> bool
   - allowed_openvpn_groups(policy) -> list
5. Маппинг variant/path → route/group/protocol согласовать с antizapret.get_profile_files, openvpn_group, telegram_profile_ui.is_az_profile.
6. Unit-тесты: примеры A и B из SPEC §8; null наследует default; admin → full; пустой openvpn_groups скрывает OVPN-файлы.

Не трогай роутеры configs/tg_mini/telegram handlers и фронт в этом шаге.
```

---

## Prompt 2 — Backend: фильтр profile_files и create guards (web API)

```
Продолжи фичу видимости VPN-профилей (docs/plans/vpn-profile-visibility/SPEC.md). Ядро resolve уже есть.

Подключи политику к web API конфигов:
1. После enrichment profile_files (list/detail) фильтруй через profile_file_allowed(resolve_visible_vpn_profiles(...)).
2. Create config: enforce can_create_vpn_type; 403 с понятным detail на русском.
3. GET/PUT openvpn-group: отдавай/принимай только группы из allowed_openvpn_groups; при запрещённой сохранённой группе — fallback на первую разрешённую.
4. Admin не фильтруется.
5. Добавь GET effective policy для текущего пользователя (удобный эндпоинт рядом с quota/settings — на твоё усмотрение в стиле проекта).
6. Admin API: GET/PUT default setting; PATCH users поддерживает visible_vpn_profiles: object|null.
7. Тесты API/сервиса на пример A (только udp OVPN) и create wireguard → 403.

Не делай фронт и Telegram/Mini App в этом шаге (Mini App можно затронуть только если делит те же backend-хелперы — тогда фильтр файлов тоже).
```

---

## Prompt 3 — Admin UI: default + per-user

```
Добавь админский UI для видимости VPN-профилей по docs/plans/vpn-profile-visibility/SPEC.md.

1. Блок «Умолчание видимости профилей» рядом с квотой / в Users settings: чекбоксы routes, openvpn_groups, protocols; сохранить через API default.
2. В карточке пользователя: режим «Как умолчание» | «Своя политика»; при своей — те же чекбоксы; null vs JSON override.
3. Предупреждение, если все оси пустые.
4. Типы/клиент API в frontend по аналогии с updateUser / quota.
5. Не ломай существующий UsersTab (роль, telegram_id, квота, viewer access).

После изменений — кратко опиши, куда кликать в UI для настройки примера A и B.
```

---

## Prompt 4 — Mini App + Telegram bot parity

```
Доведи паритет видимости VPN-профилей на Mini App и Telegram-бот (SPEC.md §5, §8).

1. Mini App: create options и списки файлов/фильтры только по effective policy (используй тот же backend resolve; при необходимости отдай policy в /tg-mini/settings или configs).
2. Telegram bot configs handlers: фильтры ovpn/wg/awg и выбор файла через profile_file_allowed; скрытые протоколы не показывать в меню.
3. Сообщения при пустом каталоге — коротко по-русски («Администратор ограничил доступные типы конфигураций»).
4. Не меняй публичные QR/route downloads.
5. Проверь сценарии A и B вручную по чеклисту SPEC §8 для bot/mini (или автотесты хелперов).

Фронт web admin UI уже сделан — не переделывай без нужды.
```

---

## Prompt 5 — Пользовательская документация после merge

```
Фича видимости VPN-профилей уже в коде. Обнови пользовательские гайды:

1. docs/nastrojki/polzovateli.md — как задать умолчание и исключение на пользователя; примеры A/B простым языком.
2. docs/konfiguracii.md — что обычный пользователь может не видеть часть типов.
3. docs/Telegram.md — если бот/Mini App режут каталог по политике.
4. В docs/plans/vpn-profile-visibility/README.md смени статус на «реализовано» и укажи версию/дату если известно.
5. Не переписывай SPEC/PROMPTS целиком — только статус и ссылки при необходимости.

Стиль — как остальные docs: просто, без жаргона, таблицы сценариев.
```

---

## Рекомендуемый порядок

1 → 2 → 3 → 4 → 5. После каждого этапа — тесты/сборка соответствующего слоя и короткий отчёт по критериям приёмки SPEC §8.

---

[← README плана](README.md) · [SPEC.md](SPEC.md)
