# PROMPTS: упрощение установщика (HTTP default, без easy, systemd-only)

Копируй промпт из файла этапа целиком в Agent mode. Спека и решения: [README.md](README.md).

## Общий контекст (общий для всех этапов)

> Репозиторий AdminPanelAZ. План: `docs/plans/simplify-installer-http-default/README.md`.
>
> **Цель:** один `install.sh` без easy; интерактивно не спрашивать HTTPS/публикацию, APP_ENV, systemd/daemon, workers, mTLS, resource profile, optional (Telegram/бэкап), firewall, внешний IP, internal nodes. Дефолт: `http_direct`, `0.0.0.0`, `APP_ENV=production`, systemd, workers=1, profile `full`, `ALLOW_INTERNAL_NODES=false`, `FEATURE_TELEGRAM_ENABLED=true`. HTTPS/домен — только UI.
>
> **Python runtime (не ломать):** `scripts/python-runtime.sh` — **Ubuntu 24.04 → Python 3.12**, **Debian 13 / прочие → Python 3.13** (автопорядок в `_ap_python_auto_minor_order`). Любые правки install/start/systemd должны по-прежнему `source` этот скрипт / `ap_ensure_venv` / `ap_resolve_python`. Не хардкодить один minor для всех ОС.

После **каждого** этапа 01–05: чеклист этапа + `bash -n` на затронутых `.sh` + не регрессировать Python 3.12/3.13.  
После **06** — обязательный релизный этап **07** (docs + CHANGELOG + версия + `05-whats-new.png`).

---

## Порядок выполнения

| # | Этап | Файл |
|---|------|------|
| 00 | Инвентаризация (read-only) | [00-inventory.md](00-inventory.md) |
| 01 | Мастер: HTTP-default + сеть | [01-http-default-network.md](01-http-default-network.md) |
| 02 | Мастер: вырезать остальные лишние шаги | [02-strip-wizard-steps.md](02-strip-wizard-steps.md) |
| 03 | Удалить easy-установщик | [03-remove-easy.md](03-remove-easy.md) |
| 04 | Systemd прямой ExecStart → удалить start.sh | [04-systemd-delete-start-sh.md](04-systemd-delete-start-sh.md) |
| 05 | Docs + Unreleased (черновик) | [05-docs-defaults-changelog.md](05-docs-defaults-changelog.md) |
| 06 | Финальная проверка / smoke | [06-acceptance-smoke.md](06-acceptance-smoke.md) |
| 07 | **Релиз:** все README/инструкции, CHANGELOG cut, версия, `05-whats-new.png` | [07-release-docs-changelog-promo.md](07-release-docs-changelog-promo.md) |

---

## Зависимости между этапами

```text
00 (обзор)
 └─► 01 (HTTP + сеть)
      └─► 02 (остальные шаги мастера)
           └─► 03 (delete easy) ──┬─► 04 (systemd / delete start.sh)
                                 └─► 05 (docs Unreleased) ──► можно параллелить с 04 после 03
                                      └─► 06 (приёмка)
                                           └─► 07 (релиз: версия + CHANGELOG + promo PNG)
```

Этап **04** самый рискованный (systemd). **07** только после зелёного **06**. Не пропускать **04** без замены `ExecStart`. Не пропускать **07** — без него README/версия/promo останутся на старом релизе.

---

[← README плана](README.md) · [К оглавлению docs](../../README.md)
