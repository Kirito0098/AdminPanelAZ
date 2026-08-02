# Установка proxy_agent (прокси-узел)

Агент панели на **RU VPS** слушает порт **9101** (health / статус / DESTINATION / mappings). Это **не** `node_agent` VPN-узла (`:9100`).

Панель **никогда** не устанавливает и не запускает `proxy.sh`. Сначала прокси по [инструкции AntiZapret](https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер), потом агент.

Полная схема: [proxy-nodes.md](proxy-nodes.md).

## Рекомендуемый способ: install.sh

На RU-хосте (нужен root и копия репозитория, обычно `/opt/AdminPanelAZ`):

```bash
cd /opt/AdminPanelAZ   # или путь к репо
sudo ./install.sh --proxy-only --with-systemd -y
```

Или интерактивно: `sudo ./install.sh` → пункт **«Только proxy_agent (RU-прокси)»**.

Установщик сам:

1. Создаст `backend/proxy_agent.env` и сгенерирует `PROXY_AGENT_API_KEY`
2. Поставит и запустит systemd-сервис `adminpanelaz-proxy`
3. Покажет ключ и порт — их нужно указать в панели (**Узлы → тип Прокси**)

Откройте порт **9101** с IP панели (firewall). Модуль **Прокси-узлы** в панели по умолчанию выключен — включите в **Настройки → Модули**.

DESTINATION меняется через iptables (nat), без повторного запуска `proxy.sh`.

## Ручная установка (если нужно)

1. Ключ: `openssl rand -hex 32`
2. `backend/proxy_agent.env` из `backend/proxy_agent.env.example`
3. `sudo PROXY_AGENT_API_KEY='…' ./scripts/install-proxy-systemd.sh && sudo systemctl start adminpanelaz-proxy`

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
