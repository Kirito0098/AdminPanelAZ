# План: видимость VPN-профилей для пользователей

**Статус:** реализовано (2026-07-13)  
**Аудитория:** разработчики / агенты Cursor

Администратор задаёт, какие варианты VPN-профилей **видны** обычным пользователям (`role=user`) при создании, скачивании, в Mini App и Telegram-боте. Глобальное **умолчание** + **исключения** на конкретного пользователя (как у квоты конфигов).

---

## Оглавление

| Файл | Содержание |
|------|------------|
| [SPEC.md](SPEC.md) | Продуктовая и техническая спека: JSON-модель, resolve, поверхности, edge cases, приёмка |
| [PROMPTS.md](PROMPTS.md) | Готовые промпты для поэтапной реализации в агенте |

---

## Примеры сценариев

### Пример A

Пользователю видны только **AZ** и **VPN · UDP**.

Скрыто: OpenVPN UDP+TCP, OpenVPN TCP, WireGuard, AmneziaWG.

```json
{
  "routes": ["az", "vpn"],
  "protocols": ["openvpn"],
  "openvpn_groups": ["udp"]
}
```

### Пример B

Пользователю видны **AZ**, **VPN · UDP**, **WireGuard**, **AmneziaWG**.

Скрыто: OpenVPN UDP+TCP, OpenVPN TCP.

```json
{
  "routes": ["az", "vpn"],
  "protocols": ["openvpn", "wireguard", "amneziawg"],
  "openvpn_groups": ["udp"]
}
```

---

## Ключевые решения (кратко)

- Три оси: маршрут (`az`/`vpn`) × OpenVPN-группа (`udp_tcp`/`udp`/`tcp`) × протокол (`openvpn`/`wireguard`/`amneziawg`).
- Default в `AppSetting`; per-user override в колонке пользователя (`null` = наследовать).
- Override — **полная замена**, не merge.
- Админ — без ограничений по этой политике.
- Глобальные feature-toggles остаются «потолком».

Подробности — в [SPEC.md](SPEC.md). Реализация — по [PROMPTS.md](PROMPTS.md).

---

[← К оглавлению docs](../../README.md)
