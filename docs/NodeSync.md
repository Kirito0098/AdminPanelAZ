# Node Sync / HA (AntiZapret failover)

## Сценарий

Один домен (`vpn.example.com`), два A-записи (primary IP + replica IP). Клиент переключается между IP только если PKI (`/etc/openvpn/easyrsa3`), WireGuard peers и клиенты совпадают на обоих серверах.

## MVP (этап 5.1–5.3)

- **Sync Group** — primary + 1+ replica, shared domain
- **Push full** — `client.sh 8` на primary → transfer → restore на replica (как `setup.sh`)
- **Verify** — списки OVPN/WG клиентов + checksums PKI/WG/config

## API

| Method | Route |
|--------|-------|
| GET/POST | `/api/nodes/sync-groups` |
| GET/PUT/DELETE | `/api/nodes/sync-groups/{id}` |
| POST | `/api/nodes/sync-groups/{id}/push-full` |
| POST | `/api/nodes/sync-groups/{id}/verify` |
| GET | `/api/nodes/sync-groups/{id}/status` |

Node agent: `POST /backups/antizapret/restore`, `GET /backups/antizapret/download`, `GET /backups/antizapret/fingerprints`.

## Ограничения

- DNS панель не настраивает — второй IP добавляется у регистратора вручную **после Verify ready=true**
- Оба сервера должны быть установлены одинаковым `setup.sh`
- Push full **destructive** на replica
- Split-brain: изменения только на primary до auto-sync (v2); при failed push — `sync_status=failed`, повторить Push full

## v2 (этап 5.4–5.6)

- **Auto-sync** — `sync_mode=auto`: create/delete на primary реплицирует клиента на все replica; linked `VpnConfig` (`ha_primary_config_id`)
- **Reconcile worker** — каждые 10 мин verify всех групп; при drift → `sync_status=failed` + admin notify
- **Dashboard HA badge** — одна карточка клиента (logical primary), badge «HA: domain (N узл.)»; список configs при активном узле в группе показывает primary

Настройки: `NODE_SYNC_RECONCILE_ENABLED`, `NODE_SYNC_RECONCILE_INTERVAL_SECONDS` (default 600).
