# 02 — Вырезать APP_ENV, services, security, profile, optional, firewall

**Порядок:** после [01-http-default-network.md](01-http-default-network.md).  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Репозиторий AdminPanelAZ. План: `docs/plans/simplify-installer-http-default/README.md`.
>
> Дефолты вместо вопросов: `APP_ENV=production`, systemd, `UVICORN_WORKERS=1`, mTLS off, rotation 0, profile `full`, без optional/firewall.
>
> **Python runtime (не ломать):** Ubuntu 24.04 → **3.12**, Debian 13 → **3.13**.  
> **Не удалять** `start.sh` в этом этапе (это [04](04-systemd-delete-start-sh.md)).

---

## Промпт (копировать в Agent)

```
Продолжи план simplify-installer-http-default (этап 02).
Спека: docs/plans/simplify-installer-http-default/README.md
Промпт: docs/plans/simplify-installer-http-default/02-strip-wizard-steps.md

Убери из интерактивного мастера (дефолты вместо вопросов):

1. wizard_ask_app_env → всегда WIZ_APP_ENV=production
2. wizard_ask_services → всегда WIZ_RUN_MODE=systemd, WIZ_UVICORN_WORKERS=1 (без manual/daemon/workers prompt)
3. wizard_ask_security_hardening → пропуск; MTLS=false, ROTATION_DAYS=0 (без Redis-вопроса — workers=1)
4. wizard_ask_resource_profile → всегда full + apply-resource-profile
5. wizard_ask_optional → удалить вызов; не сеять Telegram token из install
6. wizard_ask_firewall → не вызывать; WIZ_CONFIGURE_FIREWALL=false

Обнови run_install_wizard порядок шагов и summary (убрать устаревшие строки).
Сохрани: тип установки, AntiZapret, сеть (порты), DDNS, admin, node agent (если нужен), paths (BACKUP_ROOT/state).

Не удаляй start.sh в этом этапе.
Не ломай python-runtime (Ubuntu 3.12 / Debian 3.13).

Проверки: bash -n; rg по удалённым промптам; убедись что WITH_SYSTEMD=true после wizard_apply_run_mode_flags.
```

---

## Чеклист

- [ ] Нет выбора production/development
- [ ] Нет вручную/daemon/systemd и workers
- [ ] Нет mTLS / ротации / optional Telegram-CIDR / firewall
- [ ] Всегда full profile
- [ ] DDNS / admin / тип установки на месте
- [ ] `bash -n` OK

---

## Проверки

```bash
bash -n install.sh scripts/install-wizard.sh
rg -n 'wizard_ask_app_env|wizard_ask_services|wizard_ask_security_hardening|wizard_ask_resource_profile|wizard_ask_optional|wizard_ask_firewall' scripts/install-wizard.sh
# Ожидание: либо нет вызовов из run_install_wizard, либо функции стали no-op apply-defaults
```

---

## Дальше

→ [03-remove-easy.md](03-remove-easy.md)
