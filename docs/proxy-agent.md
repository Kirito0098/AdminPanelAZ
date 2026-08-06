# Установка proxy_agent (прокси-узел)

Агент панели на **RU VPS** слушает порт **9101** (health / статус / DESTINATION / mappings). Это **не** `node_agent` VPN-узла (`:9100`).

Панель **никогда** не устанавливает и не запускает `proxy.sh`. Сначала прокси по [инструкции AntiZapret](https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер), потом агент.

Полная схема: [proxy-nodes.md](proxy-nodes.md).

## Репозиторий на RU VPS

На машине с `proxy.sh` нужна **копия** AdminPanelAZ (панель на этом хосте не ставится). Обычно каталог `/opt/AdminPanelAZ`:

```bash
sudo apt update && sudo apt install -y git
sudo git clone https://github.com/Kirito0098/AdminPanelAZ.git /opt/AdminPanelAZ
cd /opt/AdminPanelAZ
```

Если репозиторий уже есть на другой машине — можно скопировать дерево (например `rsync`/`scp`) в `/opt/AdminPanelAZ`. Для обновления агента позже: `git pull` в этом каталоге и переустановка unit при необходимости.

## Рекомендуемый способ: install.sh

```bash
cd /opt/AdminPanelAZ   # или путь к репо
sudo ./install.sh --proxy-only --with-systemd -y
```

Или интерактивно: `sudo ./install.sh` → пункт **«Только proxy_agent (RU-прокси)»**.

Установщик сам:

1. Создаст `backend/proxy_agent.env` и сгенерирует `PROXY_AGENT_API_KEY`
2. Поставит и запустит systemd-сервис `adminpanelaz-proxy`
3. Покажет ключ и порт — их нужно указать в панели (**Узлы → тип Прокси**)

Откройте порт **9101** только с IP панели (firewall хостера / `ufw`). Мастер установки при выборе firewall может предложить правило для proxy_agent. Модуль **Прокси-узлы** в панели по умолчанию выключен — включите в **Настройки → Модули**.

DESTINATION меняется через iptables (nat), без повторного запуска `proxy.sh`.

## Ручная установка (если нужно)

1. Ключ: `openssl rand -hex 32`
2. `backend/proxy_agent.env` из `backend/proxy_agent.env.example`
3. `sudo PROXY_AGENT_API_KEY='…' ./scripts/install-proxy-systemd.sh && sudo systemctl start adminpanelaz-proxy`

## Параметры `proxy_agent.env`

Файл создаёт установщик; образец — `backend/proxy_agent.env.example`. Основные переменные:

| Переменная | Смысл |
|------------|--------|
| `PROXY_AGENT_API_KEY` | Ключ для панели (`X-Node-Key`); минимум 24 символа |
| `PROXY_AGENT_HOST` / `PROXY_AGENT_PORT` | Слушать адрес и порт (по умолчанию `0.0.0.0` / **9101**) |
| `PROXY_AGENT_ALLOWED_IPS` | Опционально: список CIDR/IP, с которых принимать запросы (например IP панели `203.0.113.10/32`). Пусто — без доп. фильтра по IP (остаётся ключ / mTLS) |
| `PROXY_AGENT_STATE_DIR` | Каталог состояния агента |
| `PROXY_AGENT_MODE` | Обычно `prod` |

После правок env: `sudo systemctl restart adminpanelaz-proxy`.

## mTLS (опционально)

В `proxy_agent.env`:

```env
PROXY_AGENT_MTLS_ENABLED=true
PROXY_AGENT_MTLS_SERVER_CERT=/etc/adminpanelaz/mtls/agent.crt
PROXY_AGENT_MTLS_SERVER_KEY=/etc/adminpanelaz/mtls/agent.key
PROXY_AGENT_MTLS_CA_CERT=/etc/adminpanelaz/mtls/ca.crt
```

Сертификаты — как для VPN node agent (`scripts/generate-mtls-certs.sh`). Затем: `sudo systemctl restart adminpanelaz-proxy`.

## Полезные команды

```bash
journalctl -u adminpanelaz-proxy -f
sudo systemctl restart adminpanelaz-proxy
sudo systemctl status adminpanelaz-proxy
```

[← Прокси (полная схема)](proxy-nodes.md) · [Узлы](uzly.md) · [Все руководства](README.md)
