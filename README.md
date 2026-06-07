# AdminPanel AntiZapret

Веб-панель администрирования для VPN-сервера [AntiZapret](https://github.com/GubernievS/AntiZapret-VPN).

Стек: **FastAPI** (backend) + **React/Vite** (frontend).

## Возможности

- Авторизация с ролями (администратор / пользователь), JWT
- CRUD VPN-клиентов через `/root/antizapret/client.sh`
- Скачивание профилей подключения (`.ovpn`, `.conf`)
- Мониторинг: статус служб, OpenVPN-логи, WireGuard (`wg show`)
- Настройки: тема, списки доменов/IP AntiZapret, управление пользователями
- Светлая / тёмная тема с сохранением

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
# Статика в frontend/dist — раздавайте через nginx или FastAPI StaticFiles
```

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
| OpenVPN-подключения | `/etc/openvpn/server/logs/*-status.log` |
| WireGuard-подключения | `wg show all dump` |
| Статус служб | `systemctl is-active` |

## Роли

| Роль | Доступ |
|------|--------|
| **admin** | Все конфигурации, пользователи, списки AntiZapret, синхронизация |
| **user** | Только свои конфигурации, мониторинг, смена пароля и темы |

## Структура проекта

```
/opt/AdminPanelAZ/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── models.py
│   │   ├── routers/
│   │   └── services/antizapret.py
│   └── requirements.txt
├── frontend/
│   └── src/
├── start.sh
└── README.md
```

## Переменные окружения

Скопируйте `backend/.env.example` в `backend/.env`:

```env
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///./data/adminpanel.db
ANTIZAPRET_PATH=/root/antizapret
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## Ограничения

- Backend должен запускаться с правами, достаточными для `client.sh` (обычно root)
- Изменение списков AntiZapret запускает `doall.sh` (может занять несколько минут)
- WireGuard-пиры без handshake отображаются как неактивные
- TCP-службы OpenVPN/WireGuard могут быть не установлены — отображаются как inactive
