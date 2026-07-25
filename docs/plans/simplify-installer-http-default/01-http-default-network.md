# 01 — HTTP-default + упрощение «Сеть»

**Порядок:** после [00-inventory.md](00-inventory.md).  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Репозиторий AdminPanelAZ. План: `docs/plans/simplify-installer-http-default/README.md`.
>
> **Цель:** один `install.sh` без easy; интерактивно не спрашивать HTTPS/публикацию, APP_ENV, systemd/daemon, workers, mTLS, resource profile, optional (Telegram/бэкап), firewall, внешний IP, internal nodes. Дефолт: `http_direct`, `0.0.0.0`, `APP_ENV=production`, systemd, workers=1, profile `full`, `ALLOW_INTERNAL_NODES=false`, `FEATURE_TELEGRAM_ENABLED=true`. HTTPS/домен — только UI.
>
> **Python runtime (не ломать):** `scripts/python-runtime.sh` — **Ubuntu 24.04 → Python 3.12**, **Debian 13 / прочие → Python 3.13**.

---

## Промпт (копировать в Agent)

```
Реализуй этап 01 по docs/plans/simplify-installer-http-default/README.md
и docs/plans/simplify-installer-http-default/01-http-default-network.md.

Контекст Python: не ломай scripts/python-runtime.sh (Ubuntu 24.04 → 3.12, Debian → 3.13).

Сделай:

1. Вместо wizard_ask_https — apply дефолта публикации:
   - WIZ_NGINX_MODE=http_direct
   - WIZ_BACKEND_HOST=0.0.0.0
   - WIZ_BEHIND_NGINX=false
   - не задавать DOMAIN/HTTPS/SSL/ACCESS_PATH из этого шага
   - WIZ_ACCEPT_DEFAULTS тоже http_direct (не localhost none)

2. wizard_ask_network:
   - убрать вопрос «Внешний IP или домен»
   - убрать вопрос ALLOW_INTERNAL_NODES → всегда false
   - убрать/переписать ui_info_box про 127.0.0.1 + Nginx «на шаге Публикация»
   - НЕ форсировать BACKEND_HOST=127.0.0.1
   - оставить порт backend (+ node port если нужен)

3. CORS / summary URL: автодетект IP (переиспользуй nginx_server_primary_ip или аналог) + localhost; при DDNS можно добавить FQDN.

4. Preflight портов: по умолчанию не требовать свободные 80/443 для controller без HTTPS-override.

5. Env-override: если WIZ_NGINX_MODE уже задан извне (CI) — можно уважать; интерактивно не спрашивать.

Проверки после правок:
- bash -n install.sh scripts/install-wizard.sh
- rg не должен находить интерактивный prompt SERVER_ADDRESS / «Способ публикации» в run path
- source scripts/python-runtime.sh && ap_python_candidate_versions | head -1  # на Ubuntu ожидаем 3.12, на Debian 3.13
```

---

## Чеклист

- [ ] Нет шага HTTPS / 8 вариантов публикации
- [ ] Нет «Внешний IP или домен» / internal nodes
- [ ] Дефолт `http_direct` + `0.0.0.0`
- [ ] Summary показывает `http://<IP>:<port>/`
- [ ] `bash -n` OK
- [ ] python-runtime не сломан

---

## Проверки

```bash
bash -n install.sh scripts/install-wizard.sh scripts/python-runtime.sh
# На машине разработки:
source scripts/python-runtime.sh && ap_python_candidate_versions
# Ubuntu 24.04: первая строка 3.12; Debian 13: 3.13
rg -n 'wizard_ask_https|Внешний IP или домен|ALLOW_INTERNAL_NODES' scripts/install-wizard.sh || true
```

---

## Дальше

→ [02-strip-wizard-steps.md](02-strip-wizard-steps.md)
