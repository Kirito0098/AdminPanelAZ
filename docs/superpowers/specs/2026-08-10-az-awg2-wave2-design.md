# AZ-AWG2 — волна 2 (сводный спек: срезы 2a–2c)

**Дата:** 2026-08-10  
**Статус:** draft — **выполнять по срезам**  
**Эпик:** [`2026-08-10-az-awg2-epic.md`](2026-08-10-az-awg2-epic.md)  
**Зависит от:** срезы 1a–1c

| Срез | Спек | План |
|------|------|------|
| **2a** HA | [wave2a](2026-08-10-az-awg2-wave2a-design.md) | [plan](../plans/2026-08-10-az-awg2-wave2a.md) |
| **2b** обфускация | [wave2b](2026-08-10-az-awg2-wave2b-design.md) | [plan](../plans/2026-08-10-az-awg2-wave2b.md) |
| **2c** мониторинг | [wave2c](2026-08-10-az-awg2-wave2c-design.md) | [plan](../plans/2026-08-10-az-awg2-wave2c.md) |

Монолитный план-справочник: [`../plans/2026-08-10-az-awg2-wave2.md`](../plans/2026-08-10-az-awg2-wave2.md)

Ниже — исходное полное описание волны 2.

---

# AZ-AWG2 — волна 2 (HA + обфускация + мониторинг) [архив текста]

**Upstream:** [blindtechnique/az-awg2](https://github.com/blindtechnique/az-awg2)

## Цель


Довести модуль AZ-AWG2 до HA-паритета со стоковым WireGuard и сделать вкладку `/awg2` операторски полезной: управление обфускацией и мониторинг peers/трафика без Telegram-бота az-awg2.

## Решения владельца

| Тема | Выбор |
|------|--------|
| Scope | HA crypto-sync + обфускация UI + мониторинг overview |
| HA глубина | Полный паритет со стоком WG: archive state + runtime apply + shadow `VpnConfig` |
| Replica без слоя | Replicate **fails** с `install_command`; remote install из панели — нет |
| Обфускация | show + regenerate + apply (preset/template/MTU/host); после apply — warning re-import + HA sync |
| Мониторинг | `awg show` summary + `awg_stats overview` (без deep client card / geo) |
| Подход | Расширить `Awg2Service` / `/api/awg2/*` + ветка в `vpn_state_sync` |
| Отмена правила волны 1 | HA skip для `amneziawg2` **снимается** |

## Не цели (волна 3+)

- TTL-клиенты, бэкап/restore слоя (`awg-backup`)
- Telegram / Mini App для AWG2
- Remote `install.sh` / `--update` stream из панели
- Peer block / client-access iptables для AWG2
- Deep `awg_stats client` UI, geo/history как в боте az-awg2
- Изменение AZ-WARP или стокового AmneziaWG

## Жёсткие правила

1. На replica слой должен быть установлен **до** успешного AWG2 replicate (админ ставит по SSH, команда из health).  
2. Crypto на replica — **byte-copy** с primary (не `awg-client add` с новыми ключами).  
3. `stats.db` — node-local, не входит в crypto archive.  
4. `obfuscation.env` / `obfuscation.meta` / server confs / clients — входят в sync.  
5. После смены обфускации клиентские профили на устройствах требуют re-import.  
6. Панель по-прежнему не запускает `install.sh` на узле.

## Архитектура HA

```
create/delete VpnConfig(amneziawg2) on primary
        │
        ▼
maybe_replicate_create / maybe_replicate_delete
        │
        ▼
sync_amneziawg2_state_from_primary(primary, replica)
  1. replica get_awg2_health → installed?
     else raise with install_command
  2. export tar.gz:
       - /etc/amnezia/amneziawg/** (configs, services.env, obfuscation.*)
       - /opt/antizapret-awg/clients/**
     (exclude stats.db, venv, __pycache__)
  3. import on replica (replace those trees)
  4. apply_awg2_runtime on replica
       (awg syncconf and/or systemctl restart awg-quick@<iface>)
  5. ensure shadow VpnConfig rows (existing HA machinery)
```

### Код

| Место | Изменение |
|-------|-----------|
| `vpn_state_sync.sync_vpn_crypto_from_primary` | `elif vpn_type == VpnType.amneziawg2: sync_amneziawg2_state_from_primary(...)` |
| `vpn_state_sync` | Новые `export/import` helpers + `sync_amneziawg2_state_from_primary` |
| `Awg2Service` / adapter / node_agent | `export_awg2_state_archive`, `import_awg2_state_archive`, `apply_awg2_runtime` |
| `client_sync.maybe_replicate_*` | Убрать skip для `amneziawg2` (волна 1) |
| `replicate.py` | Create/delete для amneziawg2 идут через crypto sync, не stock `client.sh` |
| Push full | Включить AWG2 state, если primary installed |

### Preflight UI

- На `/awg2` и в карточке HA-группы: предупреждение, если у replica `awg2` not installed.  
- `ha_replicate_warning` при create — как у WG.

### Endpoint / host caveat

Клиентские `Endpoint=` используют `WIREGUARD_HOST` / shared domain группы. Порты берутся из скопированного `services.env`. Админ должен понимать: failover по DNS/VIP группы, не «другой IP в старом conf без смены Endpoint».

## Обфускация

### CLI (upstream)

- `awg-obfuscation --show`
- `awg-obfuscation --regenerate` (+ apply)
- `awg-obfuscation --preset … --template … [--mtu …] [--host …] --apply`
- После смены профиля: `awg-client regen-all`

### API

| Метод | Путь | Тело / результат |
|-------|------|------------------|
| GET | `/api/awg2/obfuscation` | meta + non-secret params summary |
| POST | `/api/awg2/obfuscation/regenerate` | regen+apply+regen-all; затем HA sync |
| POST | `/api/awg2/obfuscation/apply` | `{preset, template, mtu?, host?, fp?}` → apply+regen-all; HA sync |

Ошибки CLI → 502 с stderr. Слой не установлен → 409.

### UI вкладка «Обфускация»

- Блок текущего профиля (preset/template/mtu/host)  
- Кнопка «Перегенерировать сигнатуры»  
- Форма Apply: select preset, select template, optional MTU/host  
- После успеха: alert re-import; список клиентов для скачивания  
- HA sync errors в том же alert  

Presets: `router`, `low`, `medium`, `high`, `paranoid`.  
Templates: `quic`, `tls`, `web`, `voip`, `dns`, `mixed`.

## Мониторинг

### API

| Метод | Путь | Результат |
|-------|------|-----------|
| GET | `/api/awg2/monitoring` | `{ ifaces: [...], clients: [...], stats_available: bool }` |

- `ifaces`: из `awg show` / services.env (name, port, subnet, peer_count, transfer if cheap)  
- `clients`: из `awg_stats.py overview` (name, online, handshake_age_s, rx, tx)  
- Если нет `stats.db` или overview пуст: `stats_available=false`, `clients` строится из live `awg show dump` (online/handshake/transfer), без 500.  

`stats.db` path: `/opt/antizapret-awg/stats.db` (node-local).

### UI вкладка «Мониторинг»

- Карточки интерфейсов  
- Таблица клиентов (online badge, handshake, traffic)  
- Refresh  

## Страница `/awg2` (итог вкладок)

| Вкладка | Волна |
|---------|-------|
| Клиенты | 1 |
| Обфускация | 2 |
| Мониторинг | 2 |
| Справка | 1 (обновить: HA теперь есть; убрать «HA позже») |

## Тесты

- Archive export/import round-trip (tmpdir mocks)  
- Runtime apply invoked after import  
- Replica not installed → error includes install_command  
- `maybe_replicate_create` **does** run for amneziawg2  
- Obfuscation regenerate/apply builds expected CLI; triggers HA sync mock  
- Monitoring overview parse; missing stats.db → no 500  
- Adapter Local/Remote parity for new methods  
- Regression: stock WG `sync_wireguard_state_from_primary` unchanged  

## Документация

- Обновить `docs/awg2.md` — HA, обфускация, мониторинг  
- `docs/NodeSync.md` — AWG2 crypto paths / excludes (`stats.db`)  
- `docs/PROJECT_MAP.md`, `CHANGELOG.md`  
- В спеке волны 1: критерий «HA skip» пометить как superseded волной 2  

## Риски

| Риск | Митигация |
|------|-----------|
| Порт/Endpoint при failover | Копировать `services.env`; опираться на shared WG domain |
| Apply обфускации ломает старые conf | Warning + regen-all + docs |
| syncconf vs restart | Prefer syncconf; fallback restart units из services.env |
| Большой archive | Те же таймауты, что WG profile archive |
| Гонка с ботом az-awg2 при obfuscation | flock на CLI apply/regen-all |

## Критерии готовности волны 2

1. Create `amneziawg2` в HA-группе → files+peers на replica (при установленном слое).  
2. Replica без слоя → replicate error с install_command, не silent skip.  
3. Obfuscation apply на primary отражается на replica; UI предупреждает о re-import.  
4. Monitoring показывает overview online/traffic (или честный empty state).  
5. Сток WG HA и download AWG2 волны 1 без регрессий.  
6. Тесты раздела «Тесты» зелёные.

## Волна 3 (не реализовывать здесь)

Эпик: [`2026-08-10-az-awg2-wave3.md`](2026-08-10-az-awg2-wave3.md) — подволны 3a (install/TTL/backup), 3b (TG/Mini App), 3c (access + deep stats).
