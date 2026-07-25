# 06 — Финальная приёмка / smoke

**Порядок:** после [01](01-http-default-network.md)–[05](05-docs-defaults-changelog.md) зелёные.  
**Спека:** [README.md](README.md) (§ Критерии приёмки) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Полная приёмка плана (код + docs-черновик). Python: Ubuntu **3.12** / Debian **3.13**.  
> Исправить хвосты минимально.  
> **После зелёного smoke** → этап релиза [07](07-release-docs-changelog-promo.md): версия, полный CHANGELOG cut, все README, `05-whats-new.png`.

---

## Промпт (копировать в Agent)

```
По чеклисту приёмки docs/plans/simplify-installer-http-default/README.md (§ Критерии приёмки)
и docs/plans/simplify-installer-http-default/06-acceptance-smoke.md
проверь репозиторий и исправь хвосты:

1. Статический rg: нет easy, нет интерактивных удалённых шагов, нет start.sh в runtime-путях.
2. bash -n все ключевые sh; shellcheck CI список актуален.
3. Backend pytest (хотя бы test_panel_publish_info + smoke import app).
4. Подтверди python-runtime: Ubuntu→3.12, Debian→3.13 в коде _ap_python_auto_minor_order.
5. Составь короткий smoke-сценарий для ручного прогона на VPS (ниже) — не обязательно выполнять, но вставь в план/README как «ручная проверка».

Если найдёшь регрессии — исправь минимально.
Версию / badge / 05-whats-new.png не трогай — это этап 07.
```

---

## Чеклист (приёмка)

- [ ] Нет `install-easy*` / `--easy`
- [ ] Нет шагов: HTTPS-выбор, SERVER_ADDRESS, internal nodes, APP_ENV, run mode, workers, mTLS, profile, optional, firewall
- [ ] Дефолт http_direct / 0.0.0.0 / production / systemd / workers=1 / full / Telegram feature on
- [ ] Нет `start.sh` / `start_node_agent.sh`; unit’ы прямые
- [ ] Docs-черновик OK (HTTPS UI, workers, Telegram, firewall, Python 3.12/3.13); Unreleased есть
- [ ] `bash -n` + релевантные тесты зелёные

---

## Ручной smoke (VPS)

```text
1. Ubuntu 24.04: sudo ./install.sh → в venv python 3.12; панель http://IP:8000/; systemctl status adminpanelaz
2. Debian 13 (если есть): то же → python 3.13
3. Логин admin → Настройки → Адрес сайта и HTTPS → nginx_le или uvicorn_le → сайт открывается
4. Telegram в меню доступен без «включить модуль»; token задаётся в UI
5. systemctl restart adminpanelaz работает; start.sh отсутствует
```

---

## Автопроверки

```bash
bash -n install.sh scripts/install-wizard.sh scripts/python-runtime.sh scripts/install-ui.sh
rg -n 'install-easy|start\.sh|start_node_agent' --glob '!CHANGELOG.md' --glob '!docs/plans/**' || echo 'clean'
source scripts/python-runtime.sh && ap_python_candidate_versions
cd backend && .venv/bin/python -c 'from app.main import app; print(len(app.routes))'
cd backend && .venv/bin/python -m pytest tests/test_panel_publish_info.py -q
```

---

## Дальше

→ [07-release-docs-changelog-promo.md](07-release-docs-changelog-promo.md) — версия, CHANGELOG cut, все инструкции, `05-whats-new.png`
