# AdminPanel AntiZapret

> **⚠️ Статус проекта**
>
> Проект находится на этапе **переноса функциональности и тестирования**. Решение о долгосрочной поддержке и сопровождении **ещё не принято**.
>
> **AdminPanelAZ** — экспериментальный порт панели [AdminAntizapret](https://github.com/Kirito0098/AdminAntizapret) на стек **FastAPI + React** (TypeScript, Vite). Основной репозиторий, которым рекомендуется пользоваться на данный момент: [**AdminAntizapret**](https://github.com/Kirito0098/AdminAntizapret).
>
> *Project status: experimental FastAPI+React port of [AdminAntizapret](https://github.com/Kirito0098/AdminAntizapret) — functionality migration and testing in progress; long-term maintenance TBD.*

Веб-панель администрирования для VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN).

Стек: **FastAPI** (backend) + **React/Vite/TypeScript** (frontend: Tailwind CSS, shadcn/ui, Recharts).

Документация: [`MIGRATION.md`](MIGRATION.md) · [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) · [`SECURITY.md`](SECURITY.md) · [`CHANGELOG.md`](CHANGELOG.md)

---

## Статус переноса из AdminAntizapret

Сравнение с upstream [AdminAntizapret](https://github.com/Kirito0098/AdminAntizapret) **1.9.0** (Flask + Jinja2). AdminPanelAZ **1.0.0** — релиз после фазы 20 (parity audit). Полные таблицы, карта файлов и backlog — в [`MIGRATION.md`](MIGRATION.md). Поэтапный план (20 фаз) — в [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md).

**Оценка готовности:** ~**92–95%** функциональности AA 1.9.0 перенесено или покрыто эквивалентами; оставшиеся пробелы — в backlog [`MIGRATION.md`](MIGRATION.md#backlog-переноса-приоритеты).

| Маркер | Значение |
|--------|----------|
| ✅ | Перенесено — API и UI работают |
| 🟡 | Частично — упрощённый порт или подмножество возможностей |
| ❌ | Не перенесено |
| 🆕 | Есть только в AdminPanelAZ |

### Сводка по областям

| Область | Статус | Комментарий |
|---------|--------|-------------|
| VPN-клиенты (OpenVPN, WireGuard, AmneziaWG) | ✅ | CRUD, sync, download, QR |
| Политики доступа (блок, срок, лимиты) | ✅ | OpenVPN + WG/AWG + TG notify |
| Синхронизация и графики трафика | ✅ | Collector + «Мониторинг трафика» |
| Маршрутизация / CIDR | ✅ | Pipeline, presets CRUD, AntiZapret config, game filters include/exclude |
| Редактор файлов AntiZapret | ✅ | Мультифайловый редактор + apply + diff-подсветка |
| Мониторинг сервера (CPU/RAM/vnstat) | ✅ | Страница «Сервер» |
| NOC / клиенты / логи | ✅ | Monitoring + Logs + экспорт action logs |
| Безопасность | ✅ | IP whitelist, temp whitelist, scanner (вкл. dwell/window), rate limit |
| QR / одноразовые ссылки | ✅ | SecurityTab (TTL, PIN, max downloads 1/3/5) |
| Бэкапы (ручные + авто + TG) | ✅ | + `client.sh 8` в BackupTab |
| Feature toggles | ✅ | 23 toggles (parity AA + `NIGHTLY_IDLE_RESTART`) |
| Telegram Login + Mini App | ✅ | |
| Telegram admin-уведомления | ✅ | Login, config ops, settings, CPU/RAM, traffic limits, ban/unban, user ops |
| Auth (login, captcha, роли) | ✅ | + 🆕 2FA/TOTP, refresh tokens |
| Viewer role | ✅ | API + UI назначения доступа в UsersTab |
| Обновление системы (git) | ✅ | + 🆕 node agent / AntiZapret на узлах |
| In-panel pytest | ✅ | 53 модуля / 414 тестов; parity audit (`test_aa_parity_audit.py`) |
| Установка / ops | ✅ | `install.sh` + `scripts/adminpanel-menu.sh`; diagnostics/safe-browsing CLI ✅ |
| Multi-node | 🆕 | Controller + Node Agent |
| CI/CD | ✅ | pytest + ruff + build + shellcheck + eslint; pip-audit/bandit advisory |

---

## Production readiness

Чеклист перед использованием AdminPanelAZ вместо upstream AdminAntizapret на реальном VPN-сервере. Проект по-прежнему **экспериментальный** — долгосрочная поддержка не гарантирована.

### Готово к production-пилоту

- [x] VPN-клиенты OpenVPN / WireGuard / AmneziaWG (CRUD, sync, download, QR, public routes)
- [x] Политики доступа, лимиты трафика, reconcile + TG notify
- [x] Маршрутизация / CIDR pipeline, game filters include (~75), presets CRUD, вкладка «Конфиг AntiZapret»
- [x] Мониторинг: трафик, подключённые клиенты, CPU/RAM, vnstat, WebSocket
- [x] Безопасность: JWT, captcha, 2FA/TOTP, IP whitelist (+ temp 1h/12h/24h UI), scanner ipset/iptables, global API rate limit
- [x] Бэкапы панели + AntiZapret (`client.sh 8`), авто-бэкап, TG-доставка
- [x] Telegram Login, Mini App, AdminNotify (все основные события, включая ban/unban и user ops)
- [x] Multi-node: local + remote через Node Agent (mTLS)
- [x] Установка: `install.sh`, nginx, firewall scripts, site-diagnostics CLI
- [x] CI: pytest (414), ruff, frontend build, shellcheck, eslint
- [x] Документация: [`MIGRATION.md`](MIGRATION.md), [`SECURITY.md`](SECURITY.md), [`docs/Telegram.md`](docs/Telegram.md)

### Перед production — проверить вручную

- [ ] **Multi-node remote** — обновление agent, бэкап `client.sh 8`, routing apply на удалённом узле
- [ ] **2FA/TOTP** — вход с включённым TOTP, recovery codes
- [ ] **Nginx + TLS** — `scripts/nginx-setup.sh`, `BEHIND_NGINX`, сертификаты
- [ ] **Firewall** — `scripts/firewall-setup.sh`; backend на `127.0.0.1` за reverse proxy
- [ ] **Telegram** — Login Widget, Mini App, AdminNotify на реальный `telegram_id`
- [x] **In-panel pytest** — вкладка «Тесты» в настройках (или `cd backend && pytest`); 53 модуля / 414 тестов

### Известные пробелы vs AdminAntizapret 1.9.0

| Пробел | Обходной путь |
|--------|----------------|
| Custom SSL certs в VPN wizard | `sudo ./scripts/nginx-setup.sh` (интерактивно) |

### 🆕 Только в AdminPanelAZ (сверх AA 1.9.0)

| Возможность | Где |
|-------------|-----|
| **Multi-node** — Controller + Node Agent, per-node scoping в БД | [`nodes.py`](backend/app/routers/nodes.py), [`NodesPage`](frontend/src/pages/NodesPage.tsx) |
| **NOC-мониторинг** — метрики VPN-узла и панели, история CPU/RAM | [`MonitoringPage`](frontend/src/pages/MonitoringPage.tsx) |
| **2FA/TOTP** + refresh tokens | [`TwoFactorTab`](frontend/src/components/settings/TwoFactorTab.tsx), [`auth.py`](backend/app/routers/auth.py) |
| **Обновление node agent и AntiZapret** с панели | [`NodeUpdateDialog`](frontend/src/components/NodeUpdateDialog.tsx) |
| **Per-node mTLS** panel ↔ agent (кнопка в UI) | [`NodesPage`](frontend/src/pages/NodesPage.tsx), [`node_mtls_provision.py`](backend/app/services/node_mtls_provision.py) |
| **DDNS timer** (DuckDNS / No-IP) | `systemd/adminpanelaz-ddns.*`, `scripts/ddns-update.sh` |
| **Роль `user`** (между admin и viewer) | [`models.py`](backend/app/models.py) |
| **Глобальный rate limit** `/api/*` | [`api_rate_limit.py`](backend/app/middleware/api_rate_limit.py) |
| **React SPA** (Vite, Tailwind, shadcn/ui) | [`frontend/src/`](frontend/src/) |

---

## Установка

**Единственный поддерживаемый способ установки** — интерактивный мастер `install.sh` (клонирование репозитория, зависимости, мастер, systemd/nginx — всё в одном скрипте). Запускайте скрипт **с TTY** (SSH-сессия, локальный терминал), чтобы мастер мог задать вопросы.

> **⚠️ Не используйте `wget|curl | sudo bash`**
>
> Передача скрипта через pipe **не даёт TTY** — интерактивный мастер и меню не запускаются. Установщик **откажется продолжать** без явных флагов (`--non-interactive`, `--with-systemd`, `--node-only` и т.д.), чтобы не установить панель «молча» с настройками по умолчанию.
>
> *Do not pipe install.sh into bash — no TTY, no wizard. Download the script and run `sudo bash /tmp/install.sh`, or pass explicit flags.*

### Рекомендуемая установка

Стандартный каталог — **`/opt/AdminPanelAZ`** (переопределяется через `INSTALL_TARGET`).

На **Ubuntu 24.04+** или **Debian 13+** с `root`/`sudo`, `git` и доступом в интернет:

```bash
sudo apt update && sudo apt install -y git wget curl
wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
sudo bash /tmp/install.sh
```

Альтернатива через `curl`:

```bash
curl -fsSL -o /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
sudo bash /tmp/install.sh
```

Скрипт клонирует репозиторий в `/opt/AdminPanelAZ` (или в `INSTALL_TARGET`) и запускает интерактивный мастер. Другой форк или каталог:

```bash
wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
sudo INSTALL_FROM_GIT=https://github.com/you/AdminPanelAZ.git INSTALL_TARGET=/opt/my-panel bash /tmp/install.sh
```

### Установка из уже клонированного репозитория

```bash
cd /opt/AdminPanelAZ
sudo ./install.sh
```

### Только Node agent (VPN-сервер без панели)

**Интерактивно:** в мастере выберите пункт **«Только Node agent»** (вариант 3 на шаге «Тип установки»).

**Без TTY (automation):**

```bash
sudo bash /tmp/install.sh --node-only --with-systemd -y
```

Флаг `--with-node-agent` добавляет агент **вместе с панелью**, а не вместо неё — для node-only используйте `--node-only` или мастер.

### Автоматизация без TTY (CI)

`--non-interactive -y` без `WIZ_*` — **минимальная dev-установка** (admin/admin, без Nginx/DDNS/firewall).
Для production передайте флаги **и** экспортируйте `WIZ_*` (см. `./install.sh --help`):

```bash
sudo bash /tmp/install.sh --non-interactive --with-systemd -y
# node-only:
sudo bash /tmp/install.sh --node-only --with-systemd -y
# production + Let's Encrypt (пример):
export WIZ_APP_ENV=production WIZ_NGINX_MODE=le WIZ_NGINX_DOMAIN=panel.example.com
export WIZ_NGINX_EMAIL=admin@example.com WIZ_CONFIGURE_FIREWALL=true
sudo bash /tmp/install.sh --non-interactive --with-systemd -y
```

**Почему не `sudo bash <(wget …)`?** Process substitution `<(wget …)` создаёт fd в текущей оболочке; `sudo bash` запускает новый процесс без доступа к этому fd — ошибка `bash: /dev/fd/63: No such file or directory`. Скачивание в файл (`/tmp/install.sh`) решает проблему.

Другие пути (ручная настройка systemd, отдельный запуск `nginx-setup.sh` как установщик, `start.sh` вместо install) **не предусмотрены**. Скрипты `scripts/nginx-setup.sh`, `scripts/uninstall.sh` и др. — **утилиты после установки**, не альтернатива `install.sh`.

### Предварительные требования

| Требование | Описание |
|------------|----------|
| ОС | **Ubuntu 24.04+** или **Debian 13+** (другие дистрибутивы — на свой риск) |
| Права | `root` или `sudo` |
| Сеть | Доступ в интернет для apt, npm, pip, Let's Encrypt |
| Репозиторий | Клонирование в `/opt/AdminPanelAZ` (install.sh делает это автоматически) |
| AntiZapret (VPN) | Устанавливается **отдельно** на VPN-сервере в каталог **`/root/antizapret`** ([AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN)). AdminPanelAZ не ставит AntiZapret — только проверяет наличие `client.sh` и пишет `ANTIZAPRET_PATH=/root/antizapret` в конфиг. |

```bash
# Пример: сначала AntiZapret на VPN-сервере (если нужен локальный VPN)
# curl -s ... | bash   # см. инструкции AntiZapret-VPN

# Затем панель (скачать install.sh и запустить с TTY)
sudo apt update && sudo apt install -y git wget curl
wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
sudo bash /tmp/install.sh

# Или вручную: git clone + install.sh
# sudo git clone https://github.com/Kirito0098/AdminPanelAZ.git /opt/AdminPanelAZ
# cd /opt/AdminPanelAZ && sudo ./install.sh
```

При запуске `install.sh` вне каталога проекта установщик сам клонирует репозиторий (по умолчанию в `/opt/AdminPanelAZ`). Переопределение: `INSTALL_FROM_GIT=<url>`, `INSTALL_TARGET=<каталог>`.

Без аргументов в интерактивном режиме `install.sh` показывает меню:

| Пункт | Действие |
|-------|----------|
| 1. Новая установка | Мастер установки (как раньше) |
| 2. Переустановка | Резервная копия `.env` → удаление сервисов и состояния → новая установка |
| 3. Полное удаление | Остановка сервисов, опционально nginx/firewall/каталог проекта |
| 4. Справка | `./install.sh --help` |

### Удаление и переустановка

**Переустановка** (сохраняет каталог проекта, удаляет сервисы и состояние):

```bash
sudo ./install.sh --reinstall
sudo ./install.sh --reinstall --non-interactive --with-systemd -y
```

Перед удалением создаётся резервная копия `backend/.env` в `.reinstall-backup/`; после установки можно восстановить конфигурацию.

**Полное удаление** (для чистой переустановки или снятия панели с сервера):

```bash
sudo ./install.sh                          # меню: п.3 — удаление сервисов, п.4 — без следов
sudo ./install.sh --uninstall              # интерактивно, с подтверждением
sudo ./install.sh --uninstall -y           # сервисы + состояние + nginx + firewall
sudo ./install.sh --purge-all -y           # всё без следов (проект, БД, бэкапы)
sudo ./install.sh --uninstall --purge -y   # то же через флаги uninstall + purge
sudo ./scripts/uninstall.sh --purge-state --remove-nginx -y
```

Что удаляется / что сохраняется:

| Компонент | По умолчанию при `--uninstall` | Опции |
|-----------|-------------------------------|--------|
| systemd (`adminpanelaz`, `adminpanelaz-node`, DDNS timer) | Да | — |
| daemon / watchdog (`start.sh`, `start_node_agent.sh`) | Да | — |
| Каталоги состояния (`/var/lib/adminpanelaz`, `.runtime`) | Интерактивно (по умолчанию да) / да с `-y` | `--purge-state` в uninstall.sh |
| nginx-сайт панели | Интерактивно / да с `-y` | `--remove-nginx` |
| Правила firewall (ufw / iptables) | Интерактивно / да с `-y` | `--remove-firewall` |
| `backend/.env`, `node_agent.env` | Нет | `--remove-env` |
| `/etc/adminpanelaz/ddns.env` | Да (через install.sh) | `--remove-system-config` |
| Каталог проекта `/opt/AdminPanelAZ` | **Нет** (п.4 меню / `--purge-all`) | `--purge` |
| Бэкапы (`/var/backups/adminpanelaz`) | **Нет** (п.4 меню / `--purge-all`) | `--remove-backups` |
| AntiZapret (`/root/antizapret`) | **Никогда** | — |

Подтверждение: в интерактивном режиме нужно ввести `yes` или `AdminPanelAZ`.

### Что делает `install.sh`

1. Проверяет ОС и права root
2. Запускает интерактивный мастер (`scripts/install-wizard.sh`)
3. Устанавливает системные зависимости (Python, Node.js, build tools)
4. Создаёт `backend/.env`, собирает frontend, инициализирует БД
5. По выбору: systemd / daemon; Nginx + certbot, DDNS и firewall — при выборе в мастере (или через `WIZ_*`)
6. Выводит учётные данные и URL

### Шаги мастера установки

Нажимайте **Enter** для значения по умолчанию в `[скобках]`.

#### 1. Тип установки

| Вариант | Когда выбирать |
|---------|----------------|
| Только панель | Панель на отдельном сервере, VPN-узлы удалённые |
| Панель + локальный AntiZapret | Панель и VPN на одном хосте; **AntiZapret уже установлен** в `/root/antizapret` |
| Только Node agent | Только агент на VPN-сервере (без панели); AntiZapret в `/root/antizapret` |

Путь к AntiZapret **не спрашивается** — всегда `/root/antizapret`. Если каталог не найден, установщик предупреждает; для вариантов с VPN установка прерывается до установки AntiZapret.

#### 2. Сеть и порты

- **IP или домен** — для CORS и подсказок (можно заполнить на шаге DDNS)
- **Порт backend** — внутренний порт uvicorn (по умолчанию `8000`, только `127.0.0.1`)
- **Порт node agent** — если установлен агент (по умолчанию `9100`)
- **ALLOW_INTERNAL_NODES** — разрешить внутренние IP для удалённых узлов

Рекомендуется: backend только на localhost, наружу — через Nginx (шаг 4).

#### 2a. Динамический DNS (DDNS)

Если нет своего домена — выберите бесплатный DDNS (см. раздел [Бесплатные домены](#бесплатные-домены-и-ddns) ниже).

- **DuckDNS** — поддомен + token, автообновление IP через systemd timer
- **No-IP** — hostname + логин/пароль
- **Не использую** — свой домен или прямой IP

При выборе DuckDNS/No-IP установщик создаёт `/etc/adminpanelaz/ddns.env`, выполняет первое обновление IP и (опционально) ставит timer на обновление каждые 5 минут.

#### 3. Режим приложения

- **development** — локальные тесты
- **production** — рекомендуется для доступа из интернета/LAN (автогенерация `SECRET_KEY`, политика паролей, security headers)

#### 4. Публикация через Nginx

| Вариант | Назначение |
|---------|------------|
| Nginx + Let's Encrypt | Домен в интернете, бесплатный HTTPS (рекомендуется) |
| Nginx + самоподписанный | LAN / внутренняя сеть |
| Пропустить Nginx | Только `127.0.0.1` (dev/тесты) |
| HTTP без Nginx | Не рекомендуется для интернета |

Для Let's Encrypt укажите **домен** (подставится из DDNS, если настроен) и **email**. Порты по умолчанию: HTTPS `443`, HTTP `80` (нужен для ACME).

Установщик ставит nginx, получает сертификат certbot, настраивает reverse proxy и обновляет `backend/.env` (`BEHIND_NGINX`, `DOMAIN`, CORS).

#### 5. Администратор

Логин, пароль (Enter — случайный), принудительная смена пароля при первом входе.

#### 6. Node agent

API-ключ (автогенерация или вручную), разрешённые IP панели.

#### 6a. Дополнительная безопасность

- **Панель (controller):** Redis для rate limit при workers > 1, опционально mTLS, ротация API-ключей узлов
- **Node agent:** опционально mTLS (`scripts/generate-mtls-certs.sh` после установки)

#### 7. Сервисы и автозапуск

| Режим | Описание |
|-------|----------|
| Вручную | `./start.sh` / `./start_node_agent.sh` |
| Daemon | `start.sh daemon` с watchdog |
| **Systemd** | Рекомендуется для production |

Количество uvicorn workers (при `>1` нужен Redis для rate limit).

#### 8. Опциональные функции

CIDR DB refresh, сбор трафика, Telegram, автобэкапы.

#### 9. Пути

Каталог бэкапов (`BACKUP_ROOT`). Каталоги состояния задаются автоматически: `/var/lib/adminpanelaz` и `/var/lib/adminpanelaz-node` при systemd, иначе `.runtime/` в каталоге проекта.

#### 10. Firewall

Автонастройка ufw/iptables: закрыть backend/node с интернета, открыть HTTPS/HTTP для Nginx. Рекомендуется при `production`.

#### Сводка и подтверждение

Проверьте параметры и подтвердите установку.

### После установки

1. **Откройте панель** — URL в конце вывода `install.sh` (`https://ваш-домен/` или `http://127.0.0.1:8000/`)
2. **Войдите** — логин/пароль из вывода установщика (по умолчанию `admin` / сгенерированный)
3. **Смените пароль** — если включена принудительная смена
4. **Включите 2FA** — Настройки → безопасность (TOTP)
5. **Добавьте узлы** — страница «Узлы», укажите IP node agent и API-ключ (сначала **HTTP** + API-ключ). Опционально для каждого удалённого узла: меню → **«Включить mTLS»** — панель сгенерирует и доставит сертификаты автоматически (см. [`SECURITY.md`](SECURITY.md#mtls-per-node-включение-из-панели))

Управление (не установка; команды из `/opt/AdminPanelAZ` или вашего `INSTALL_TARGET`):

```bash
cd /opt/AdminPanelAZ
sudo ./scripts/adminpanel-menu.sh      # ops-меню: restart, backup, update, pytest, diagnose
systemctl status adminpanelaz          # если выбран systemd
./start.sh status                      # если daemon
sudo ./scripts/nginx-setup.sh          # сменить режим HTTPS после установки (или Настройки → VPN-сеть → мастер публикации)
sudo ./scripts/ddns-update.sh status   # статус DDNS
sudo ./scripts/uninstall.sh --purge-state -y   # полное удаление сервисов и состояния
sudo ./install.sh --reinstall                  # переустановка через меню install.sh
```

Подробнее о безопасности: [`SECURITY.md`](SECURITY.md).

---

## Производительность фоновых задач

Фоновые workers (traffic sync, WG policy sync, health, metrics) работают **внутри процесса uvicorn**, без отдельных cron-скриптов как в AdminAntizapret. WG runtime (`wg set` / HTTP к node agent) применяется **только при изменении политики**, кроме первого запуска `wg_policy_sync` после старта панели (полная синхронизация runtime).

Настройка через `backend/.env`:

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `TRAFFIC_SYNC_ENABLED` | `true` | Сбор трафика в SQLite |
| `TRAFFIC_SYNC_INTERVAL_SECONDS` | `60` | Интервал traffic worker |
| `TRAFFIC_LIMIT_RECONCILE_AFTER_SYNC` | `true` | Reconcile лимитов после каждого сбора |
| `WG_POLICY_SYNC_ENABLED` | `true` | Фоновый reconcile WG/AWG политик |
| `WG_POLICY_SYNC_INTERVAL_SECONDS` | `120` | Интервал wg policy worker |
| `NODE_HEALTH_SYNC_INTERVAL_SECONDS` | `60` | Опрос статуса узлов |
| `RESOURCE_METRICS_INTERVAL_SECONDS` | `60` | Сбор CPU/RAM узлов |
| `PANEL_RESOURCE_METRICS_INTERVAL_SECONDS` | `60` | Метрики самой панели |
| `MONITORING_OVERVIEW_CACHE_TTL_SECONDS` | `20` | TTL кэша `GET /monitoring/overview` на remote node (0 = выкл.) |

По умолчанию `TRAFFIC_SYNC_INTERVAL_SECONDS=60` — баланс для prod с лимитами трафика (задержка блокировки до ~60 с при `TRAFFIC_LIMIT_RECONCILE_AFTER_SYNC=true`). На слабом VPS или при очень большом числе клиентов можно увеличить до `90–120`; для жёстких лимитов — `30`. Отключать `TRAFFIC_LIMIT_RECONCILE_AFTER_SYNC` стоит только если понимаете задержку применения лимитов (до следующего wg policy sync).

В логах backend ищите строки `Traffic collect` и `WG policy sync` — поля `duration_ms`, `wg_runtime_calls`, `clients_changed` помогают оценить нагрузку.

---

## Работа с узлами и конфигурациями

Панель может управлять несколькими VPN-серверами (узлами). Список клиентов на странице **Конфигурации** всегда привязан к **активному узлу** — при переключении узла список обновляется автоматически.

### Локальный и удалённый узел

| Тип | Что это | Откуда читаются клиенты |
|-----|---------|-------------------------|
| **Локальный** | AntiZapret на том же сервере, где панель (`ANTIZAPRET_PATH` в `backend/.env`, по умолчанию `/root/antizapret`) | Файлы на диске этого сервера |
| **Удалённый** | VPN-сервер с **node agent** (отдельный хост) | Файлы на диске **того** сервера через API агента |

Записи в базе данных хранятся с полем `node_id`. Один и тот же `client_name` на разных узлах — **разные** записи.

### Как работает «Синхронизировать»

Кнопка **Синхронизировать** на странице конфигураций:

1. Берёт **только активный узел**
2. Читает список клиентов OpenVPN/WireGuard с **его** диска (локально или через node agent)
3. Добавляет в БД недостающие записи с `node_id` этого узла

Синхронизация **не копирует** `.ovpn`/`.conf` между серверами и **не удаляет** из БД клиентов, которых уже нет на диске.

### Правильный порядок действий

1. **Перезапустите backend** после обновления панели (миграция `node_id` выполняется при старте):
   ```bash
   sudo systemctl restart adminpanelaz   # если systemd
   # или ./start.sh restart
   ```
2. **Выберите активный узел** — переключатель в шапке или страница **Узлы** → «Сделать активным».
3. На **Конфигурации** нажмите **Синхронизировать** — импортируются клиенты **только с диска выбранного узла**.
4. **Переключите узел** — список должен смениться (другой набор клиентов).
5. **Создание нового клиента** — попадает только на активный узел (файлы создаются там же).

Для каждого удалённого узла повторите шаги 2–3 отдельно.

### Типичные ошибки

- **Синхронизировали на удалённом, а на локальном ждёте тех же клиентов** — у локального узла свой каталог AntiZapret; если там пусто, список будет пустым. Это нормально.
- **Один каталог AntiZapret «на всех»** — панель и node agent должны видеть **свой** `ANTIZAPRET_PATH` на **своём** сервере, не общую NFS/симлинк с чужими клиентами.
- **После исправления на локальном всё ещё видны чужие клиенты** — проверьте физические файлы в локальном `ANTIZAPRET_PATH` (`client.sh` / каталоги профилей). Если файлы есть только на удалённом сервере, пересинхронизируйте локальный узел; старые записи в БД с неверным `node_id` можно удалить вручную из списка (только для активного узла).

---

## Бесплатные домены и DDNS

Для публикации панели в интернете без покупки домена можно использовать бесплатный **динамический DNS (DDNS)** — поддомен, который указывает на ваш публичный IP. Установщик поддерживает **DuckDNS** и **No-IP**; остальные настраиваются вручную по инструкциям провайдера, затем домен указывается на шаге 4 мастера.

### Сравнение сервисов

| Сервис | Что даёт | Плюсы | Минусы | Let's Encrypt |
|--------|----------|-------|--------|---------------|
| [**DuckDNS**](https://www.duckdns.org) | `*.duckdns.org` | Бесплатно, без рекламы, простой API, встроен в install.sh | Только поддомены duckdns.org | HTTP-01 на порту 80 (работает из коробки) |
| [**No-IP**](https://www.noip.com) | `*.ddns.net`, `*.hopto.org` и др. | Известный сервис, встроен в install.sh | Бесплатный hostname нужно подтверждать раз в 30 дней | HTTP-01 на порту 80 |
| [**FreeDNS / afraid.org**](https://freedns.afraid.org) | Много зон (в т.ч. чужие домены) | Огромный выбор поддоменов | Сложнее интерфейс, зависимость от чужих зон | HTTP-01, если A-запись указывает на сервер |
| [**Dynu**](https://www.dynu.com) | `*.dynu.net` и др. | Бесплатный DDNS, клиенты под разные ОС | Ограничения бесплатного тарифа | HTTP-01 на порту 80 |
| [**deSEC**](https://desec.io) | DNS-хостинг | Бесплатный DNS для **своего** домена, API | Нужен купленный/бесплатный домен отдельно | DNS-01 или HTTP-01 |
| [**Cloudflare**](https://www.cloudflare.com) | DNS для своего домена | Бесплатный DNS, CDN, защита | Домен нужно **купить** у регистратора | HTTP-01 или DNS-01 (API token) |

### Как это работает с Let's Encrypt

1. DDNS обновляет **A-запись** вашего поддомена на текущий публичный IP сервера
2. Certbot (в `install.sh`) проверяет владение доменом через **HTTP-01**: запрос на `http://домен/.well-known/acme-challenge/...` должен прийти на этот сервер
3. **Порты 80 и 443** должны быть доступны с интернета (проброс на роутере, если сервер за NAT)
4. После получения сертификата certbot обновляет его автоматически (systemd timer)

При смене IP DDNS timer (`adminpanelaz-ddns.timer`) обновляет запись; сертификат Let's Encrypt от смены IP не зависит.

### DuckDNS (рекомендуется для homelab)

1. Зарегистрируйтесь на [duckdns.org](https://www.duckdns.org)
2. Создайте поддомен (например, `myvpn` → `myvpn.duckdns.org`)
3. Скопируйте **token**
4. В `install.sh` на шаге **2a** выберите DuckDNS, введите поддомен и token
5. На шаге **4** выберите Let's Encrypt, домен подставится автоматически

Ручное обновление IP:

```bash
sudo ./scripts/ddns-update.sh update
sudo ./scripts/ddns-update.sh status
```

### No-IP

1. Зарегистрируйтесь на [noip.com](https://www.noip.com)
2. Создайте hostname (например, `myvpn.ddns.net`)
3. В `install.sh` на шаге **2a** выберите No-IP, введите hostname, логин и пароль
4. Не забудьте подтверждать hostname каждые 30 дней (бесплатный план)

### Свой домен / Cloudflare / deSEC

Купите домен у регистратора, делегируйте DNS на Cloudflare или deSEC, создайте A-запись на публичный IP сервера. В мастере на шаге **2a** выберите «Не использую DDNS», на шаге **4** — Let's Encrypt и укажите свой домен.

---

## Firewall и Nginx

При установке с Nginx backend слушает **только** `127.0.0.1:8000`. Наружу открыты порты Nginx (по умолчанию 443/80). Firewall (шаг в конце мастера) закрывает прямой доступ к backend и node agent с интернета.

Шаблоны Nginx: `deploy/nginx/`. Изменить HTTPS после установки:

```bash
sudo ./scripts/nginx-setup.sh
```

---

## Вход по умолчанию

- `admin` / `admin` (или пароль из вывода установщика — **смените при первом входе**)

---

## Безопасность

Перед публикацией в интернет: [`SECURITY.md`](SECURITY.md) — production-секреты, HTTPS, 2FA, node agent, CORS, rate limit, аудит.

Минимум для production (задаётся мастером при `APP_ENV=production`):

```env
APP_ENV=production
SECRET_KEY=<автогенерация в install.sh>
BEHIND_NGINX=true
ENFORCE_HTTPS=true
CORS_ORIGINS=https://ваш-домен
```
