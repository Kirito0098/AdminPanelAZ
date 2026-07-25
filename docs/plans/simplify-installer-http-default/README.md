# План: упрощение установщика — HTTP по умолчанию, без простого мастера

**Статус:** реализовано (релиз **2.19.0**, 2026-07-26)  
**Аудитория:** разработчики / агенты Cursor  
**Связано:** [docs/nastrojki/set-i-publikaciya.md](../../nastrojki/set-i-publikaciya.md), мастер UI «Настройки → Адрес сайта и HTTPS»

| Файл | Содержание |
|------|------------|
| [README.md](README.md) | Решения, обоснования, критерии приёмки (этот файл) |
| [PROMPTS.md](PROMPTS.md) | Индекс этапов 00–07 |
| [00-inventory.md](00-inventory.md) … [06-acceptance-smoke.md](06-acceptance-smoke.md) | Промпт + чеклист + проверки |
| [07-release-docs-changelog-promo.md](07-release-docs-changelog-promo.md) | **Релиз:** все README/инструкции, CHANGELOG, версия, `05-whats-new.png` |

**Реализация:** копируй промпты по порядку из [PROMPTS.md](PROMPTS.md) (`00`→`07`). Не пропускай этап 04 без замены systemd `ExecStart`. Не пропускай этап **07** (версия + promo).

---

## Цель

1. **Убрать из установщика выбор способа публикации** (Nginx / uvicorn HTTPS / HTTP / localhost).
2. **Ставить панель всегда в режиме прямого HTTP** — домен, TLS, nginx/uvicorn настраиваются уже в панели.
3. **Удалить простой установщик** (`install-easy.sh` + easy-wizard) — остаётся один путь: `install.sh` + полный мастер без шага HTTPS.
4. **Убрать вопрос «Внешний IP или домен»** на шаге «Сеть и порты» — он нужен был в основном под CORS/подсказки/дефолт для HTTPS и путает пользователя.
5. **Убрать вопрос «Разрешить внутренние (приватные) IP для узлов?»** — типичный сценарий: панель+нода на одном сервере или доп. ноды по интернету (публичный IP/домен); LAN-ноды — редкость.
6. **Убрать выбор APP_ENV** — в install всегда `production` (development только у разработчиков вручную / через env).
7. **Убрать выбор способа запуска** (вручную / daemon / systemd) — всегда **systemd**.
8. **Удалить `start.sh` и `start_node_agent.sh`** — после перевода systemd unit’ов на прямой запуск uvicorn/agent (сейчас unit’ы вызывают эти скрипты).
9. **Убрать шаг «Дополнительная безопасность»** (mTLS / ротация API-ключа узлов) — продвинутое; настраивается после установки (UI «Узлы» / `.env` / docs).
10. **Убрать выбор профиля ресурсов** — всегда **`full`**; ненужные фоновые задачи отключат в панели (Модули / профили).
11. **Убрать шаг «Опциональные функции»** (Telegram token, автобэкап, CIDR hour, traffic sync) — настройка в веб-UI; модуль Telegram **доступен** без предварительного «включения» в install.
12. **Убрать шаг Firewall** — не спрашивать и не применять ufw/iptables из мастера; рекомендации — в SECURITY.md / docs (при HTTP-default старый совет «закрыть 8000, только Nginx» ещё и врёт).

Остальные вопросы мастера (тип установки, порт backend, DDNS, admin, node agent, paths и т.д.) **сохраняются**.

---

## Решения (зафиксировать)

| Тема | Решение |
|------|---------|
| Дефолт публикации | `http_direct`: `BACKEND_HOST=0.0.0.0`, `BEHIND_NGINX=false`, без nginx/certbot |
| Почему не `none` (localhost) | После установки панель должна открываться с LAN/VPS по `http://IP:порт/` без SSH-туннеля |
| HTTPS / домен | Только через UI: **Настройки → Адрес сайта и HTTPS** (уже есть 7 режимов) |
| Простой установщик | Удалить полностью; в README/справке — только `install.sh` |
| Env/CI-флаги `WIZ_NGINX_MODE=…` | Опционально оставить для неинтерактивных сценариев; **интерактивно не спрашивать** |
| ACCESS_PATH / StatusOpenVPN при install | Убрать вместе с HTTPS-шагом; сценарий только через UI после установки |
| DDNS в мастере | Оставить (DNS), но **не** привязывать к автонастройке Let's Encrypt / nginx |
| Вопрос «Внешний IP или домен» | **Убрать**. IP для URL/CORS — автодетект; при DDNS имя берётся из DuckDNS/No-IP; CORS при публикации в UI обновляет `nginx_apply_*` |
| `ALLOW_INTERNAL_NODES` | Всегда **`false`** при install (без вопроса). Панель+нода на одном хосте и ноды в интернете этого не требуют. LAN-ноды (`192.168`/`10.x`) — вручную в `.env` при необходимости |
| `APP_ENV` | Всегда **`production`** при install (без вопроса). `development` — только вручную в `.env` / `WIZ_APP_ENV=development` для разработчиков |
| Запуск после установки | Всегда **systemd**. Цель: **удалить** `start.sh` / `start_node_agent.sh` после перевода unit-файлов на прямой запуск (сейчас `ExecStart=…/start.sh watchdog prod` — без замены удалять нельзя) |
| mTLS / ротация API-ключа в install | **Не спрашивать.** Дефолт: mTLS выкл. на уровне install-флагов; ротация `0` (выкл.). Включение — в UI «Узлы» (per-node mTLS) и docs; `NODE_AGENT_MTLS_ENABLED` в `.env` панели уже deprecated |
| Профиль ресурсов (minimal/standard/full) | Всегда **`full`** при install (без вопроса). Урезать нагрузку — в UI после установки. В docs: что делает full и как сменить профиль |
| Опциональные функции (Telegram / бэкап / CIDR / traffic) | **Не спрашивать.** CIDR+traffic — из профиля `full`. Автобэкап — разумный дефолт вкл. (или тоже только UI). Telegram: **не** сеять token в install; `FEATURE_TELEGRAM_ENABLED=true` по умолчанию, чтобы раздел был в меню — token/chat настраивают в UI |
| Firewall в install | **Не спрашивать / не применять.** Старый совет «закрыть 8000, только Nginx» неверен при HTTP-default. Рекомендации — SECURITY.md; publish в UI может открыть порты сам |
| Python runtime | **Не менять политику:** Ubuntu 24.04 → **3.12**, Debian 13 → **3.13** (`scripts/python-runtime.sh`). Install/venv/systemd должны опираться на `ap_ensure_venv` / существующий venv |

---

## Зачем убираем «Внешний IP или домен»

Сейчас `wizard_ask_network` спрашивает:

> Внешний IP или домен (для CORS и подсказок; Enter — localhost)

И рядом бокс про «backend только на 127.0.0.1, наружу через Nginx на шаге Публикация» — это **устареет** после HTTP-default.

Фактически `WIZ_SERVER_ADDRESS` шёл в:

| Использование | Замена после упрощения |
|---------------|------------------------|
| `CORS_ORIGINS` (`wizard_derive_cors_origins`) | Авто: localhost + детект primary IP (`server_primary_ip` / аналог в install) + порт; при публикации UI перезапишет CORS |
| Summary / post-install URL | `http://$(детект_IP):$BACKEND_PORT/` |
| Дефолт домена на шаге HTTPS | Шага больше нет |
| Подстановка из DDNS, если адрес пустой | При выбранном DDNS — FQDN уже известен; для CORS/подсказки можно взять его без отдельного вопроса |
| Fallback IP для firewall / node allowed | Не нужен отдельный вопрос «внешний адрес»; firewall-шаг тоже убираем |

**Итог:** вопрос не даёт пользователю понятной пользы и дублирует DDNS / будущий UI.

---

## Зачем убираем «Разрешить внутренние IP для узлов?»

Флаг `ALLOW_INTERNAL_NODES` запрещает добавлять узлы с приватными адресами (`10.x`, `192.168.x`, …) — защита от случайного/опасного хоста.

Типичные сценарии AdminPanelAZ:

| Сценарий | Нужен ли `true`? |
|----------|------------------|
| Панель + нода на **одном** сервере | Нет (локальный agent / не «удалённый приватный IP» в UI как обычный remote) |
| Доп. ноды **через интернет** (публичный IP/домен) | Нет — как раз дефолт `false` |
| Несколько машин в **одной LAN** по `192.168…` | Да, но это редкий homelab-кейс → `.env` вручную |

Интерактивный вопрос почти всегда получает `n` и только шумит. В install: не спрашивать, писать `ALLOW_INTERNAL_NODES=false`. Env-override `WIZ_ALLOW_INTERNAL_NODES=true` для CI/особых сетапов — по желанию сохранить.

---

## Зачем убираем выбор APP_ENV (production / development)

Шаг «Режим приложения и безопасность» предлагает development vs production. Для пользователей установщика нужен только **production** (политика паролей, секреты, заголовки).

- `development` — локальная разработка панели, не сценарий `sudo ./install.sh` на VPS.
- В install: не спрашивать, всегда `WIZ_APP_ENV=production` / `APP_ENV=production`.
- Разработчикам: `APP_ENV=development` в `.env` или редкий env-override — вне интерактивного мастера.

Текст бокса про «production + HTTPS» при HTTP-default заменить в summary на «HTTPS настроите в панели».

---

## Зачем убираем выбор «вручную / daemon / systemd»

Шаг «Сервисы и автозапуск» предлагает три режима. На практике (включая разработку на VPS) используют только **systemd**.

| Вариант | Зачем был | Нужен ли в install |
|---------|-----------|-------------------|
| Вручную (`./start.sh`) | Исторически «для тестов» | Нет |
| Daemon + watchdog | Обход без systemd | Нет |
| Systemd | Автозапуск, restart, journalctl | **Всегда** — и prod, и dev на сервере |

В install: не спрашивать → `WIZ_RUN_MODE=systemd` / `WITH_SYSTEMD=true`.  
**Uvicorn workers:** почти всегда `1` → зафиксировать без вопроса (больше — вручную в `.env`).

Вопрос «Количество uvicorn workers» в мастере не нужен: для типичных VPS хватает одного процесса; `>1` редко и требует Redis для rate limit — это не выбор при первой установке.

**Документация (обязательно):** в README / docs (например SECURITY или раздел backend/.env) явно описать:
- по умолчанию `UVICORN_WORKERS=1`;
- как увеличить: `UVICORN_WORKERS=N` в `backend/.env` + `systemctl restart adminpanelaz`;
- при `N>1` нужен Redis для корректного rate limit (и где это настраивается).

---

## Зачем убираем «Дополнительная безопасность» (mTLS / ротация ключа)

Шаг спрашивает:

1. **mTLS панель ↔ node agent** — взаимные TLS-сертификаты (+ потом `generate-mtls-certs.sh`).
2. **Ротация API-ключа узлов** (дней).

Почему не в install:

| Факт | Вывод |
|------|--------|
| Для controller default в мастере сейчас **`Y`** при тексте «если не уверены — n» | Путает и включает сложность «из коробки» |
| В панели mTLS уже **per-node** из UI («Узлы» → включить mTLS); глобальный флаг `.env` deprecated | Дублирование и устаревший путь |
| Ротация ключа есть вручную/по расписанию в продукте | Достаточно docs + UI, не вопрос при первой установке |
| Типичный сетап: панель+нода на одном сервере / ноды по интернету с API-ключом | mTLS — редкий hardening |

В install: **пропустить шаг**; `WIZ_NODE_AGENT_MTLS_ENABLED=false`, `WIZ_NODE_API_KEY_ROTATION_DAYS=0`.  
В docs: как включить mTLS из UI и (при необходимости) скрипт сертификатов; как задать `NODE_API_KEY_ROTATION_DAYS`.

Redis-вопрос внутри этого шага (только при workers>1) тоже отпадает вместе с фиксацией workers=1.

---

## Зачем убираем выбор профиля ресурсов (minimal / standard / full)

Шаг оценивает RAM и предлагает урезать фоновые workers. Для продукта проще:

- поставить **полный** набор (`WIZ_RESOURCE_PROFILE=full` → `apply-resource-profile.py full`);
- пользователь сам выключит ненужное в **Настройки → Модули** (или сменит профиль там же).

Иначе новичок на 1 GB может выбрать minimal и потом удивляться, что «не работает CIDR/traffic». Лучше полный функционал + понятное отключение в UI.

В docs: краткое описание профилей и где переключить после установки; предупреждение про RAM (~400 MB full stack с локальной нодой).

---

## Зачем убираем «Опциональные функции» (Telegram, бэкап, CIDR, traffic)

Сейчас `wizard_ask_optional` спрашивает CIDR refresh (+ час/минута), traffic sync, Telegram (token/chat), автобэкап.

Проблема с Telegram (как на скрине):

- Ответ **`n`** → токены не пишутся; плюс в `env_defaults.sh` уже **`FEATURE_TELEGRAM_ENABLED=false`** — раздел Telegram в меню недоступен, пока вручную не включат модуль.
- Ответ **`y`** → только seed token/chat; сам мастер пишет, что модуль всё равно «включается позже в Настройки → Модули».
- Итог: спрашивать в SSH бессмысленно — проще один раз настроить в веб-UI; «n» ощущается как «модуль вырезан».

Решение:

| Тема | Дефолт install | Где настраивать |
|------|----------------|-----------------|
| Feature Telegram | `FEATURE_TELEGRAM_ENABLED=true` (модуль виден) | Token, chat, notify — страница Telegram в UI |
| Автобэкап | вкл. с интервалом 7 дн. **без вопроса** (или только UI — зафиксировать одно) | Настройки бэкапов |
| CIDR / traffic | из профиля `full` (`true`) без отдельных yes/no | Модули / `.env` |
| Шаг `wizard_ask_optional` | **удалить** | — |

В docs: «после установки откройте Telegram в настройках и укажите bot token».

---

## Зачем убираем шаг Firewall

Сейчас `wizard_ask_firewall` показывает «планируемые правила» и предлагает ufw/iptables. Типичный текст: закрыть 8000, снаружи только Nginx — это было под старую схему «backend на 127.0.0.1 + nginx».

При дефолте **HTTP на `0.0.0.0:порт`** такой шаг:

- либо **ломает доступ** к панели, если закрыть backend-порт;
- либо показывает устаревшие/нерелевантные правила;
- большинству неинтересен на этапе install (firewall часто уже у хостера / вручную).

Решение: **не вызывать** `wizard_ask_firewall`; `WIZ_CONFIGURE_FIREWALL=false`.  
Документировать: какие порты слушает панель после install; как открыть/закрыть у провайдера или ufw; при публикации через nginx UI/`firewall_apply_publish_mode` может править правила сам.

---

## Удаление `start.sh` и `start_node_agent.sh`

**Сейчас удалять нельзя «как есть».** Systemd unit’ы вызывают именно их:

```text
systemd/adminpanelaz.service
  ExecStart=…/start.sh watchdog prod
  ExecStop=…/start.sh stop

systemd/adminpanelaz-node.service
  ExecStart=…/start_node_agent.sh watchdog prod
  ExecStop=…/start_node_agent.sh stop
```

Также fallback’и: `install.sh` (daemon path), `nginx-setup.sh` / `nginx-repair.sh` restart, `panel_restart_command()`, `adminpanel-menu.sh`, site-diagnostics, CI shellcheck, bootstrap-проверка наличия `start.sh`.

### Решение

1. Переписать unit’ы на **прямой** запуск (systemd сам рестартит — отдельный bash-watchdog не нужен):
   - panel: `ExecStart=…/backend/.venv/bin/uvicorn app.main:app --host … --port …` (+ SSL flags из env при `USE_HTTPS`);
   - node: `ExecStart=…/backend/.venv/bin/python -m …` (как сейчас делает `start_node_agent.sh` внутри).
2. `Restart=on-failure` уже в unit — логика watchdog из скриптов не нужна.
3. Все места с `./start.sh restart` → `systemctl restart adminpanelaz` (и аналог для node).
4. Удалить `start.sh`, `start_node_agent.sh`; обновить README, PROJECT_MAP, diagnostics, CI.
5. Bootstrap install: проверка «репо целое» — по `install.sh` + `backend/requirements.txt` + `systemd/*.service`, не по `start.sh`.

### Объём

Отдельный подэтап после упрощения мастера (или сразу в том же PR, но это уже не «только wizard»). Без переписывания unit’ов скрипты оставить нельзя.

---

## Что остаётся в мастере `install.sh`

Порядок (после изменений):

1. Тип установки (controller / +VPN / node)
2. AntiZapret (если нужен)
3. **Сеть и порты** — только порт backend (+ node port при необходимости); **без** «внешний IP/домен» и **без** «внутренние IP узлов»
4. DDNS (DuckDNS / No-IP / нет) — без авто-HTTPS; подпись «только DNS»
5. ~~App env~~ → **всегда production**
6. ~~Публикация и HTTPS~~ → **удалить**
7. Admin login/пароль
8. Node agent (если выбран)
9. ~~Сервисы: вручную/daemon/systemd + workers~~ → **всегда systemd, workers=1**
10. ~~Дополнительная безопасность (mTLS / ротация)~~ → **пропустить, дефолты off**
11. ~~Профиль ресурсов~~ → **всегда full** (без вопроса)
12. ~~Опциональные функции~~ → **удалить** (Telegram/бэкап/CIDR-вопросы); дефолты выше
13. Paths (BACKUP_ROOT и state dirs)
14. ~~Firewall~~ → **удалить** (не применять из мастера)
15. Summary → preflight портов → confirm

---

## Дефолт `.env` после установки (controller)

```text
BACKEND_HOST=0.0.0.0
BACKEND_PORT=<из мастера, обычно 8000>
BEHIND_NGINX=false
PUBLISH_MODE=http_direct
ALLOW_INTERNAL_NODES=false
APP_ENV=production
FEATURE_TELEGRAM_ENABLED=true
# UVICORN_WORKERS=1 (дефолт)
# RESOURCE_PROFILE=full (apply-resource-profile)
# unit systemd включается при установке (WITH_SYSTEMD)
# USE_HTTPS / SSL_* / DOMAIN / HTTPS_PUBLIC_PORT / HTTP_ACME_PORT / ACCESS_PATH — не задавать
# CORS_ORIGINS — localhost + http://<detected-ip>:<port> (+ vite dev ports при необходимости)
```

Post-install summary:

- Основной URL: `http://<auto-detected-IP>:<BACKEND_PORT>/` (если DDNS — можно показать и FQDN как «после настройки HTTPS»)
- Подсказка: «HTTPS и домен — в панели: Настройки → Адрес сайта и HTTPS»

При `WIZ_ACCEPT_DEFAULTS=true` — тот же `http_direct` (не localhost `none`, как сейчас).

---

## Удаление простого установщика

### Файлы к удалению

- [`install-easy.sh`](../../../install-easy.sh)
- [`scripts/install-easy-wizard.sh`](../../../scripts/install-easy-wizard.sh)

### Ссылки и ветки кода к подчистить

| Место | Действие |
|-------|----------|
| `install.sh` | Убрать `--easy`, `source install-easy-wizard.sh`, упоминания в шапке/help/ошибках |
| `scripts/install-ui.sh` | Убрать пункт меню / `--easy` / примеры `install-easy.sh` |
| `README.md` | Быстрый старт → только `install.sh`; убрать wget easy |
| `docs/**` | Заменить `install-easy.sh` на `install.sh` (в т.ч. StatusOpenVPN) |
| `CHANGELOG.md` | Unreleased: Removed easy installer + Changed install defaults |
| Тесты (`scripts/test-install-*.sh` и т.п.) | Убрать/переписать кейсы easy / HTTPS-выбора / SERVER_ADDRESS в wizard |
| CI / pre-commit / PROJECT_MAP | Если есть ссылки — обновить |

Bootstrap «скачал один sh и запустил» остаётся на **`install.sh`** (у него уже есть remote bootstrap).

---

## Изменения в полном мастере

### Удалить / упростить

- Вызов `wizard_ask_https` из `run_install_wizard`
- Вызов `wizard_ask_app_env` — заменить на `WIZ_APP_ENV=production` (функцию можно удалить или оставить no-op)
- Вызов `wizard_ask_services` — заменить на apply systemd + `WIZ_UVICORN_WORKERS=1` (без choice manual/daemon)
- Вызов `wizard_ask_security_hardening` — убрать; mTLS=false, rotation=0
- Вызов `wizard_ask_resource_profile` — убрать; всегда `WIZ_RESOURCE_PROFILE=full` + apply
- Вызов `wizard_ask_optional` — убрать; не сеять Telegram из install; `FEATURE_TELEGRAM_ENABLED=true` в `env_defaults.sh`
- Вызов `wizard_ask_firewall` — убрать; не вызывать `firewall_apply_*` из install-wizard
- Тело `wizard_ask_https` и зависимые ветки (домен LE, email, порты 80/443, cert paths, publish uvicorn из install)
- `wizard_ask_access_path_and_status` / integrate Status — **только из install-пути** (функции можно оставить для `nginx-setup.sh` / UI)
- В `wizard_ask_network`:
  - убрать prompt «Внешний IP или домен…»
  - убрать yes/no «Разрешить внутренние (приватные) IP для узлов?» → всегда `WIZ_ALLOW_INTERNAL_NODES=false`
  - убрать/переписать `ui_info_box` про 127.0.0.1 + Nginx на шаге «Публикация»
  - **не** форсировать `WIZ_BACKEND_HOST=127.0.0.1` — для default publish будет `0.0.0.0`
  - оставить: порт backend, порт node (если нужно)
- Зависимость summary/CORS/firewall от ручного `WIZ_SERVER_ADDRESS` — заменить на автодетект (+ FQDN из DDNS, если есть)
- Убрать строку summary «Внутренние IP узлов», либо показывать фиксированно `false`

### Добавить

- `wizard_apply_default_publish_http_direct`:
  - `WIZ_NGINX_MODE=http_direct`, `WIZ_BACKEND_HOST=0.0.0.0`, `WIZ_BEHIND_NGINX=false`
  - не задаёт доменные HTTPS-переменные
- `wizard_derive_cors_origins` без обязательного `WIZ_SERVER_ADDRESS`: localhost + detected IP [:port]; если DDNS FQDN известен — добавить `http://fqdn:port`
- Хелпер детекта IP для summary (переиспользовать логику `nginx_server_primary_ip` / аналог)
- В summary: «Публикация: HTTP напрямую → HTTPS в панели»
- Preflight: проверять **backend port** (+ node), **не** 80/443 по умолчанию

### `setup_nginx_if_selected` в `install.sh`

При `http_direct` уже есть ветка — дефолтный путь всегда в неё; nginx/certbot не ставить.

---

## Документация и UX после установки

1. **README** — один быстрый старт; сначала HTTP по IP:порт, HTTPS в настройках.
2. **set-i-publikaciya.md** — StatusOpenVPN / подпуть: только «install → UI».
3. Telegram / бэкапы / модули — «настройте в панели», не в install.
4. Firewall — кратко в SECURITY.md / README (порты после HTTP-default; не закрывать backend-порт, пока панель на нём).
5. (Опционально) баннер в UI при `http_direct`: «Настройте домен и HTTPS».

---

## Неинтерактивный режим / обратная совместимость

- Интерактивно HTTPS и SERVER_ADDRESS не спрашивать.
- Env `WIZ_NGINX_MODE=le|…` — можно уважать для CI.
- Env `WIZ_SERVER_ADDRESS` — если задан снаружи, можно учесть в CORS; интерактивно не спрашивать.
- Документировать override’ы в help/`--help`.

---

## Критерии приёмки

- [x] Нет `install-easy.sh` / `install-easy-wizard.sh`; нет `--easy` в help.
- [x] Интерактивный `install.sh` не показывает шаг «Способ публикации» / 8 вариантов HTTPS.
- [x] Нет вопроса «Внешний IP или домен…»; нет устаревшего бокса про Nginx на шаге «Публикация».
- [x] Нет вопроса про внутренние IP узлов; в `.env` `ALLOW_INTERNAL_NODES=false`.
- [x] Нет шага выбора APP_ENV; в `.env` `APP_ENV=production`.
- [x] Нет выбора вручную/daemon/systemd; ставится systemd, workers=1.
- [x] Нет шага mTLS / ротации ключа; дефолты выкл.
- [x] Нет выбора профиля ресурсов; применяется `full`.
- [x] Нет шага Telegram/бэкап/CIDR-опций; `FEATURE_TELEGRAM_ENABLED=true`; настройка Telegram в UI без «сначала включить модуль».
- [x] Нет шага Firewall; install не трогает ufw/iptables сам.
- [x] Нет `start.sh` / `start_node_agent.sh`; unit’ы запускают venv/uvicorn (или python agent) напрямую; restart только через systemctl.
- [x] После установки controller: слушает `0.0.0.0:<port>`, URL в summary с авто-IP; nginx не из коробки (без env-override).
- [x] CORS достаточен для входа по `http://IP:port` (или обновляется при первом publish в UI).
- [x] Остальные шаги на месте (тип, порт, DDNS, admin, paths, …).
- [x] Docs/README без easy; StatusOpenVPN через UI.
- [x] В инструкциях описано, как вручную задать `UVICORN_WORKERS>1` и зачем Redis.
- [x] В инструкциях описано включение mTLS (UI) и ротации ключа (при необходимости).
- [x] В инструкциях: профиль full по умолчанию и как урезать в UI; RAM-ориентир.
- [x] В инструкциях: настройка Telegram в веб-UI (модуль не «вырезан» после install).
- [x] В инструкциях: порты / firewall после HTTP-default (не закрывать порт панели до перехода на nginx).
- [x] В инструкциях: Python — Ubuntu 3.12 / Debian 3.13 автоматически (`python-runtime.sh`).
- [x] `bash -n`; релевантные `test-install-*.sh` зелёные.
- [x] Smoke: install → login по IP → VpnNetwork publish → nginx_le или uvicorn_le.
- [x] Smoke Python: на Ubuntu venv = 3.12; на Debian = 3.13.
- [x] **Релиз (этап 07):** все пользовательские README/инструкции согласованы с новым install.
- [x] **Релиз:** `CHANGELOG.md` — секция новой версии заполнена; Unreleased очищен.
- [x] **Релиз:** версия панели проставлена (README badge + «Текущая версия», `frontend/package.json`).
- [x] **Релиз:** обновлён [`docs/assets/telegram-promo/05-whats-new.png`](../../assets/telegram-promo/05-whats-new.png) под новую версию и темы релиза.

---

## Ручная проверка (VPS)

Короткий smoke после зелёных автопроверок этапа [06](06-acceptance-smoke.md):

```text
1. Ubuntu 24.04: sudo ./install.sh → в venv python 3.12; панель http://IP:8000/; systemctl status adminpanelaz
2. Debian 13 (если есть): то же → python 3.13
3. Логин admin → Настройки → Адрес сайта и HTTPS → nginx_le или uvicorn_le → сайт открывается
4. Telegram в меню доступен без «включить модуль»; token задаётся в UI
5. systemctl restart adminpanelaz работает; start.sh отсутствует
```

Полный чеклист приёмки и автопроверки — в [06-acceptance-smoke.md](06-acceptance-smoke.md).

---

## Этапы реализации

Пошаговые промпты — отдельные файлы (порядок в [PROMPTS.md](PROMPTS.md)):

| # | Файл |
|---|------|
| 00 | [00-inventory.md](00-inventory.md) |
| 01 | [01-http-default-network.md](01-http-default-network.md) |
| 02 | [02-strip-wizard-steps.md](02-strip-wizard-steps.md) |
| 03 | [03-remove-easy.md](03-remove-easy.md) |
| 04 | [04-systemd-delete-start-sh.md](04-systemd-delete-start-sh.md) |
| 05 | [05-docs-defaults-changelog.md](05-docs-defaults-changelog.md) — Unreleased-черновик |
| 06 | [06-acceptance-smoke.md](06-acceptance-smoke.md) |
| 07 | [07-release-docs-changelog-promo.md](07-release-docs-changelog-promo.md) — версия + CHANGELOG cut + promo PNG |

Не пропускать этап **04** без замены `ExecStart`. Не пропускать этап **07** (docs/версия/`05-whats-new.png`).

---

## Риски

| Риск | Митигация |
|------|-----------|
| HTTP + дефолт `admin/admin` в интернет | Post-install warn; IP-whitelist в UI |
| Пользователи ждут сразу `https://домен` | Summary/README + баннер |
| Сломаются гайды/CI на easy / LE / SERVER_ADDRESS | Поиск по репо; env-override |
| DDNS без HTTPS сбивает с толку | «только DNS; HTTPS — в панели» |
| Неверный авто-IP (несколько NIC / NAT) | Показать IP в summary; CORS с localhost всегда; UI publish поправит DOMAIN/CORS |
| Слишком узкий CORS без ручного адреса | Включить detected IP; при публикации UI — полный origin |
| Homelab с нодами только по LAN | Документировать: `ALLOW_INTERNAL_NODES=true` в `.env` + restart |
| Пользователь ждёт, что install «настроит firewall» | Docs: порты вручную / у хостера; publish-режим может открыть нужное сам |
| Сломать выбор Python на Ubuntu/Debian | Не трогать `_ap_python_auto_minor_order`; после правок проверять `ap_python_candidate_versions` |

---

## Вне скоупа этого плана

- Переписывание мастера публикации в UI
- Обязательный force-HTTPS на первом входе
- Смена дефолтного порта 8000
- (Опционально вынести этап 4 «удаление start.sh» в отдельный PR, если install-упрощение нужно раньше)

---

## Быстрый чеклист файлов (ориентир)

```
install.sh
scripts/install-wizard.sh
scripts/install-ui.sh
install-easy.sh                    # DELETE
scripts/install-easy-wizard.sh     # DELETE
start.sh                           # DELETE (после rewrite systemd)
start_node_agent.sh                # DELETE (после rewrite systemd)
systemd/adminpanelaz.service       # ExecStart → uvicorn напрямую
systemd/adminpanelaz-node.service  # ExecStart → python agent напрямую
README.md                              # badge + «Текущая версия» на релизе
docs/nastrojki/set-i-publikaciya.md
docs/README.md
docs/PROJECT_MAP.md
docs/**                                 # полный проход инструкций на этапе 07
CHANGELOG.md                            # Unreleased → [X.Y.Z] на этапе 07
frontend/package.json                   # version bump на этапе 07
docs/assets/telegram-promo/05-whats-new.png  # перегенерировать на этапе 07
scripts/nginx-setup.sh / nginx-repair.sh / adminpanel-menu.sh
backend/app/services/panel_publish_info.py  # panel_restart_command
scripts/python-runtime.sh             # НЕ ломать: Ubuntu 3.12 / Debian 3.13
scripts/env_defaults.sh               # FEATURE_TELEGRAM_ENABLED=true
scripts/seed-wizard-db.py             # меньше использования из install / или только backup defaults
```

---

## Релиз после приёмки (этап 07)

После зелёного smoke:

1. Пройти **все** пользовательские инструкции и README под новый install.
2. Вырезать версию в `CHANGELOG.md` (обычно следующий minor, напр. **2.19.0**).
3. Синхронизировать версию: README badge, «Текущая версия», `frontend/package.json`.
4. Обновить promo: [`docs/assets/telegram-promo/05-whats-new.png`](../../assets/telegram-promo/05-whats-new.png) — версия + 3–4 пункта релиза (HTTP-default, один install.sh, HTTPS в UI, Python 3.12/3.13).
5. Статус этого плана → «реализовано».

Подробный промпт: [07-release-docs-changelog-promo.md](07-release-docs-changelog-promo.md). Git tag / `gh release` — только по явной просьбе.

---

[← К оглавлению docs](../../README.md) · [PROMPTS.md](PROMPTS.md) · [00](00-inventory.md) → [07](07-release-docs-changelog-promo.md)
