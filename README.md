# 🛡️ AdminPanel AntiZapret

Веб-панель для администрирования VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN)

[![GitHub](https://img.shields.io/badge/GitHub-Kirito0098%2FAdminPanelAZ-181717?style=for-the-badge&logo=github)](https://github.com/Kirito0098/AdminPanelAZ)
[![Version](https://img.shields.io/badge/Панель-2.19.0-blue?style=for-the-badge)](CHANGELOG.md)
[![Node agent](https://img.shields.io/badge/Node_agent-1.6.0-555?style=for-the-badge)](CHANGELOG.md)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](backend/)
[![React](https://img.shields.io/badge/Frontend-React-61DAFB?style=for-the-badge&logo=react&logoColor=black)](frontend/)

[🚀 Быстрый старт](#-быстрый-старт) · [✨ Возможности](#-возможности) · [🖼️ Обзор](#-обзор-панели) ·
[📖 Руководства](docs/README.md) · [💬 Пожелания и баги](https://claymore0098.fider.io/) · [🔐 Безопасность](SECURITY.md) · [📝 Changelog](CHANGELOG.md)

<p align="center">
  <img src="docs/assets/telegram-promo/01-hero-banner.png" alt="AdminPanel AntiZapret" width="900">
</p>

> [!NOTE]
> **Статус проекта**
> Проект **полностью перенесён** на новый стек: добавлен новый функционал, интерфейс и документация обновлены.
> Разработка **продолжается** — планируются новые возможности и улучшения.
> Предыдущая версия на Flask — [AdminAntizapret](https://github.com/Kirito0098/AdminAntizapret).

**Панель помогает администрировать VPN: клиенты, маршрутизация, мониторинг, бэкапы и Telegram.**

- **Пользователи и администраторы** — **[docs/README.md](docs/README.md)** — простые инструкции по каждому разделу
- **Разработчики** — [CONTRIBUTING.md](CONTRIBUTING.md) (MCP, skills, договорённости) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md) · [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) · [HA / Node Sync](docs/NodeSync.md)

## 🚀 Быстрый старт

**Требования:** Ubuntu 24.04+ или Debian 13+, root / sudo, доступ в интернет.
AntiZapret ставится **отдельно** на VPN-сервер — см. [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN).

**Python:** установщик сам выбирает runtime через `scripts/python-runtime.sh` — на **Ubuntu 24.04** это **3.12**, на **Debian 13** — **3.13**.

### Порты

После `install.sh` панель сразу доступна по **HTTP** (`http://IP:порт/`, обычно **8000**). HTTPS и Nginx настраиваются позже в UI.

| Порт | Назначение | Куда открывать |
| --- | --- | --- |
| **8000** (или выбранный) | Панель | LAN / интернет — пока панель на этом порту |
| **9100** | Node agent | localhost или между панелью и VPN-узлом |
| **80** / **443** | HTTP ACME / HTTPS | после публикации в **Настройки → Адрес сайта и HTTPS** |

Порты **OpenVPN / WireGuard / AmneziaWG** задаёт **AntiZapret**, не панель.
Откройте порт панели у хостера или вручную (`ufw` / security group). Подробнее: [SECURITY.md](SECURITY.md).

### Варианты установки

Первый вопрос мастера — **что ставим на этот сервер**:

| Вариант | Что ставится | Когда выбирать |
| --- | --- | --- |
| **Только панель** | Веб-интерфейс управления | Отдельный **управляющий сервер**; к нему потом подключаются VPN-узлы (AntiZapret на других машинах) |
| **Панель + узел** | Панель и **локальный узел** на одном хосте | **AntiZapret уже установлен** на этом же сервере (`/root/antizapret`) — типичный случай «всё на одном VDS» |
| **Узел** | Только **node agent** (без панели) | Отдельный **VPN-сервер**, который нужно **подключить к уже работающей панели** на другом хосте |

#### Установка

Один скрипт — `install.sh`:

```bash
sudo apt update && sudo apt install -y git wget curl
wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
sudo bash /tmp/install.sh
```

Мастер спросит: тип установки, порты, логин/пароль администратора, ключ node agent (если ставите узел) и каталог бэкапов.

После установки откройте `http://IP:порт/` из вывода мастера. Дальше в панели:

- **Настройки → Адрес сайта и HTTPS** — DDNS, домен, Let's Encrypt. **Рекомендуем сразу перейти на HTTPS** — так доступ к панели защищён (шифрование трафика, безопасный вход).
- **Telegram** — bot token / chat (раздел уже в меню)

Подробнее: [после установки](#-после-установки) · [DDNS](#-бесплатный-адрес-для-панели-ddns) · [Production](#️-production-vds-redis-и-профили)

## 📑 Содержание

- [🚀 Быстрый старт](#-быстрый-старт)
  - [Варианты установки](#варианты-установки)
- [🖼️ Обзор панели](#-обзор-панели)
- [✨ Возможности](#-возможности)
- [✅ После установки](#-после-установки)
- [📖 Руководства пользователя](#-руководства-пользователя)
- [🌐 Бесплатный адрес (DDNS)](#-бесплатный-адрес-для-панели-ddns)
- [🔗 StatusOpenVPN на одном домене](#-statusopenvpn-на-одном-домене)
- [⚙️ Production: VDS, Redis и профили](#️-production-vds-redis-и-профили)
- [🔐 Безопасность](#-безопасность)
- [💻 Полезные команды](#-полезные-команды-на-сервере)
- [📝 История изменений](#-история-изменений)
- [💖 Поддержка проекта](#-поддержка-проекта)

## 🖼️ Обзор панели

<p align="center">
  <img src="docs/assets/telegram-promo/02-features-overview.png" alt="Все модули AdminPanel AntiZapret" width="900">
</p>

| | | |
| --- | --- | --- |
| [<img src="docs/assets/telegram-promo/10-configurations.png" alt="Конфигурации" width="400">](docs/konfiguracii.md) | [<img src="docs/assets/telegram-promo/09-nodes.png" alt="Узлы VPN" width="400">](docs/uzly.md) | [<img src="docs/assets/telegram-promo/07-routing-cidr.png" alt="Маршрутизация CIDR" width="400">](docs/routing-cidr.md) |
| [<img src="docs/assets/telegram-promo/08-routing-az-warp.png" alt="AZ-WARP" width="400">](docs/warper.md) | [<img src="docs/assets/telegram-promo/04-monitoring-noc.png" alt="Мониторинг и NOC" width="400">](docs/noc-monitoring.md) | [<img src="docs/assets/telegram-promo/03-telegram-integration.png" alt="Telegram" width="400">](docs/Telegram.md) |

## ✨ Возможности

### 🔌 VPN и клиенты

<p align="center">
  <img src="docs/assets/telegram-promo/10-configurations.png" alt="Конфигурации — VPN-клиенты" width="900">
</p>

- OpenVPN, WireGuard, AmneziaWG — создание, скачивание, QR-коды ([инструкция](docs/konfiguracii.md))
- Блокировка, срок действия, лимиты трафика
- Несколько VPN-серверов (узлов) из одной панели ([инструкция](docs/uzly.md))
- **HA (отказоустойчивость)** — группы синхронизации primary + replica, один домен, Push full, verify и авто-репликация с primary ([Node Sync](docs/NodeSync.md), UI: **Узлы → Группы синхронизации**)

<p align="center">
  <img src="docs/assets/telegram-promo/09-nodes.png" alt="Узлы VPN — несколько серверов из одной панели" width="900">
</p>

### 🧭 Маршрутизация

<p align="center">
  <img src="docs/assets/telegram-promo/07-routing-cidr.png" alt="Маршрутизация и CIDR" width="900">
</p>

- Списки провайдеров (CIDR), пресеты, конфиг AntiZapret ([маршрутизация](docs/routing-cidr.md), [конфиг](docs/antizapret-config.md))
- Редактор файлов AntiZapret с применением на сервер ([инструкция](docs/edit-files.md))
- AZ-WARP — точечная маршрутизация через Cloudflare WARP ([инструкция](docs/warper.md))

<p align="center">
  <img src="docs/assets/telegram-promo/08-routing-az-warp.png" alt="AZ-WARP — интеграция с github.com/Liafanx/AZ-WARP" width="900">
</p>

### 📊 Мониторинг

<p align="center">
  <img src="docs/assets/telegram-promo/04-monitoring-noc.png" alt="Мониторинг и NOC" width="900">
</p>

- **NOC** — кто подключён, откуда (город и провайдер), графики, состояние служб;
  **Telegram-сводки** — ежедневный/еженедельный текст и еженедельный PNG-дашборд
  ([инструкция](docs/noc-monitoring.md))
- **Трафик** — расход по клиентам и доля в общем объёме, лимиты, окна 1д / 7д / 30д ([инструкция](docs/traffic-monitoring.md))
- **Сервер** — live CPU/RAM/диск, **история ресурсов** за 1 / 7 / 30 дней, vnStat ([инструкция](docs/server-monitor.md))
- **Локальная GeoIP** — MaxMind GeoLite2 в `data/geoip/` ([инструкция](docs/GeoIP.md))

### 🔐 Безопасность и администрирование

- Роли: администратор, пользователь ([пользователи](docs/nastrojki/polzovateli.md))
- 2FA, белый список IP, защита от перебора паролей ([безопасность](docs/nastrojki/bezopasnost.md))
- Вход через Telegram — Legacy Login Widget или OpenID Connect ([Telegram](docs/Telegram.md))
- Бэкапы вручную и по расписанию, отправка в Telegram ([инструкция](docs/nastrojki/rezervnye-kopii.md))

### 💬 Telegram

<p align="center">
  <img src="docs/assets/telegram-promo/03-telegram-integration.png" alt="Telegram — вход, Mini App, бот, уведомления" width="900">
</p>

- **Вход в панель** — Legacy Login Widget или OpenID Connect (настройка на вкладке «Бот и авторизация»)
- **Mini App** — адаптированная панель и отправка VPN-конфигов из Telegram
- **Бот** — webhook, команды (`/start`, `/link`, `/status`, …), привязка и отвязка аккаунтов администратором
- **Уведомления** — несколько получателей (admin из «Пользователи» + chat ID групп/каналов),
  карточный формат, тест каждого события
- **NOC и бэкапы** — сводки по расписанию в Telegram, авто-отправка архивов выбранным получателям

Пошаговая настройка и вкладки раздела: [docs/Telegram.md](docs/Telegram.md)

## ✅ После установки

<p align="center">
  <img src="docs/assets/telegram-promo/06-quick-install.png" alt="Быстрая установка AdminPanel AntiZapret" width="900">
</p>

1. Откройте URL из вывода установщика (`http://IP:порт/`)
2. Войдите под созданным администратором
3. **Смените пароль** и включите **2FA** — [Настройки → Профиль](docs/nastrojki/profil.md)
4. **Переключите панель на HTTPS** — **Настройки → Адрес сайта и HTTPS** (домен или DDNS + Let's Encrypt). HTTP удобен для первого входа, но для постоянной работы HTTPS надёжнее и безопаснее — [инструкция](docs/nastrojki/set-i-publikaciya.md)
5. Если VPN на другом сервере — добавьте узел — [Узлы](docs/uzly.md)
6. На **Конфигурации** нажмите **Синхронизировать** — [инструкция](docs/konfiguracii.md)
7. **Telegram** — раздел уже в меню; укажите bot token в UI — [инструкция](docs/Telegram.md)
8. Для **HA** (два сервера на один домен): создайте группу синхронизации на **Узлах**, выполните **Настройку** (домен → Push full → verify) — [Node Sync](docs/NodeSync.md). После обновления панели перезапустите **node agent** на VPN-узлах (`systemctl restart adminpanelaz-node`), чтобы в «Узлах» отображалась версия **1.6.0**

> [!NOTE]
> **Вход по умолчанию** (если не задавали в мастере): `admin` / `admin` — смените сразу.
> **Авто-бэкап** после install включён (каждые **7** дней) — изменить в [Настройки → Резервные копии](docs/nastrojki/rezervnye-kopii.md).

### 🗑️ Удаление и переустановка

```bash
sudo ./install.sh              # меню: переустановка или удаление
sudo ./install.sh --uninstall  # удалить сервисы панели
```

AntiZapret и VPN-конфиги при удалении панели **не трогаются**.

## 📖 Руководства пользователя

Полный список инструкций: **[docs/README.md](docs/README.md)**

- **VPN-клиенты** — [docs/konfiguracii.md](docs/konfiguracii.md)
- **Несколько серверов и HA** — [docs/uzly.md](docs/uzly.md) · [docs/NodeSync.md](docs/NodeSync.md)
- **NOC и трафик** — [docs/noc-monitoring.md](docs/noc-monitoring.md) · [docs/traffic-monitoring.md](docs/traffic-monitoring.md)
- **Настройки и бэкапы** — [docs/nastrojki/README.md](docs/nastrojki/README.md)
- **Адрес сайта, HTTPS, StatusOpenVPN** — [docs/nastrojki/set-i-publikaciya.md](docs/nastrojki/set-i-publikaciya.md)
- **Telegram** — [docs/Telegram.md](docs/Telegram.md)

## 🌐 Бесплатный адрес для панели (DDNS)

Если нет своего домена, в панели: **Настройки → Адрес сайта и HTTPS** → блок **Динамический DNS**:

### DuckDNS

1. [www.duckdns.org](https://www.duckdns.org/) — войдите и создайте **два** имени (обычно до 5 бесплатно): одно для VPN AntiZapret, другое для панели.
2. В DDNS панели укажите **панельный** поддомен + token.
3. Не используйте VPN-имя DuckDNS как домен панели — [подробнее](docs/nastrojki/set-i-publikaciya.md#duckdns-duckdnsorg).

### No-IP и свой домен

- [No-IP](https://www.noip.com) — `myvpn.ddns.net`
- Свой домен: на один hostname можно (и рекомендуется) повесить несколько A-записей на разные IP — удобно для VPN при двух серверах; для панели заведите отдельное имя.

Можно включить автообновление IP (systemd timer каждые 5 мин) и затем указать адрес панели в мастере HTTPS.

CLI (если нужно вручную): `sudo ./scripts/ddns-update.sh update|status`.

> [!TIP]
> Для HTTPS нужны открытые порты **80** и **443** на сервере. Свой домен тоже подойдёт — укажите его в том же разделе настроек.

## 🔗 StatusOpenVPN на одном домене

[StatusOpenVPN](https://github.com/TheMurmabis/StatusOpenVPN) занимает `https://домен/status/`. Если оба поставят отдельный nginx-сайт на один домен — будет конфликт.

**Установка → UI:** `sudo ./install.sh` (панель по HTTP) → **Настройки → Адрес сайта и HTTPS** → Nginx + Let's Encrypt → подпуть `panel` → **Интегрировать с StatusOpenVPN**. Итог: `https://домен/status/` и `https://домен/panel/`.

> [!WARNING]
> Подпуть обязателен. Не удаляйте Status через его `uninstall` после интеграции — может сломать nginx и доступ к панели.
> Если панель пропала — по SSH: `cd /opt/AdminPanelAZ && sudo ./scripts/nginx-repair.sh`

Подробно: [docs/nastrojki/set-i-publikaciya.md](docs/nastrojki/set-i-publikaciya.md#совместно-со-statusopenvpn-на-одном-домене)

## ⚙️ Production: VDS, Redis и профили

После установки: профиль **Full**, `UVICORN_WORKERS=1`. Профиль и модули меняются в **Настройки → Модули** ([инструкция](docs/nastrojki/moduli.md)), затем `sudo systemctl restart adminpanelaz`.

**Ориентир по RAM** (Full, панель + локальная нода): ~**411 MB** стек (ср. ~148 MB за 7 дней). Для одного VDS с VPN — **1–2 GB**; только панель на Minimal — **1 GB** + swap.

**Workers > 1:** в `backend/.env` задайте `UVICORN_WORKERS=N` и Redis (`AUTH_RATE_LIMIT_BACKEND=redis`, `API_RATE_LIMIT_BACKEND=redis`, `REDIS_URL=redis://127.0.0.1:6379/0`), затем перезапустите панель. См. [SECURITY.md](SECURITY.md).

**LAN-ноды / mTLS:** приватные IP узлов — `ALLOW_INTERNAL_NODES=true` в `.env`; mTLS — per-node в UI **Узлы**. Подробнее: [docs/uzly.md](docs/uzly.md).

- **Health** — `GET /api/health`, `GET /api/health/deep`
- **Метрики** — `GET /metrics` (Prometheus)
- **Node agent** — **1.6.0** (для HA: ≥ 1.3.0; byte-copy `.ovpn` при Push full: ≥ 1.5.0; сроки сертификатов: ≥ 1.6.0)

## 🔐 Безопасность

Перед выходом панели в интернет:

- HTTPS
- Смена пароля и **2FA**
- Белый список IP

- **Адрес сайта и HTTPS** — [docs/nastrojki/set-i-publikaciya.md](docs/nastrojki/set-i-publikaciya.md)
- **Профиль и 2FA** — [docs/nastrojki/profil.md](docs/nastrojki/profil.md)
- **Доступ к панели** — [docs/nastrojki/bezopasnost.md](docs/nastrojki/bezopasnost.md)
- **Технические детали** — [SECURITY.md](SECURITY.md)

## 💻 Полезные команды на сервере

```bash
cd /opt/AdminPanelAZ
sudo ./scripts/adminpanel-menu.sh   # меню: перезапуск, бэкап, обновление
sudo systemctl restart adminpanelaz # перезапуск панели
sudo ./scripts/nginx-setup.sh       # сменить HTTPS после установки
sudo ./scripts/nginx-repair.sh      # восстановить nginx (например после uninstall StatusOpenVPN)
```

## 📝 История изменений

<p align="center">
  <img src="docs/assets/telegram-promo/05-whats-new.png" alt="Последние обновления AdminPanel AntiZapret" width="900">
</p>

**Текущая версия: панель 2.19.0 · node agent 1.6.0** (2026-07-30)

После установки панель сразу открывается по `http://IP:порт/`; домен и HTTPS — в **Настройки → Адрес сайта и HTTPS**. Python **3.12** (Ubuntu) / **3.13** (Debian) выбирается автоматически.

Полный список: **[CHANGELOG.md](CHANGELOG.md)** · runbook аудита HA: [reviews/HA-sync-remediation-plan.md](reviews/HA-sync-remediation-plan.md)

## 💬 Обратная связь

Пожелания, баги и идеи — на доске **[AdminPanelAZ на Fider](https://claymore0098.fider.io/)**.

Перед новой записью **поищите похожие** — если тема уже есть, проголосуйте за неё, а не создавайте дубликат. GitHub не нужен.

## 💖 Поддержка проекта

- Донат: [cloudtips.ru](https://pay.cloudtips.ru/p/3c6704ca)
- Приватная группа Telegram: [Приватная группа в Telegram](https://t.me/+XJwXHTmMvUk3NTli)
- Личные сообщения: [Личные сообщения](https://t.me/Claymore0098)

---

*Сделано с ❤️ для сообщества AntiZapret · [⭐ Star на GitHub](https://github.com/Kirito0098/AdminPanelAZ)*
