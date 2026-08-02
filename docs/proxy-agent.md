# Установка proxy_agent (прокси-узел)

Короткая инструкция для **RU VPS**, где уже работает AntiZapret `proxy.sh`. Агент панели слушает порт **9101** и даёт health / статус / смену DESTINATION / mappings. Это **не** `node_agent` VPN-узла (`:9100`).

Панель **никогда** не устанавливает и не запускает `proxy.sh`. Сначала прокси по [инструкции AntiZapret](https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер), потом агент.

## Что нужно

- Root на RU-хосте
- Копия репозитория AdminPanelAZ на этом хосте (или хотя бы `backend/proxy_agent`, `scripts/`, `systemd/`)
- Открытый порт **9101** с IP панели (firewall)
- Модуль **Прокси-узлы** в панели (по умолчанию выключен)

## Шаги

1. Сгенерируйте ключ (минимум 24 символа):

```bash
openssl rand -hex 32
```

2. Создайте `backend/proxy_agent.env` на RU-хосте (образец: `backend/proxy_agent.env.example`):

```env
PROXY_AGENT_API_KEY=<ваш_ключ>
PROXY_AGENT_HOST=0.0.0.0
PROXY_AGENT_PORT=9101
PROXY_AGENT_MODE=prod
# PROXY_AGENT_ALLOWED_IPS=<IP_панели>/32
```

3. Установите systemd unit:

```bash
cd /opt/AdminPanelAZ   # или ваш путь к репозиторию
sudo PROXY_AGENT_API_KEY='<ваш_ключ>' ./scripts/install-proxy-systemd.sh
sudo systemctl start adminpanelaz-proxy
sudo systemctl status adminpanelaz-proxy
```

4. В панели: **Настройки → Модули** → **Прокси-узлы** → включить.  
   **Узлы** → добавить узел типа **Прокси** с тем же ключом и портом **9101** → **Проверить**.

DESTINATION меняется через iptables (nat), без повторного запуска `proxy.sh`. Подробнее для пользователей: [uzly.md](uzly.md).

## mTLS (опционально)

В `proxy_agent.env`:

```env
PROXY_AGENT_MTLS_ENABLED=true
PROXY_AGENT_MTLS_SERVER_CERT=/etc/adminpanelaz/mtls/agent.crt
PROXY_AGENT_MTLS_SERVER_KEY=/etc/adminpanelaz/mtls/agent.key
PROXY_AGENT_MTLS_CA_CERT=/etc/adminpanelaz/mtls/ca.crt
```

Сертификаты — как для VPN node agent (`scripts/generate-mtls-certs.sh`). Затем перезапуск: `sudo systemctl restart adminpanelaz-proxy`.

## Полезные команды

```bash
journalctl -u adminpanelaz-proxy -f
sudo systemctl restart adminpanelaz-proxy
```

[← Узлы](uzly.md) · [Все руководства](README.md)
