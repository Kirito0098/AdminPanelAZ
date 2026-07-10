# Руководства пользователя AdminPanelAZ

Здесь собраны простые инструкции по работе с веб-панелью. Написано для администраторов и обычных пользователей VPN — без технического жаргона.

---

## Роли в панели

| Роль | Кто это | Что может |
|------|---------|-----------|
| **Администратор** | Владелец сервера | Всё: клиенты, узлы, настройки, бэкапы, маршрутизация |
| **Пользователь** | Обычный клиент VPN | Свои конфиги, скачивание, QR-код |
| **Наблюдатель** | Только просмотр | Мониторинг, журналы, конфиги — без изменений |

Некоторые разделы видны не всем — зависит от роли и от того, какие модули включил администратор.

---

## Основные разделы меню

| Раздел в панели | Инструкция | Для кого |
|-----------------|------------|----------|
| Конфигурации | [konfiguracii.md](konfiguracii.md) | Все (создание — админ) |
| NOC Мониторинг | [noc-monitoring.md](noc-monitoring.md) | Все |
| Мониторинг трафика | [traffic-monitoring.md](traffic-monitoring.md) | Все |
| Маршрутизация / CIDR | [routing-cidr.md](routing-cidr.md) | Все (pipeline — админ) |
| Конфиг AntiZapret | [antizapret-config.md](antizapret-config.md) | Только админ |
| AZ-WARP | [warper.md](warper.md) | Только админ |
| Telegram | [Telegram.md](Telegram.md) | Только админ |
| Редактор файлов | [edit-files.md](edit-files.md) | Админ и пользователь* |
| Журналы | [logs.md](logs.md) | Все |
| Сервер | [server-monitor.md](server-monitor.md) | Только админ |
| Узлы | [uzly.md](uzly.md) | Только админ |
| Настройки | [nastrojki/README.md](nastrojki/README.md) | Все (часть — только админ) |

\* Редактор файлов доступен не всем ролям — см. инструкцию.

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

## С чего начать после установки

1. Смените пароль и включите двухфакторную защиту — [profil.md](nastrojki/profil.md)
2. Если VPN на другом сервере — добавьте узел — [uzly.md](uzly.md)
3. На **Конфигурации** нажмите **Синхронизировать** — [konfiguracii.md](konfiguracii.md)
4. Настройте HTTPS и резервные копии — [set-i-publikaciya.md](nastrojki/set-i-publikaciya.md), [rezervnye-kopii.md](nastrojki/rezervnye-kopii.md)
