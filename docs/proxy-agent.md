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

Если репозиторий уже есть на другой машине — можно скопировать дерево (например `rsync`/`scp`) в `/opt/AdminPanelAZ`. Как обновлять агент потом — [Обновление агента](#обновление-агента).

## Рекомендуемый способ: install.sh

```bash
cd /opt/AdminPanelAZ   # или путь к репо
sudo ./install.sh --proxy-only --with-systemd -y
```

Или интерактивно: `sudo ./install.sh` → пункт **«Только proxy_agent (RU-прокси)»**.

Установщик сам:

1. Создаст `backend/proxy_agent.env` (права `600`) и сгенерирует `PROXY_AGENT_API_KEY`
2. Поставит и запустит systemd-сервис `adminpanelaz-proxy`
3. Покажет ключ и порт — их нужно указать в панели (**Узлы → тип Прокси**)

Ключ хранится только в `backend/proxy_agent.env`, в unit-файле systemd его нет (подробнее — [uzly.md](uzly.md#api-ключ-агента-где-хранится-и-как-сменить)). Повторная установка сохраняет существующий ключ и mTLS: мастер спрашивает «На сервере уже есть PROXY_AGENT_API_KEY — оставить его…?».

Откройте порт **9101** только с IP панели (firewall хостера / `ufw`). Мастер установки при выборе firewall может предложить правило для proxy_agent. Модуль **Прокси-узлы** в панели по умолчанию выключен — включите в **Настройки → Разделы панели**.

DESTINATION меняется через iptables (nat), без повторного запуска `proxy.sh`.

## Ручная установка (если нужно)

1. Ключ: `openssl rand -hex 32`
2. `backend/proxy_agent.env` из `backend/proxy_agent.env.example`
3. `sudo PROXY_AGENT_API_KEY='…' ./scripts/install-proxy-systemd.sh && sudo systemctl start adminpanelaz-proxy`

Скрипт записывает переданный ключ в `proxy_agent.env` и выставляет файлу права `600`, но только если там ещё нет ключа или стоит заглушка `change-me…`. Уже заданный ключ не перезаписывается — меняйте его в файле ([Смена API-ключа](#смена-api-ключа)).

## Параметры `proxy_agent.env`

Файл создаёт установщик; образец — `backend/proxy_agent.env.example`. Основные переменные:

| Переменная | Смысл |
|------------|--------|
| `PROXY_AGENT_API_KEY` | Ключ для панели (`X-Node-Key`); минимум 24 символа. Хранится только здесь |
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

## Смена API-ключа

Для прокси-узлов ключ меняется только вручную: кнопки **Ключ** у прокси-узла нет, панель отклоняет ротацию его ключа, автоматическая ротация (`NODE_API_KEY_ROTATION_DAYS`) прокси-узлы не затрагивает.

1. Новый ключ: `openssl rand -hex 32` (минимум 24 символа).
2. На RU VPS замените значение `PROXY_AGENT_API_KEY=` в `backend/proxy_agent.env`.
3. `sudo systemctl restart adminpanelaz-proxy` — с этого момента агент принимает только новый ключ.
4. В панели: **Узлы** → карточка прокси-узла → **Изменить** → поле **API-ключ** → новый ключ → **Сохранить**, затем **Здоровье**.

**После обновления до 2.26.0 смените ключ** — до этого ключ лежал в unit-файле `/etc/systemd/system/adminpanelaz-proxy.service`, который может прочитать любой пользователь сервера.

## Обновление агента

Кнопки **Обновить** у прокси-узла в панели нет — агент обновляется на RU VPS:

```bash
cd /opt/AdminPanelAZ
sudo git pull
sudo systemctl restart adminpanelaz-proxy
```

При старте агент переписывает устаревший unit `adminpanelaz-proxy` из шаблона репозитория и переносит ключ из unit'а в `proxy_agent.env`, если там его ещё нет. Сделать это вручную можно командой `sudo ./scripts/refresh-systemd-units.sh`. После обновления до 2.26.0 [смените ключ](#смена-api-ключа).

## Полезные команды

```bash
journalctl -u adminpanelaz-proxy -f
sudo systemctl restart adminpanelaz-proxy
sudo systemctl status adminpanelaz-proxy
```

[← Прокси (полная схема)](proxy-nodes.md) · [Узлы](uzly.md) · [Все руководства](README.md)
