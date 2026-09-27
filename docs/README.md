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
| Прокси | [proxy-nodes.md](proxy-nodes.md) | Только админ (меню **Конфигурация → Прокси**, модуль `proxy_nodes`) |
| AZ-WARP | [warper.md](warper.md) | Только админ |
| AZ-AWG2 | [awg2.md](awg2.md) | Админ (страница); пользователи — свои конфиги на Конфигурациях |
| Telegram | [Telegram.md](Telegram.md) | Только админ |
| Редактор файлов | [edit-files.md](edit-files.md) | Только админ |
| Журналы | [logs.md](logs.md) | Только админ |
| Сервер | [server-monitor.md](server-monitor.md) | Только админ |
| Узлы | [uzly.md](uzly.md) | Только админ |
| SSH-транспорт узлов | [node-ssh-transport.md](node-ssh-transport.md) | Только админ (модуль `node_ssh_transport`) |
| proxy_agent (установка на RU) | [proxy-agent.md](proxy-agent.md) | Только админ |
| Подписка | [podpiska.md](podpiska.md) | Только админ: срок на пользователе, портал (`c_`/`u_`), unlock (модули `client_portal` / `unlock_codes`) |
| Настройки | [nastrojki/README.md](nastrojki/README.md) | Все (часть — только админ) |

---

## Настройки (подразделы)

Полный список: [nastrojki/README.md](nastrojki/README.md)

| Раздел | Файл |
|--------|------|
| Мой профиль | [profil.md](nastrojki/profil.md) |
| Пользователи | [polzovateli.md](nastrojki/polzovateli.md) |
| Защита входа | [bezopasnost.md](nastrojki/bezopasnost.md) |
| Выдача VPN-профилей | [razdacha-konfigov.md](nastrojki/razdacha-konfigov.md) |
| Обслуживание VPN | [obsluzhivanie.md](nastrojki/obsluzhivanie.md) |
| Адрес сайта и HTTPS | [set-i-publikaciya.md](nastrojki/set-i-publikaciya.md) |
| Резервные копии | [rezervnye-kopii.md](nastrojki/rezervnye-kopii.md) |
| Нагрузка и уведомления | [monitoring-i-alerty.md](nastrojki/monitoring-i-alerty.md) |
| Разделы панели | [moduli.md](nastrojki/moduli.md) |
| Обновление панели | [obnovleniya.md](nastrojki/obnovleniya.md) |
| Перезапуск и пересборка | [perezapusk-i-peresborka.md](nastrojki/perezapusk-i-peresborka.md) |
| Проверка работы | [diagnostika.md](nastrojki/diagnostika.md) |

---

## Дополнительно

| Тема | Файл |
|------|------|
| Локальная геолокация (GeoIP) | [GeoIP.md](GeoIP.md) |
| Telegram (бот, Mini App, уведомления) | [Telegram.md](Telegram.md) |
| Карта проекта (для разработчиков) | [PROJECT_MAP.md](PROJECT_MAP.md) |
| Кодревью сентябрь 2026: исправлено и что осталось (для разработчиков) | [code-review-2026-09.md](code-review-2026-09.md) |

---

## Пожелания и баги

Что-то не работает или хотите новую функцию — **[доска обратной связи AdminPanelAZ](https://claymore0098.fider.io/)**.

1. **Поищите** похожие записи.
2. Если нашли — **проголосуйте** или уточните в комментарии.
3. Если нет — создайте новую с тегом: **ошибка**, **пожелание** или **вопрос**.

GitHub для этого не нужен.

---

## С чего начать после установки

После `install.sh` панель открывается по `http://IP:порт/` (HTTPS — позже в UI). Авто-бэкап уже включён (каждые 7 дней).

Логин и пароль администратора — в итоговой сводке установщика, блок **«Учётные данные»**. Пароля `admin` / `admin` по умолчанию нет: если пароль не вводили, установщик сгенерировал случайный — [подробнее](../README.md#вход-после-установки).

1. Смените пароль и включите двухфакторную защиту — [profil.md](nastrojki/profil.md)
2. Настройте домен и HTTPS — [set-i-publikaciya.md](nastrojki/set-i-publikaciya.md)
3. Если VPN на другом сервере — добавьте узел — [uzly.md](uzly.md)
4. В разделе **Клиенты** нажмите **Синхронизировать** — [konfiguracii.md](konfiguracii.md)
5. Telegram (token в UI) и бэкапы — [Telegram.md](Telegram.md), [rezervnye-kopii.md](nastrojki/rezervnye-kopii.md)

Обновляетесь с 2.25.1 на 2.26.0 — выполните шаги из раздела [Обновление с 2.25.1 до 2.26.0](nastrojki/obnovleniya.md#обновление-с-2251-до-2260).
