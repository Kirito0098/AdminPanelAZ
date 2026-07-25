# 00 — Инвентаризация (только чтение)

**Порядок:** первый. Ничего не менять.  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Репозиторий AdminPanelAZ. План: `docs/plans/simplify-installer-http-default/README.md`.
>
> **Цель:** один `install.sh` без easy; интерактивно не спрашивать HTTPS/публикацию, APP_ENV, systemd/daemon, workers, mTLS, resource profile, optional (Telegram/бэкап), firewall, внешний IP, internal nodes. Дефолт: `http_direct`, `0.0.0.0`, `APP_ENV=production`, systemd, workers=1, profile `full`, `ALLOW_INTERNAL_NODES=false`, `FEATURE_TELEGRAM_ENABLED=true`. HTTPS/домен — только UI.
>
> **Python runtime (не ломать):** `scripts/python-runtime.sh` — **Ubuntu 24.04 → Python 3.12**, **Debian 13 / прочие → Python 3.13** (автопорядок в `_ap_python_auto_minor_order`). Любые правки install/start/systemd должны по-прежнему `source` этот скрипт / `ap_ensure_venv` / `ap_resolve_python`. Не хардкодить один minor для всех ОС.

---

## Промпт (копировать в Agent)

```
По docs/plans/simplify-installer-http-default/README.md сделай read-only обзор (ничего не меняй):

1. Перечисли все вызовы wizard_ask_* в scripts/install-wizard.sh и run_install_wizard.
2. Где WIZ_NGINX_MODE / SERVER_ADDRESS / ALLOW_INTERNAL_NODES / APP_ENV / RUN_MODE / UVICORN_WORKERS / MTLS / RESOURCE_PROFILE / TELEGRAM / FIREWALL пишутся в .env (install.sh).
3. Все ссылки на install-easy.sh / install-easy-wizard.sh / --easy.
4. Все использования start.sh и start_node_agent.sh (systemd, install, nginx-*, menu, panel_restart_command, diagnostics, CI).
5. Подтверди, что scripts/python-runtime.sh: Ubuntu 24.04 → 3.12 first, Debian → 3.13 first.

Верни краткий отчёт: что трогать в этапах 01–05, риски регрессии.
```

---

## Чеклист

- [ ] Список шагов мастера актуален
- [ ] Список зависимостей start.sh полный
- [ ] Python-runtime порядок ОС зафиксирован в отчёте

---

## Дальше

→ [01-http-default-network.md](01-http-default-network.md)
