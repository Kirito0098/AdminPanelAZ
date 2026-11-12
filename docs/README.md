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
| Клиенты (конфигурации) | [konfiguracii.md](konfiguracii.md) | Все (создание — админ) |
| Абоненты (вкладки «Абоненты» / «Портал и коды») | [podpiska.md](podpiska.md) | Только админ (модуль `user_provisioning`; вкладка — `client_portal` / `unlock_codes`) |
| Наблюдение | [noc-monitoring.md](noc-monitoring.md), [traffic-monitoring.md](traffic-monitoring.md), [logs.md](logs.md), [server-monitor.md](server-monitor.md) | Только админ; вкладка «Трафик» — все |
| Сеть → Узлы | [uzly.md](uzly.md) | Только админ |
| Сеть → Прокси | [proxy-nodes.md](proxy-nodes.md) | Только админ (модуль `proxy_nodes`) |
| Сеть → Маршрутизация | [routing-cidr.md](routing-cidr.md) | Только админ |
| Протоколы → AntiZapret | [antizapret-config.md](antizapret-config.md) | Только админ |
| Протоколы → OpenVPN | [antizapret-config.md](antizapret-config.md#openvpn-профили-логи-и-состояние-установки) | Только админ |
| Протоколы → AZ-WARP | [warper.md](warper.md) | Только админ |
| Протоколы → AZ-AWG2 | [awg2.md](awg2.md) | Админ (страница); пользователи — свои конфиги на Клиентах |
| Система → Telegram | [Telegram.md](Telegram.md) | Только админ |
| Система → Редактор файлов | [edit-files.md](edit-files.md) | Только админ |
| SSH-транспорт узлов | [node-ssh-transport.md](node-ssh-transport.md) | Только админ (модуль `node_ssh_transport`) |
| proxy_agent (установка на RU) | [proxy-agent.md](proxy-agent.md) | Только админ |
| Настройки | [nastrojki/README.md](nastrojki/README.md) | Все (часть — только админ) |

Старые адреса **Мониторинга трафика**, **Журналов** и **Сервера** открываются редиректом на вкладки **Наблюдения**; **Подписка** стала вкладкой **«Портал и коды»** в **Абонентах**.

---

## Настройки (подразделы)

Полный список: [nastrojki/README.md](nastrojki/README.md)

| Группа | Раздел | Файл |
|--------|--------|------|
| Личное | Мой профиль | [profil.md](nastrojki/profil.md) |
| Доступ | Пользователи панели | [polzovateli.md](nastrojki/polzovateli.md) |
| Доступ | Защита входа | [bezopasnost.md](nastrojki/bezopasnost.md) |
| VPN | Выдача VPN-профилей | [razdacha-konfigov.md](nastrojki/razdacha-konfigov.md) |
| VPN | Обслуживание VPN | [obsluzhivanie.md](nastrojki/obsluzhivanie.md) |
| Сервер | Адрес сайта и HTTPS | [set-i-publikaciya.md](nastrojki/set-i-publikaciya.md) |
| Сервер | Резервные копии | [rezervnye-kopii.md](nastrojki/rezervnye-kopii.md) |
| Сервер | Нагрузка и уведомления | [monitoring-i-alerty.md](nastrojki/monitoring-i-alerty.md) |
| Панель | Уведомления в панели | [monitoring-i-alerty.md](nastrojki/monitoring-i-alerty.md) |
| Панель | Разделы панели | [moduli.md](nastrojki/moduli.md) |
| Панель | Обновление панели | [obnovleniya.md](nastrojki/obnovleniya.md) |
| Панель | Перезапуск и пересборка | [perezapusk-i-peresborka.md](nastrojki/perezapusk-i-peresborka.md) |
| Панель | Проверка работы | [diagnostika.md](nastrojki/diagnostika.md) |

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
