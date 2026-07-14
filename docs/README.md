# Руководства пользователя AdminPanelAZ

Здесь собраны простые инструкции по работе с веб-панелью. Написано для администраторов и обычных пользователей VPN — без технического жаргона.

---

## Роли в панели

| Роль | Кто это | Что может |
|------|---------|-----------|
| **Администратор** | Владелец сервера | Всё: клиенты, узлы, настройки, бэкапы, маршрутизация |
| **Пользователь** | Клиент VPN / self-service | Свои конфиги; по настройкам админа — создание, квота, доп. доступ к чужим клиентам (только просмотр/скачивание) |

Некоторые разделы видны не всем — зависит от роли и от того, какие модули включил администратор.

---

## Основные разделы меню

| Раздел в панели | Инструкция | Для кого |
|-----------------|------------|----------|
| Конфигурации | [konfiguracii.md](konfiguracii.md) | Все (создание — админ) |
| NOC Мониторинг | [noc-monitoring.md](noc-monitoring.md) | Только админ |
| Мониторинг трафика | [traffic-monitoring.md](traffic-monitoring.md) | Все |
| Маршрутизация / CIDR | [routing-cidr.md](routing-cidr.md) | Только админ |
| Конфиг AntiZapret | [antizapret-config.md](antizapret-config.md) | Только админ |
| AZ-WARP | [warper.md](warper.md) | Только админ |
| Telegram | [Telegram.md](Telegram.md) | Только админ |
| Редактор файлов | [edit-files.md](edit-files.md) | Только админ |
| Журналы | [logs.md](logs.md) | Только админ |
| Сервер | [server-monitor.md](server-monitor.md) | Только админ |
| Узлы | [uzly.md](uzly.md) | Только админ |
| Настройки | [nastrojki/README.md](nastrojki/README.md) | Все (часть — только админ) |

---

## Настройки (подразделы)

Полный список: [nastrojki/README.md](nastrojki/README.md)

| Раздел | Файл |
|--------|------|
| Профиль | [profil.md](nastrojki/profil.md) |
| Пользователи | [polzovateli.md](nastrojki/polzovateli.md) |
| Доступ к панели | [bezopasnost.md](nastrojki/bezopasnost.md) |
| Раздача конфигов | [razdacha-konfigov.md](nastrojki/razdacha-konfigov.md) |
| Обслуживание | [obsluzhivanie.md](nastrojki/obsluzhivanie.md) |
| Адрес сайта и HTTPS | [set-i-publikaciya.md](nastrojki/set-i-publikaciya.md) |
| Резервные копии | [rezervnye-kopii.md](nastrojki/rezervnye-kopii.md) |
| Мониторинг и алерты | [monitoring-i-alerty.md](nastrojki/monitoring-i-alerty.md) |
| Модули | [moduli.md](nastrojki/moduli.md) |
| Обновления | [obnovleniya.md](nastrojki/obnovleniya.md) |
| Диагностика | [diagnostika.md](nastrojki/diagnostika.md) |

---

## Дополнительно

| Тема | Файл |
|------|------|
| Локальная геолокация (GeoIP) | [GeoIP.md](GeoIP.md) |
| Telegram (бот, Mini App, уведомления) | [Telegram.md](Telegram.md) |
| Карта проекта (для разработчиков) | [PROJECT_MAP.md](PROJECT_MAP.md) |

---

## Пожелания и баги

Что-то не работает или хотите новую функцию — **[доска обратной связи AdminPanelAZ](https://claymore0098.fider.io/)**.

1. **Поищите** похожие записи.
2. Если нашли — **проголосуйте** или уточните в комментарии.
3. Если нет — создайте новую с тегом: **ошибка**, **пожелание** или **вопрос**.

GitHub для этого не нужен.

---

## Планы / доработки

Технические планы для разработчиков (не пользовательские инструкции):

| Тема | Папка |
|------|-------|
| NOC Ops (инциденты, SSE, rate, история, действия, фильтры, health, freshness, source badge, HA) | [plans/noc-ops/](plans/noc-ops/) |
| Видимость VPN-профилей для пользователей (default + per-user, спека и промпты) | [plans/vpn-profile-visibility/](plans/vpn-profile-visibility/) |
| Консолидация роли Пользователь / удаление viewer (ACL, can_create) | [plans/user-role-consolidation/](plans/user-role-consolidation/) |

---

## С чего начать после установки

1. Смените пароль и включите двухфакторную защиту — [profil.md](nastrojki/profil.md)
2. Если VPN на другом сервере — добавьте узел — [uzly.md](uzly.md)
3. На **Конфигурации** нажмите **Синхронизировать** — [konfiguracii.md](konfiguracii.md)
4. Настройте HTTPS и резервные копии — [set-i-publikaciya.md](nastrojki/set-i-publikaciya.md), [rezervnye-kopii.md](nastrojki/rezervnye-kopii.md)
