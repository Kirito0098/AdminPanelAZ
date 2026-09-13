# Backup restore coverage matrix (A → B → C)

**Дата:** 2026-09-12  
**Статус:** approved + implemented  
**Ветка:** `feature/client-portal`  
**Подход:** spec + checklist + точечные UX/тесты (не machine-image в tar)  
**Связанные спеки:** `2026-09-12-backup-portal-restore-design.md`, `2026-08-17-backup-restore-parity-design.md`

## Цель

Зафиксировать, что `adminpanelaz_*.tar.gz` (и опциональные слои) реально покрывают для восстановления работы по сценариям **A → B → C**, отделить `covered` / `optional` / `manual` / `gap`, и закрыть только узкие UX-дыры без упаковки nginx/LE/systemd в архив.

## Сценарии успеха

| Сценарий | Успех |
|----------|--------|
| **A** Same-host panel | После restore: логин, клиенты, политики/`access_until`, unlock/portal tokens в БД; API панели жив. VPN-диск не трогали → клиенты могут уже коннектиться. |
| **B** Portal HTTPS | A + `PORTAL_DOMAIN` в `.env` + ручной шаг **Подписка → «Настроить под текущую публикацию»** (+ DNS A). Nginx/LE портала **не** в tar. |
| **C** Full DR | A+B + отдельный полный AntiZapret (`client.sh 8`) и/или AWG2 overlay + **Применение** / **Push full** / живой node-agent на нодах по необходимости. На чистом хосте дополнительно: install, systemd, `.venv`, `frontend/dist`, panel nginx. |

## Статусы строк матрицы

- **covered** — в panel tar и применяется restore’ом (или sync после restore).
- **optional** — в tar только при флаге/настройке; без флага сценарий не обязан.
- **manual** — намеренно вне panel tar; нужен явный чеклист/hint.
- **gap** — должно быть covered/manual, но сейчас вводит в заблуждение или не хватает hint; чинится в коде/docs.

## Матрица покрытия

| Компонент | A | B | C | Статус | Примечание |
|-----------|---|---|---|--------|-----------|
| `adminpanel.db` (юзеры, узлы, политики, `access_until`, portal/unlock) | ✓ | ✓ | ✓ | covered | всегда в tar (`data/adminpanel.db`) |
| `cidr.db` | ✓ | — | ✓ | covered | если файл есть |
| `.env` + sync `PORTAL_DOMAIN` | ✓ | ✓ | ✓ | covered | sync после restore уже есть |
| Списки AntiZapret (5 txt) | ○ | — | ○ | optional | галочка/авто; после restore — **Применение** |
| AWG2 narrow overlay | ○ | — | ○ | optional | галочка / `backup_awg2_enabled`; нужен слой на узле |
| Полный AZ (`client.sh 8`) | — | — | ✓ | optional | **отдельный** `backup-*.tar.gz`, не член panel tar; restore на VPN-хосте |
| Portal nginx + LE | — | ✓ | ✓ | manual | Подписка → «Настроить…»; DNS |
| Panel nginx / `ACCESS_PATH` | ○ | ○ | ✓ | manual | на живом хосте часто уже есть; на чистом — `nginx-setup` |
| systemd / `.venv` / `frontend/dist` | ○ | ○ | ✓ | manual | C: install; A на живом хосте обычно ок |
| Node-agent / mTLS на репликах | — | — | ○ | manual | HA: Push full + живой agent |
| Cloudflare realip / TG webhook URL | ○ | — | ○ | manual | re-apply при CF/смене URL |
| AWG2 `stats.db` | — | — | — | manual | намеренно не в backup (только статистика) |

**Легенда ячеек:** ✓ нужно для успеха сценария · ○ часто нужно / зависит от установки · — не требуется для сценария.

## Что в panel tar (факт)

**Всегда (если файлы существуют):** `data/adminpanel.db`, `data/cidr/cidr.db`, `env/.env`.  
**Опционально в том же tar:** `antizapret/config/{include,exclude}-{hosts,ips}.txt`, `allow-ips.txt`; `awg2/az-awg2-backup.tar.gz`.  
**Не в panel tar:** полный AZ, nginx/certs, systemd, SPA dist, node-agent, CF snippet, AWG2 stats.

Sidecar метаданных: `adminpanelaz_….json` с `components` ∈ {`db`,`cidr_db`,`env`,`configs`,`awg2`}. Тег `antizapret_backup` в metadata panel-архива **не** появляется — полный VPN отдельно.

## Restore flow (кратко)

| | API | CLI |
|--|-----|-----|
| Порядок | load → overlays(adapter) → dispose → sqlite/env → portal sync → restart | stop → load → sqlite/env → overlays(local) → portal sync → start |
| Применение | hint если были configs | stdout |
| Push full | **сейчас нет hint** (gap #1) | stdout если configs/awg2 |
| Portal | `portal_reprovision_needed` + hint на `POST /restore` | stdout |
| upload+restore | возвращает `BackupEntry` без detail hints (gap #2) | n/a |

## Gaps → фиксы (в scope)

| # | Gap | Решение |
|---|-----|---------|
| 1 | API restore без Push full hint при configs/awg2 | `_restore_response`: добавить hint как у CLI |
| 2 | upload+restore без apply/portal hints | При `restore=true` включить в ответ `detail` с hint-полями **или** статическое UI-сообщение после upload-restore (предпочтительно detail, едино с `/restore`) |
| 3 | Путаница «полный VPN в panel-архиве» | BackupTab + `docs/nastrojki/rezervnye-kopii.md`: полный AZ = отдельный файл; не ждать badge `antizapret_backup` в panel list |

## Вне скоупа

- Упаковка nginx / Let’s Encrypt / self-signed / systemd / `frontend/dist` в tar.
- Автозапуск `task_portal_publish`, certbot, Применение, Push full без явного действия админа.
- Полный machine-image backup.

## Чеклист после restore (docs)

**A:** дождаться рестарта → логин → клиенты/даты/unlock на месте.  
**B:** A + Подписка → «Настроить под текущую публикацию» + DNS.  
**C:** B + restore AZ-архива на VPN (если диск потерян) + optional AWG2 + Применение + Push full при HA + проверка node-agent.

## Тесты / verification

- Существующие: `test_backup_*`, `test_backup_portal_restore`, portal tests.
- Добавить: `_restore_response` содержит Push full hint при configs и/или awg2; при реализации gap #2 — detail на upload+restore.
- Критерий готовности: матрица в этой спеке; gaps 1–3 закрыты; тесты зелёные; machine-image по-прежнему вне scope.

## Критерии готовности

1. Спека approved пользователем.  
2. Gaps 1–3 реализованы (или явно переведены в `manual` с текстом в UI/docs).  
3. Чеклист A/B/C в пользовательской доке.  
4. Регрессия backup/portal tests проходит.
