# 05 — Docs, env defaults, CHANGELOG (черновик Unreleased)

**Порядок:** после [03-remove-easy.md](03-remove-easy.md); можно частично параллелить с [04](04-systemd-delete-start-sh.md).  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Документация и дефолты под новый install. Упомянуть Python: Ubuntu **3.12** / Debian **3.13**.  
> Не регрессировать этапы 01–04.
>
> **Важно:** здесь только правка docs + запись в **`[Unreleased]`**.  
> Вырезка версии, badge, `package.json` и обновление `05-whats-new.png` — этап **[07](07-release-docs-changelog-promo.md)** после приёмки.

---

## Промпт (копировать в Agent)

```
Этап 05 плана simplify-installer-http-default.
Спека: docs/plans/simplify-installer-http-default/README.md
Промпт: docs/plans/simplify-installer-http-default/05-docs-defaults-changelog.md

1. README: один быстрый старт install.sh; HTTP по IP:port; HTTPS в «Адрес сайта и HTTPS».
2. docs/nastrojki/set-i-publikaciya.md — StatusOpenVPN только через UI после install.
3. SECURITY.md / docs: порты при http_direct; НЕ закрывать порт панели до перехода на nginx; firewall вручную.
4. Документируй вручную:
   - UVICORN_WORKERS>1 + Redis + systemctl restart
   - ALLOW_INTERNAL_NODES=true для LAN-нод
   - mTLS per-node в UI; NODE_API_KEY_ROTATION_DAYS
   - resource profile / модули в UI
   - Telegram token в UI (модуль включён)
5. scripts/env_defaults.sh: FEATURE_TELEGRAM_ENABLED=true (было false).
6. Автобэкап: зафиксируй дефолт (вкл 7 дней без вопроса ИЛИ только UI) — одно поведение, опиши в docs.
7. CHANGELOG [Unreleased]: Changed/Removed по факту (ещё НЕ вырезай версию — это этап 07).
8. Обнови статус в docs/plans/simplify-installer-http-default/README.md → «в работе».
9. Упомяни в docs: Python Ubuntu 3.12 / Debian 3.13 автоматически через python-runtime.sh.

Не регрессируй этапы 01–04.
Не бампь frontend/package.json и не трогай 05-whats-new.png в этом этапе.
```

---

## Чеклист

- [x] Нет ссылок на easy в пользовательских docs (кроме истории CHANGELOG)
- [x] FEATURE_TELEGRAM_ENABLED=true в defaults
- [x] Инструкции: workers, mTLS, firewall/ports, Telegram UI, Python 3.12/3.13
- [x] CHANGELOG **Unreleased** заполнен (версия ещё не вырезана)
- [x] Статус плана → «в работе»

---

## Проверки

```bash
rg -n 'FEATURE_TELEGRAM_ENABLED' scripts/env_defaults.sh
rg -n 'install-easy|start\.sh watchdog' README.md docs/nastrojki SECURITY.md || echo 'clean user docs'
rg -n '3\.12|3\.13|python-runtime' README.md docs/ SECURITY.md docs/plans/simplify-installer-http-default/
rg -n 'Unreleased|Removed|Changed' CHANGELOG.md | head -40
```

---

## Дальше

→ [06-acceptance-smoke.md](06-acceptance-smoke.md)  
→ затем релиз: [07-release-docs-changelog-promo.md](07-release-docs-changelog-promo.md)
