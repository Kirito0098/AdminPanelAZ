# 🛡️ AdminPanel AntiZapret

Веб-панель для администрирования VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN)

[![GitHub](https://img.shields.io/badge/GitHub-Kirito0098%2FAdminPanelAZ-181717?style=for-the-badge&logo=github)](https://github.com/Kirito0098/AdminPanelAZ)
[![Version](https://img.shields.io/badge/Панель-2.19.0-blue?style=for-the-badge)](CHANGELOG.md)
[![Node agent](https://img.shields.io/badge/Node_agent-1.5.0-555?style=for-the-badge)](CHANGELOG.md)
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
- **Разработчики** — [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md) · [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) · [HA / Node Sync](docs/NodeSync.md)

## 🚀 Быстрый старт

**Требования:** Ubuntu 24.04+ или Debian 13+, root / sudo, доступ в интернет.
AntiZapret ставится **отдельно** на VPN-сервер — см. [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN).

**Python:** установщик сам выбирает runtime через `scripts/python-runtime.sh` — на **Ubuntu 24.04** это **3.12**, на **Debian 13** — **3.13**. Вручную указывать версию не нужно.

### Порты

После `install.sh` панель слушает **HTTP напрямую** (`0.0.0.0:<порт>`, обычно **8000**). Nginx и HTTPS **не** ставятся из установщика.

| Порт | Назначение | Куда открывать |
| --- | --- | --- |
| **8000** (или выбранный) | Панель (uvicorn, `http_direct`) | LAN / интернет — **пока** панель на этом порту; **не закрывайте** его до перехода на Nginx |
| **9100** | Node agent | localhost или между панелью и VPN-узлом |
| **80** / **443** | HTTP ACME / HTTPS (Nginx) | в интернет — **после** настройки в UI |
| **6379** | Redis | localhost — только если `UVICORN_WORKERS > 1` |

Порты **OpenVPN / WireGuard / AmneziaWG** задаёт **AntiZapret** на VPN-сервере, не панель.
Firewall из мастера **не** настраивается — откройте порт панели у хостера или вручную (`ufw` / security group). После публикации через Nginx UI может открыть **80**/**443** сам. Подробнее: [SECURITY.md](SECURITY.md).

> HTTPS и домен — только в панели: **Настройки → Адрес сайта и HTTPS**.
> Нестандартный HTTPS-порт: `HTTPS_PUBLIC_PORT` в `backend/.env` или через UI публикации.

### Варианты установки

Первый вопрос мастера — **что ставим на этот сервер**. Три сценария:

| Вариант | Что ставится | Когда выбирать |
| --- | --- | --- |
| **Только панель** | Веб-интерфейс управления | Отдельный **управляющий сервер**; к нему потом подключаются VPN-узлы (AntiZapret на других машинах) |
| **Панель + узел** | Панель и **локальный узел** на одном хосте | **AntiZapret уже установлен** на этом же сервере (`/root/antizapret`) — типичный случай «всё на одном VDS» |
| **Узел** | Только **node agent** (без панели) | Отдельный **VPN-сервер**, который нужно **подключить к уже работающей панели** на другом хосте |

#### Установка

Один путь — `install.sh` (systemd, профиль **full**, HTTP по IP:порт):

```bash
sudo apt update && sudo apt install -y git wget curl
wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
sudo bash /tmp/install.sh
```

Мастер спросит: тип установки, порты (панель; node agent — если ставите узел), логин/пароль администратора, ключ node agent (если нужен) и пути (бэкапы).

**Не спрашивает:** HTTPS/домен/публикацию, DDNS, `APP_ENV`, firewall, workers/Redis, mTLS, профиль ресурсов, Telegram — дефолты: HTTP по IP:порт, `production`, systemd, workers=1, профиль Full.

После установки откройте `http://IP:порт/` из вывода мастера. Рекомендуется в панели:

- **Настройки → Адрес сайта и HTTPS** — DDNS (DuckDNS/No-IP), домен, Let's Encrypt, nginx/uvicorn
- **Telegram** — bot token / chat (модуль уже в меню)
- LAN-ноды — при необходимости `ALLOW_INTERNAL_NODES=true` в `backend/.env`
- workers/Redis, mTLS — вручную / UI, см. [Production](#️-production-vds-redis-и-профили)

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
4. Для домена/HTTPS — **Настройки → Адрес сайта и HTTPS** — [инструкция](docs/nastrojki/set-i-publikaciya.md)
5. Если VPN на другом сервере — добавьте узел — [Узлы](docs/uzly.md)
6. На **Конфигурации** нажмите **Синхронизировать** — [инструкция](docs/konfiguracii.md)
7. **Telegram** — раздел уже в меню; укажите bot token в UI — [инструкция](docs/Telegram.md)
8. Для **HA** (два сервера на один домен): создайте группу синхронизации на **Узлах**, выполните **Настройку** (домен → Push full → verify) — [Node Sync](docs/NodeSync.md). После обновления панели перезапустите **node agent** на VPN-узлах (`systemctl restart adminpanelaz-node`), чтобы в «Узлах» отображалась версия **1.5.0**

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

- [DuckDNS](https://www.duckdns.org) — `myvpn.duckdns.org`
- [No-IP](https://www.noip.com) — `myvpn.ddns.net`

Можно включить автообновление IP (systemd timer каждые 5 мин) и затем указать этот адрес в мастере HTTPS.

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

После `install.sh` всегда профиль **Full** и `UVICORN_WORKERS=1`. Урезать нагрузку или включить лишнее — в UI, не в установщике.

Профили (**Minimal / Standard / Full**) меняют **фоновые задачи панели** (collectors, CIDR scheduler).
В UI на вкладке **Модули** показывается замер **только стека AdminPanelAZ**: панель + локальная нода и её
VPN-сервисы (`ANTIZAPRET_PATH`). Сторонние проекты на том же VDS не входят в цифру.

**Замер на реальном сервере (профиль Full, панель + локальная нода):**

- **Текущий стек** — AdminPanelAZ **358 MB** + нода **53 MB** ≈ **411 MB**
- **Средний стек за 7 дней** — ~**148 MB**
- **Minimal / Standard** — меньше нагрузка на панель (без части collectors); VPN на хосте тот же

| Сценарий | Стек (замер / ориентир) | VDS RAM |
| --- | --- | --- |
| Только панель, профиль Minimal (VPN на других узлах) | без локальной ноды в замере | **1 GB** + swap |
| Панель + node agent + VPN на одном VDS, профиль Full | **~411 MB** (358 + 53); ср. ~148 MB | **1 GB+** (лучше **2 GB** с запасом под ОС и VPN) |
| Профиль Standard | между Minimal и Full | **1 GB+** |

Профиль и модули: **Настройки → Модули**. После смены профиля:

```bash
sudo systemctl restart adminpanelaz
```

Подробнее: [docs/nastrojki/moduli.md](docs/nastrojki/moduli.md).

### Несколько uvicorn workers

По умолчанию один worker. Чтобы увеличить:

1. В `backend/.env`: `UVICORN_WORKERS=N` (N > 1)
2. Обязательно Redis для rate limit: `AUTH_RATE_LIMIT_BACKEND=redis`, `API_RATE_LIMIT_BACKEND=redis`, `REDIS_URL=redis://127.0.0.1:6379/0`
3. `sudo systemctl restart adminpanelaz`

См. [SECURITY.md](SECURITY.md).

### LAN-ноды, mTLS, ротация ключа

- Узлы с приватными IP (`192.168…`, `10…`): в `backend/.env` `ALLOW_INTERNAL_NODES=true`, затем `systemctl restart adminpanelaz` — [Узлы](docs/uzly.md)
- mTLS панель ↔ agent — per-node в UI **Узлы → Включить mTLS** (не из install)
- Авторотация API-ключа: `NODE_API_KEY_ROTATION_DAYS` в `backend/.env` (`0` = выкл.)

- **Health** — `GET /api/health` (лёгкий), `GET /api/health/deep` (БД, CIDR, traffic lag)
- **Метрики** — `GET /metrics` — Prometheus (`traffic_collector_lag_seconds`, `node_health_*`)
- **Node agent** — версия **1.5.0** (минимум **≥ 1.3.0** для HA crypto-sync и verify; **≥ 1.5.0** для byte-copy `.ovpn` при Push full); отображается в **Узлы** → health узла

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
sudo systemctl restart adminpanelaz # перезапуск панели (если установлен systemd)
sudo ./scripts/nginx-setup.sh       # сменить HTTPS после установки
sudo ./scripts/nginx-repair.sh      # восстановить nginx (например после uninstall StatusOpenVPN)
```

## 📝 История изменений

<p align="center">
  <img src="docs/assets/telegram-promo/05-whats-new.png" alt="Последние обновления AdminPanel AntiZapret" width="900">
</p>

**Текущая версия: панель 2.19.0 · node agent 1.5.0** (2026-07-26)

Последний релиз — **HTTP по умолчанию** (`http://IP:порт` сразу после install), **один `install.sh`** без easy и без выбора HTTPS, домен/TLS в **Настройки → Адрес сайта и HTTPS**, **systemd → `scripts/systemd-exec-*.sh`** (тонкие compat-shim `start.sh` только для старых unit’ов), Python **3.12 (Ubuntu) / 3.13 (Debian)** автоматически.

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
