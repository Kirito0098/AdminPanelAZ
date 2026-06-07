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

## Запуск

### Установка (первый раз)

Единый интерактивный установщик — задаёт все вопросы (тип установки, порты, Nginx/HTTPS, firewall, администратор, node agent, Telegram и др.). **По умолчанию рекомендуется публикация только через Nginx**: backend на `127.0.0.1`, наружу — HTTPS.

```bash
cd /opt/AdminPanelAZ
sudo ./install.sh
```

Опции без мастера (CI/автоматизация): `sudo ./install.sh --non-interactive --with-systemd`, см. `./install.sh --help`.

### Запуск

- Dev (foreground): `./start.sh`
- Prod (daemon): `./start.sh daemon`
- Остановка / статус: `./start.sh stop`, `./start.sh status`
- Systemd: выбирается в мастере `install.sh` или `sudo ./install.sh --with-systemd`

### Node agent (опционально, на VPN-сервере)

```bash
./start_node_agent.sh daemon
```

### URL после запуска

- Dev: UI http://127.0.0.1:5173, API http://127.0.0.1:8000
- Prod (daemon): http://127.0.0.1:8000/ (UI и API на одном порту)

### Публикация через Nginx (HTTPS, рекомендуется)

При установке мастер `install.sh` по умолчанию предлагает **Nginx + HTTPS** (Let's Encrypt или самоподписанный). Backend слушает только `127.0.0.1`; наружу — выбранные порты HTTPS/HTTP (по умолчанию 443/80). Опционально настраивается firewall (ufw/iptables).

Для смены режима после установки — утилита (не отдельный установщик):

```bash
sudo ./scripts/nginx-setup.sh
```

Неинтерактивно (Let's Encrypt): `sudo DOMAIN=panel.example.com EMAIL=admin@example.com ./scripts/nginx-setup.sh --nginx-le`

Шаблоны: `deploy/nginx/`. Nginx проксирует React SPA, API, WebSocket и Telegram Mini App на uvicorn.

### Вход по умолчанию

- `admin` / `admin` (смените при первом входе)

### Безопасность (доступ из сети)

Перед публикацией в интернет/LAN: [`SECURITY.md`](SECURITY.md) — production-секреты, HTTPS, node agent, CORS, rate limit (в т.ч. Redis при нескольких workers), аудит.

Минимум для production в `backend/.env`:

```env
APP_ENV=production
SECRET_KEY=<openssl rand -hex 32>
DEFAULT_ADMIN_PASSWORD=<надёжный пароль>
BEHIND_NGINX=true
ENFORCE_HTTPS=true
CORS_ORIGINS=https://ваш-домен
```
