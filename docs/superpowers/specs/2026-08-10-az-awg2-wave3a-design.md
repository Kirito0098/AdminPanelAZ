# AZ-AWG2 — волна 3a (install SSE, TTL, узкий backup)

**Дата:** 2026-08-10  
**Статус:** draft  
**Эпик:** [wave3](2026-08-10-az-awg2-wave3.md)  
**Зависит от:** волны 1–2

## Цель

Дать админу установку/обновление слоя из панели (SSE), временные клиенты с TTL и безопасный backup/restore **только** состояния AWG2.

## В scope

- SSE stream: `install.sh` (layer) и `install.sh --update` на active node (паттерн Warper `/warper/updates/stream`)
- Диалог перед install: preset/template (non-interactive flags), `--no-bot` по умолчанию
- Явный запрет / отсутствие UI для `--install-base` и reboot orchestration; warning в copy
- Create `amneziawg2` с optional TTL; `VpnConfig.expires_at`; sync с `expiry.tsv`
- Expire job: удалить peers/files + DB row; HA копирует `expiry.tsv`
- Узкий backup/restore API + вкладка «Бэкап» на `/awg2`
- После restore на primary — HA sync state на replicas (волна 2 machinery)

## Не цели

- Полный `awg-backup.sh` upstream (OVPN, lists, knot, stock clients)
- TG / Mini App (3b)
- Peer block / deep stats (3c)

## Remote install / update

### API

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/awg2/install/stream?token=&mode=install\|update&preset=&template=&mtu=` | SSE лог |

События SSE: `{event: start|log|error|done, ...}` как у Warper.

### Поведение

- `mode=install`: curl `install.sh` с non-interactive obfuscation flags; **не** `--install-base`
- `mode=update`: `install.sh --update`
- Если AntiZapret base отсутствует — stream error + SSH hint для base install
- Node-agent endpoints для remote nodes
- Concurrent streams: один install/update lock на узел

### UI

- На install-prompt: кнопка «Установить из панели» + по-прежнему SSH command
- На справке/hero: «Обновить слой» со стримом
- Warning: «перезагрузка / install-base только по SSH»

## TTL

### Модель

- Колонка `vpn_configs.expires_at` (`DateTime`, nullable) — для всех типов допустима, используется для `amneziawg2`
- Create body: optional `ttl` string (`30m`, `2h`, `6h`, `7d`, …) → `awg-client add … --ttl` + compute `expires_at`
- Upstream truth: `/opt/antizapret-awg/expiry.tsv`; панель периодически reconcile

### Job

- Interval ~60s (или существующий background tick): `awg-client expire-check` **или** parse expiry.tsv → для истёкших вызвать delete path (CLI + DB)
- Не оставлять orphan `VpnConfig`

### HA

- Wave 2 archive includes `expiry.tsv`
- Shadow configs копируют `expires_at` metadata

### UI

- Create dialog: TTL select (нет / 30m / 2h / 6h / 7d)
- Badge «истекает …» на `/awg2` и Dashboard

## Узкий backup / restore

### Содержимое tar

```
amneziawg/     # /etc/amnezia/amneziawg (conf, obfuscation.*, services.env, keys)
clients/       # /opt/antizapret-awg/clients
awgstate/      # expiry.tsv only (optional stats.db — NO, node-local metrics)
MANIFEST
```

Не включать: OpenVPN PKI, `/root/antizapret/config`, knot, stock `client/`, venv, `stats.db`.

### API

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/api/awg2/backup` | создать tar, вернуть download |
| POST | `/api/awg2/restore` | multipart tar → replace trees → `apply_awg2_runtime` → HA sync |

### UI

- Вкладка **Бэкап**: скачать / загрузить; warning «не замена полного awg-backup / бэкапов панели»

## Тесты

- SSE install builds argv without `--install-base`
- TTL parse + `expires_at`; expire job deletes DB+CLI mock
- Backup tar membership excludes OVPN paths
- Restore then `apply_awg2_runtime` called; HA sync mocked
- Lock prevents concurrent install streams

## Критерии готовности 3a

1. Admin может установить/обновить слой со стримом логов на active node.  
2. `--install-base` недоступен из UI.  
3. TTL-клиент создаётся, отображается, автоудаляется.  
4. Узкий backup/restore восстанавливает AWG2 clients+обфускацию без OVPN.  
5. Тесты зелёные; волны 1–2 без регрессий.
