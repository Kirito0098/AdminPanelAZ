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

- [x] Список шагов мастера актуален
- [x] Список зависимостей start.sh полный
- [x] Python-runtime порядок ОС зафиксирован в отчёте

## Отчёт (2026-07-26)

Собрал [Installer inventory](2ceeb7d2-faab-47f0-b714-73cf9fc18a4a). Кратко:

1. **Мастер:** 14 `wizard_ask_*` в `run_install_wizard` (+ вложенные access_path/subpath из HTTPS).
2. **`.env`:** `ALLOW_INTERNAL_NODES`/`APP_ENV`/`FEATURE_*` через `apply_wiz_env_settings`; `SERVER_ADDRESS` → только CORS; `RUN_MODE` → флаги systemd/daemon; firewall не в `.env`; Telegram token → БД; `FEATURE_TELEGRAM_ENABLED` сейчас `false` в `env_defaults.sh`.
3. **easy:** `install-easy.sh`, `install-easy-wizard.sh`, `--easy` в install/ui, README/docs, CI shellcheck.
4. **start.sh:** systemd units, install bootstrap/daemon/next_steps, nginx-*, menu, `panel_restart_command`, diagnostics, CI, update/backup/uninstall/UI.
5. **Python:** Ubuntu 24.04 → 3.12 first; Debian/прочие → 3.13 first (`_ap_python_auto_minor_order`).

Риски: HTTP+admin в интернет; удаление start.sh без unit/restart; `http_direct` без `PUBLISH_MODE` в install; смена `WIZ_ACCEPT_DEFAULTS` с `none` на `http_direct`.

---

## Дальше

→ [01-http-default-network.md](01-http-default-network.md)
