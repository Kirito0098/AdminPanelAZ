# AdminPanel AntiZapret

Веб-панель администрирования для VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN).

Стек: **FastAPI** (backend) + **React/Vite/TypeScript** (frontend: Tailwind CSS, shadcn/ui, Recharts).

## Архитектура Controller + Nodes

**Controller** — эта панель администрирования (центральное управление).  
**Nodes** — VPN-серверы с AntiZapret, которыми управляет controller.

| Компонент | Роль |
|-----------|------|
| Admin Panel (backend + frontend) | Controller: CRUD узлов, выбор активного узла, проксирование операций |
| Локальный узел (`is_local=true`) | Прямой доступ к `/root/antizapret` через shell/файлы |
| Node Agent (`node_agent/`) | Лёгкий FastAPI-агент на удалённом сервере; аутентификация `X-Node-Key` |
| `LocalNodeAdapter` | Выполняет команды локально |
| `RemoteNodeAdapter` | HTTP-вызовы к node agent |

При старте controller автоматически регистрирует локальный узел «Локальный сервер», если его ещё нет. Все страницы (конфигурации, мониторинг, настройки) работают через **активный узел**.

### API узлов (только admin)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/nodes` | Список узлов |
| POST | `/api/nodes` | Добавить удалённый узел |
| GET | `/api/nodes/active` | Текущий активный узел |
| GET | `/api/nodes/{id}` | Детали узла |
| PUT | `/api/nodes/{id}` | Обновить узел |
| DELETE | `/api/nodes/{id}` | Удалить узел |
| POST | `/api/nodes/{id}/health` | Проверка доступности |
| POST | `/api/nodes/{id}/activate` | Сделать узел активным |

### Добавление удалённого узла

1. На VPN-сервере установите AntiZapret и скопируйте репозиторий панели (или только `backend/`).
2. Задайте API-ключ и запустите агент:

```bash
export NODE_AGENT_API_KEY="your-secure-random-key"
export ANTIZAPRET_PATH=/root/antizapret
./start_node_agent.sh              # foreground dev (uvicorn --reload)
./start_node_agent.sh daemon       # prod daemon с watchdog (рекомендуется)
```

3. В панели: **Узлы → Добавить узел** — укажите имя, хост, порт (по умолчанию 9100) и тот же API-ключ.
4. Нажмите «Проверка здоровья», затем «Активировать» для переключения операций на этот сервер.

API-ключи хранятся в БД в виде bcrypt-хеша и Fernet-шифрования (для исходящих запросов). Заголовок: `X-Node-Key`.

Переменная `ALLOW_INTERNAL_NODES=true` разрешает добавление узлов с приватными IP (по умолчанию запрещено из соображений SSRF).

## Возможности

### Ядро (портировано ранее)
- Авторизация JWT, роли admin / user / **viewer**
- Controller + Nodes: локальный узел и удалённые через node agent
- CRUD VPN-клиентов через `client.sh`
- Скачивание профилей (`.ovpn`, `.conf`), QR-коды
- KPI на главной, NOC-мониторинг, мониторинг трафика (SQLite + Recharts)
- CIDR: 12 провайдеров, 6 пресетов, sync → `AP-*-include-ips.txt`
- Списки AntiZapret (5 базовых файлов в Настройках)
- Обслуживание: `doall.sh`, `client.sh 7`, перезапуск VPN-служб
- Бэкапы, Telegram-уведомления, принудительная смена пароля, темы

### Портировано в этом проходе (паритет с AdminAntizapret)
| Функция | Статус |
|---------|--------|
| **Редактор файлов** (10 файлов: hosts, ips, adblock, forward, drop) | ✅ `/edit-files` |
| **Политики клиентов** (блок/разблок OpenVPN + WG, срок WG) | ✅ `/api/client-access` |
| **Роль viewer** + scoped config access | ✅ API `/api/system/viewer-access` |
| **CIDR DB pipeline** (internet download, antifilter, generate) | ✅ `/routing` + `/api/routing/cidr-db/*` |
| **Игровые фильтры** (15 игр, домены → include-hosts) | ✅ вкладка «Игры» в Routing |
| **Журналы** (подключения + audit log) | ✅ `/logs` |
| **IP whitelist / безопасность** | ✅ Настройки → Безопасность |
| **Авто-бэкап по расписанию** | ✅ фоновый worker (hourly check) |
| **Мониторинг сервера** (CPU/RAM/диск) | ✅ `/server-monitor` + WebSocket |
| **Telegram Mini App** (базовый) | ✅ `/api/tg-mini` |
| **Системные обновления** (git pull) | ✅ `/api/system/updates` |
| **Скачивание бэкапов** | ✅ кнопка в UI |
| **OpenVPN management socket** (status 3, log tail) | ✅ `/api/logs/openvpn-events`, fallback `*-status.log` |

### Не портировано (ограничения)
| Функция | Причина |
|---------|---------|
| vnStat bandwidth charts (полные) | vnstat опционален; базовые метрики через psutil |
| IP scanner iptables firewall | Требует root + iptables на controller |
| Captcha / Telegram Login Widget | Flask-session специфика |
| In-panel pytest runner | Низкий приоритет |
| IP-blocked dwell page | Отдельный Flask blueprint |
| OpenVPN client-kill через management | Не реализовано (только чтение) |
| Полный tg_mini UI (все вкладки) | Портирован core API + минимальная HTML-страница |

## Учётные данные по умолчанию

| Логин | Пароль |
|-------|--------|
| `admin` | `admin` |

**Смените пароль при первом входе** (Настройки → Смена пароля) или через переменные окружения:

```env
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=your-secure-password
```

## Требования

- Python 3.11+
- Node.js 18+
- Установленный AntiZapret в `/root/antizapret`
- Права на выполнение `client.sh`, `doall.sh`, `systemctl`, `wg`

## Установка на новый сервер

Автоматическая установка на **Ubuntu 24.04** / **Debian 13+** (без Docker).

### Интерактивный мастер (по умолчанию)

При запуске в терминале (`sudo ./install.sh`) открывается пошаговый мастер на русском языке:

1. **Тип установки** — controller / controller+node / node-only  
2. **AntiZapret** — путь к каталогу (`ANTIZAPRET_PATH`)  
3. **Сеть** — `BACKEND_HOST`, `BACKEND_PORT`, CORS, `ALLOW_INTERNAL_NODES`  
4. **Администратор** — `DEFAULT_ADMIN_*`, принудительная смена пароля  
5. **Node agent** — порт, `NODE_AGENT_API_KEY` → `backend/node_agent.env`  
6. **Автозапуск** — manual / daemon / systemd  
7. **Опции** — CIDR refresh, traffic sync, Telegram, auto-backup  
8. **Пути** — state dir, `BACKUP_ROOT`  

Enter принимает значение в `[скобках]`. Перед применением показывается сводка: **«Применить конфигурацию? [y/N]»**.

```bash
cd /opt/AdminPanelAZ
sudo ./install.sh              # интерактивный мастер
sudo ./install.sh -y           # все значения по умолчанию, без вопросов
sudo ./install.sh --non-interactive --with-systemd   # CI / скрипты, только флаги
```

### Флаги (неинтерактивный режим)

```bash
# С автозапуском через systemd (рекомендуется для production)
sudo ./install.sh --non-interactive --with-systemd

# Полная установка: controller + node agent на одной машине
sudo ./install.sh --non-interactive --with-systemd --with-node-agent

# Prod daemon без systemd (watchdog через start.sh)
sudo ./install.sh --non-interactive --with-daemon

# Клонирование из git при первом запуске
sudo INSTALL_FROM_GIT=https://github.com/your-org/AdminPanelAZ.git \
  INSTALL_TARGET=/opt/AdminPanelAZ ./install.sh --non-interactive --with-systemd
```

Скрипт `install.sh`:

| Этап | Действие |
|------|----------|
| Pre-checks | root/sudo, версия ОС, мастер или флаги |
| Зависимости | python3, venv, pip, nodejs 18+, npm, git, curl, build-essential |
| Backend | venv + `pip install -r requirements.txt` |
| Frontend | `npm install` + `npm run build` (пропуск в режиме node-only) |
| Конфиг | `backend/.env`, `backend/node_agent.env`, генерация секретов |
| Опции | `--with-daemon`, `--with-systemd`, `--with-node-agent` |

Флаги:

| Флаг | Описание |
|------|----------|
| *(без флагов, TTY)* | Интерактивный мастер установки |
| `-y`, `--yes` | Принять значения по умолчанию в мастере |
| `--non-interactive` | Без мастера: только флаги и переменные окружения |
| `--with-daemon` | Запустить prod daemon (`./start.sh daemon`) после установки |
| `--with-systemd` | Установить unit `adminpanelaz` (`scripts/install-systemd.sh`) |
| `--with-node-agent` | Настроить node agent (+ `install-node-systemd.sh` с `--with-systemd`) |
| `--force` | Перезаписать существующий `backend/.env` |

Файлы конфигурации после мастера:

| Файл | Назначение |
|------|------------|
| `backend/.env` | Controller: секреты, CORS, admin, опции |
| `backend/node_agent.env` | Node agent (gitignore), подключается systemd |
| `/etc/systemd/system/adminpanelaz*.service` | `EnvironmentFile` на env-файлы проекта |

Повторный запуск безопасен (идемпотентен): существующий `backend/.env` не перезаписывается без `--force` (мастер использует `--force` при подтверждении).

Удаление (остановка сервисов, снятие systemd units):

```bash
sudo ./scripts/uninstall.sh
sudo ./scripts/uninstall.sh --purge-state   # + удалить .runtime и /var/lib/adminpanelaz*
```

**Права root:** backend и node agent требуют root для `client.sh`, `doall.sh`, `wg`, `systemctl` (см. раздел «Ограничения»).

## Быстрый старт

Запуск backend и frontend одной командой:

```bash
cd /opt/AdminPanelAZ
./start.sh
```

Скрипт создаёт `backend/.venv` при необходимости, устанавливает зависимости (`pip`, `npm`) и запускает оба сервиса. Остановка: `Ctrl+C` или `./start.sh stop`.

Переменные окружения (опционально): `BACKEND_HOST`, `BACKEND_PORT`, `FRONTEND_HOST`, `FRONTEND_PORT`. Настройки backend — в `backend/.env` (см. `backend/.env.example`).

После запуска:

- API: http://127.0.0.1:8000
- Документация: http://127.0.0.1:8000/docs
- UI: http://127.0.0.1:5173

### Daemon / production (автоперезапуск)

Для сервера используйте detached-режим с watchdog, который перезапускает упавшие процессы.

| Команда | Описание |
|---------|----------|
| `./start.sh` или `./start.sh start` | **Dev, foreground** — uvicorn `--reload` + Vite dev; `Ctrl+C` для остановки |
| `./start.sh daemon` | **Prod daemon** — detached watchdog, frontend из `frontend/dist` через backend |
| `./start.sh daemon dev` | **Dev daemon** — detached watchdog, Vite dev server (для отладки на сервере) |
| `./start.sh stop` | Graceful stop watchdog + backend + frontend |
| `./start.sh status` | Статус процессов, режим, пути к логам |
| `./start.sh restart` | Перезапуск daemon (сохраняет последний режим dev/prod) |

**Каталог состояния:** по умолчанию `/opt/AdminPanelAZ/.runtime/` (скрытый, вне видимого корня). Переопределение: `ADMINPANELAZ_STATE_DIR` (для systemd: `/var/lib/adminpanelaz`).

**Логи:** `$ADMINPANELAZ_STATE_DIR/logs/` (по умолчанию `.runtime/logs/`)

| Файл | Содержимое |
|------|------------|
| `watchdog.log` | События watchdog (рестарты, остановка) |
| `backend.log` | stdout/stderr uvicorn |
| `frontend.log` | stdout/stderr Vite (только dev daemon) |
| `frontend-build.log` | `npm run build` (prod daemon) |

**PID-файлы:** `$ADMINPANELAZ_STATE_DIR/run/` (`watchdog.pid`, `backend.pid`, `frontend.pid`, `mode`)

**Prod vs dev:**

- **dev** — hot-reload backend, Vite на порту 5173 (как при локальной разработке).
- **prod** — `npm run build`, статика из `frontend/dist` раздаётся через FastAPI (`SERVE_FRONTEND=true`). Один процесс uvicorn на порту 8000; UI: http://127.0.0.1:8000/

Переменные:
- `ADMINPANELAZ_MODE=dev|prod` — режим для `daemon` / `watchdog`
- `ADMINPANELAZ_STATE_DIR` — каталог логов и PID (по умолчанию `.runtime/` в корне проекта)

### Node Agent daemon (на VPN-сервере)

| Команда | Описание |
|---------|----------|
| `./start_node_agent.sh` | **Dev, foreground** — uvicorn `--reload`; `Ctrl+C` для остановки |
| `./start_node_agent.sh daemon` | **Prod daemon** — detached watchdog, uvicorn без reload |
| `./start_node_agent.sh daemon dev` | Dev daemon с `--reload` |
| `./start_node_agent.sh stop` | Остановка watchdog + agent |
| `./start_node_agent.sh status` | Статус процессов и пути к логам |
| `./start_node_agent.sh restart` | Перезапуск daemon |

**Каталог состояния node agent:** по умолчанию `.runtime/node/`. Переопределение: `NODE_AGENT_STATE_DIR` (для systemd: `/var/lib/adminpanelaz-node`).

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `NODE_AGENT_API_KEY` | `change-me-node-agent-key` | Ключ `X-Node-Key` |
| `ANTIZAPRET_PATH` | `/root/antizapret` | Путь к AntiZapret |
| `NODE_AGENT_PORT` | `9100` | Порт агента |
| `NODE_AGENT_STATE_DIR` | `.runtime/node` | Логи и PID |

**Логи node agent:** `$NODE_AGENT_STATE_DIR/logs/` (`agent.log`, `watchdog.log`)

### systemd (рекомендуется для production)

**Controller (панель):**

```bash
sudo ./scripts/install-systemd.sh
sudo systemctl start adminpanelaz
sudo systemctl status adminpanelaz
```

**Node agent (на VPN-сервере):**

```bash
# Задайте NODE_AGENT_API_KEY в systemd/adminpanelaz-node.service или после установки в /etc/systemd/system/
sudo ./scripts/install-node-systemd.sh
sudo systemctl start adminpanelaz-node
sudo systemctl status adminpanelaz-node
```

Установщики копируют unit-файлы в `/etc/systemd/system/`, подставляют путь к проекту, создают каталоги состояния и включают автозапуск.

| Сервис | State dir (systemd) | Журнал |
|--------|---------------------|--------|
| `adminpanelaz` | `/var/lib/adminpanelaz` | `journalctl -u adminpanelaz -f` |
| `adminpanelaz-node` | `/var/lib/adminpanelaz-node` | `journalctl -u adminpanelaz-node -f` |

- **Файловые логи controller:** `/var/lib/adminpanelaz/logs/` (или `.runtime/logs/` без systemd)
- **Файловые логи node agent:** `/var/lib/adminpanelaz-node/logs/` (или `.runtime/node/logs/`)
- **Остановка:** `systemctl stop …` или `./start.sh stop` / `./start_node_agent.sh stop`

Другой пользователь: `sudo INSTALL_USER=adminpanel ./scripts/install-systemd.sh`

### Ручной запуск (альтернатива)

#### Backend

```bash
cd /opt/AdminPanelAZ/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API: http://127.0.0.1:8000  
Документация: http://127.0.0.1:8000/docs

#### Frontend

```bash
cd /opt/AdminPanelAZ/frontend
npm install
npm run dev
```

UI: http://127.0.0.1:5173

### Production-сборка frontend

```bash
cd /opt/AdminPanelAZ/frontend
npm run build
# Статика в frontend/dist
```

В daemon prod (`./start.sh daemon`) сборка выполняется автоматически; backend раздаёт `dist/` при `SERVE_FRONTEND=true`. Альтернатива — nginx перед uvicorn.

## Интеграция с AntiZapret

| Действие | Команда / источник |
|----------|-------------------|
| Создать OpenVPN-клиент | `client.sh 1 <имя> <дни>` |
| Удалить OpenVPN-клиент | `client.sh 2 <имя>` |
| Создать WireGuard-клиент | `client.sh 4 <имя>` |
| Удалить WireGuard-клиент | `client.sh 5 <имя>` |
| Файлы профилей | `/root/antizapret/client/` |
| Списки доменов/IP | `/root/antizapret/config/*.txt` |
| Применить списки | `doall.sh` |
| OpenVPN-подключения | Unix-сокеты `/run/openvpn-server/*.sock` (`status 3`), fallback `*-status.log` |
| WireGuard-подключения | `wg show all dump` |
| Статус служб | `systemctl is-active` |

### OpenVPN management interface

Для live-трафика и событий подключений OpenVPN должен быть настроен management interface (Unix socket). AntiZapret создаёт сокеты в `/run/openvpn-server/`:

| Профиль | Сокет | Status-лог (fallback) |
|---------|-------|------------------------|
| `antizapret-udp` | `antizapret-udp.sock` | `antizapret-udp-status.log` |
| `antizapret-tcp` | `antizapret-tcp.sock` | `antizapret-tcp-status.log` |
| `vpn-udp` | `vpn-udp.sock` | `vpn-udp-status.log` |
| `vpn-tcp` | `vpn-tcp.sock` | `vpn-tcp-status.log` |

Панель отправляет команды `status 3` (CLIENT_LIST + байты) и `log N` (хвост событий). Если сокет недоступен, используется парсинг `*-status.log` из `/etc/openvpn/server/logs/`. Переменные — `OPENVPN_SOCKET_DIR`, `OPENVPN_LOG_TAIL_LINES` в `backend/.env`.

## Роли

| Роль | Доступ |
|------|--------|
| **admin** | Полный доступ: узлы, политики клиентов, редактор файлов, бэкапы, безопасность, CIDR |
| **user** | Свои конфигурации, мониторинг, смена пароля и темы |
| **viewer** | Только чтение: назначенные конфигурации, мониторинг, журналы (без редактирования) |

### API обслуживания и бэкапов (только admin)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/settings/run-doall` | Запуск `doall.sh` на активном узле |
| POST | `/api/settings/recreate-profiles` | Пересоздание профилей (`client.sh 7`) |
| POST | `/api/settings/restart-service` | Перезапуск VPN-службы |
| GET/PATCH | `/api/settings/telegram` | Настройки Telegram |
| POST | `/api/settings/telegram/test` | Тестовое сообщение |
| GET/POST | `/api/backups` | Список / создание бэкапов |
| POST | `/api/backups/restore` | Восстановление из архива |
| GET | `/api/monitoring/summary` | KPI для главной страницы |
| GET | `/api/configs/{id}/qr` | QR-код профиля подключения |

### API маршрутизации / CIDR

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/routing/overview` | Провайдеры, пресеты, статистика маршрутов |
| POST | `/api/routing/providers/{filename}/enabled` | Вкл/выкл провайдера (admin) |
| POST | `/api/routing/presets/{key}/apply` | Применить пресет (admin) |
| POST | `/api/routing/sync` | Синхронизация list → AP-*-include-ips.txt (admin) |
| POST | `/api/routing/apply` | sync + doall.sh (admin) |
| GET | `/api/routing/cidr-db/status` | Статус CIDR БД, провайдеры, история |
| POST | `/api/routing/cidr-db/refresh` | Загрузка провайдеров из интернета (фон) |
| POST | `/api/routing/cidr-db/generate` | Генерация `data/cidr/list/*.txt` из БД |
| GET | `/api/routing/cidr-db/antifilter/status` | Статус antifilter.download |
| POST | `/api/routing/cidr-db/antifilter/refresh` | Обновить antifilter (фон) |
| GET | `/api/routing/cidr-db/tasks/{id}` | Прогресс фоновой задачи |

### CIDR DB pipeline

Двухэтапная схема (как в AdminAntizapret):

1. **Refresh** — `CidrDbUpdaterService.refresh_all_providers()` скачивает AWS/Google/Cloudflare/RIPE и ASN-префиксы в SQLite на **контроллере** (`provider_cidr`, `provider_meta`, …).
2. **Generate** — `update_cidr_files_from_db()` пишет `backend/data/cidr/list/*.txt`, опционально с фильтром **antifilter** (пересечение с заблокированными в РФ подсетями).
3. **Sync + doall** — через активный node adapter: `sync` → `AP-*-include-ips.txt` → `doall.sh` на VPN-узле.

**UI:** вкладка «Маршрутизация / CIDR» → панель «CIDR DB Pipeline».

**Расписание:** фоновый worker (`CIDR_DB_REFRESH_HOUR` / `CIDR_DB_REFRESH_MINUTE`, по умолчанию 02:30 UTC) или cron:

```bash
30 2 * * * /opt/AdminPanelAZ/backend/.venv/bin/python /opt/AdminPanelAZ/backend/utils/cidr_db_refresh.py
```

**Данные:** baseline-файлы в `backend/data/cidr/list/_baseline/` (скопированы из AdminAntizapret). Первый generate создаёт runtime backups.

**Переменные** (`backend/.env`): `CIDR_LIST_DIR`, `CIDR_DB_REFRESH_*`, `ANTIFILTER_URL`, `OPENVPN_ROUTE_TOTAL_CIDR_LIMIT`, `CIDR_DB_*_WORKERS` (см. pipeline `constants.py`).

**Antifilter:** список `allyouneed.lst` (~15k /24). При generate с `filter_by_antifilter=true` остаются только provider CIDR, **пересекающиеся** с заблокированными — для маршрутизации трафика к заблокированным ресурсам.


| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/traffic/overview` | Сводка и таблица per-client |
| GET | `/api/traffic/chart?client=&range=` | Временной ряд для графика |
| POST | `/api/traffic/reset` | Сброс статистики (admin) |

## Структура проекта

```
/opt/AdminPanelAZ/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routers/backups.py, maintenance.py, nodes.py
│   │   └── services/
│   │       ├── antizapret.py, backup_manager.py
│   │       ├── node_adapter.py, qr_generator.py, telegram.py
│   │       └── node_manager.py
│   ├── node_agent/main.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/NodesPage.tsx
│       └── components/NodeSelector.tsx
├── start.sh
├── start_node_agent.sh
├── install.sh
├── scripts/install-wizard.sh
├── scripts/install-systemd.sh
├── scripts/install-node-systemd.sh
├── scripts/uninstall.sh
├── systemd/adminpanelaz.service
├── systemd/adminpanelaz-node.service
├── .runtime/          # логи и PID (gitignored; создаётся при запуске)
└── README.md
```

## Переменные окружения

Скопируйте `backend/.env.example` в `backend/.env`:

```env
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///./data/adminpanel.db
ANTIZAPRET_PATH=/root/antizapret
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CIDR_LIST_DIR=data/cidr/list
TRAFFIC_SYNC_ENABLED=true
TRAFFIC_SYNC_INTERVAL_SECONDS=30
TRAFFIC_DB_STALE_SECONDS=600
# OpenVPN management Unix sockets (см. /etc/openvpn/server/*.conf → management ...)
OPENVPN_SOCKET_DIR=/run/openvpn-server
OPENVPN_SOCKET_TIMEOUT=2.5
OPENVPN_SOCKET_IDLE_TIMEOUT=0.12
OPENVPN_LOG_TAIL_LINES=200
OPENVPN_EVENT_MAX_RESPONSE_BYTES=524288
```

## Новые API (порт второго прохода)

| Метод | Путь | Описание |
|-------|------|----------|
| GET/PUT | `/api/edit-files/{key}` | Редактор 10 конфиг-файлов AntiZapret |
| GET/POST | `/api/client-access/*` | Блок/разблок/срок OpenVPN и WireGuard |
| POST | `/api/configs/{id}/one-time-link` | Одноразовая ссылка на профиль |
| GET/POST | `/api/public/qr-download/{token}` | Публичное скачивание по токену |
| GET/PATCH | `/api/security` | IP whitelist, QR settings, scanner block |
| GET | `/api/server-monitor/metrics` | CPU/RAM/диск |
| WS | `/api/server-monitor/ws?token=` | Live CPU/RAM (2с) |
| GET/POST | `/api/routing/game-filters` | Игровые фильтры |
| GET | `/api/logs/actions` | Audit log |
| GET | `/api/logs/connections` | Снимок подключений (+ `openvpn_data_source`) |
| GET | `/api/logs/openvpn-events` | Хвост событий OpenVPN management (`log N`) |
| GET | `/api/logs/openvpn-sockets` | Диагностика сокетов (admin) |
| GET/POST | `/api/system/updates` | Проверка/применение git update |
| PUT | `/api/system/viewer-access` | Права viewer на конфиги |
| GET/POST | `/api/tg-mini/*` | Telegram Mini App |

## Ограничения

- Backend должен запускаться с правами root для `client.sh`, `wg set`, `doall.sh`
- CIDR DB pipeline выполняется на **контроллере**; списки применяются на активном узле через sync/doall (remote node — через agent)
- WG runtime block через `wg set peer remove` (упрощённо vs полный enforcer AdminAntizapret)
- IP firewall (iptables) для scanner block — только настройки в БД, без автоматического iptables
- Авто-бэкап: asyncio worker на controller (не system crontab)
- Трафик OpenVPN: management socket (`status 3`) с fallback на `*-status.log`; WireGuard — `wg show`
- Node agent: `/openvpn/management/events`, `/openvpn/management/sockets` для удалённых узлов
