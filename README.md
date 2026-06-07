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

```bash
cd /opt/AdminPanelAZ
sudo ./install.sh
```

### Запуск

- Dev (foreground): `./start.sh`
- Prod (daemon): `./start.sh daemon`
- Остановка / статус: `./start.sh stop`, `./start.sh status`
- Systemd: `sudo ./scripts/install-systemd.sh`, затем `systemctl start adminpanelaz`

### Node agent (опционально, на VPN-сервере)

```bash
./start_node_agent.sh daemon
```

### URL после запуска

- Dev: UI http://127.0.0.1:5173, API http://127.0.0.1:8000
- Prod (daemon): http://127.0.0.1:8000/

### Вход по умолчанию

- `admin` / `admin` (смените при первом входе)
