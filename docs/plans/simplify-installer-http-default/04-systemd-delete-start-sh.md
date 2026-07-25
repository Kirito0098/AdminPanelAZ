# 04 — Systemd прямой запуск + удаление start.sh / start_node_agent.sh

**Порядок:** после [03-remove-easy.md](03-remove-easy.md). **Самый рискованный этап.**  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Сейчас unit’ы вызывают `start.sh` / `start_node_agent.sh`. Удалять скрипты **нельзя**, пока `ExecStart` не переведён на прямой uvicorn/agent.
>
> **Python:** venv создаётся install’ом через `ap_ensure_venv` — Ubuntu **3.12**, Debian **3.13**. `ExecStart` = путь к уже созданному `backend/.venv/bin/uvicorn`.

---

## Промпт (копировать в Agent)

```
Этап 04 плана simplify-installer-http-default — КРИТИЧНО.
Спека: docs/plans/simplify-installer-http-default/README.md
Промпт: docs/plans/simplify-installer-http-default/04-systemd-delete-start-sh.md

Сейчас:
  systemd/adminpanelaz.service → ExecStart=.../start.sh watchdog prod
  systemd/adminpanelaz-node.service → ExecStart=.../start_node_agent.sh watchdog prod

Сделай:

1. Перепиши unit’ы на прямой запуск через venv:
   - panel: backend/.venv/bin/uvicorn app.main:app --host/--port из EnvironmentFile; учти USE_HTTPS/SSL_CERT/SSL_KEY если нужны флаги (как в start.sh uvicorn_ssl_flags)
   - node: тот же способ, что использовал start_node_agent.sh для prod uvicorn node_agent
   - Restart=on-failure уже есть — bash-watchdog не нужен
   - WorkingDirectory / EnvironmentFile сохранить; хост/порт согласовать с http_direct (0.0.0.0) и .env

2. Python: unit или ExecStartPre/wrapper должен использовать тот же выбор, что python-runtime
   (Ubuntu 3.12 / Debian 3.13) — venv уже создан install’ом через ap_ensure_venv; ExecStart = путь к venv/bin/uvicorn.

3. Замени все fallback’и ./start.sh restart → systemctl restart adminpanelaz
   (nginx-setup, nginx-repair, panel_restart_command, adminpanel-menu, background_tasks, diagnostics, install post-install texts).

4. Удали start.sh и start_node_agent.sh.

5. Bootstrap-проверка «репо целое» в install.sh — без требования start.sh (requirements + systemd units).

6. CI shellcheck — убрать start.sh / start_node_agent.sh.

7. Обнови python-runtime.sh комментарий (больше не «для start.sh»).

Проверки:
- bash -n оставшихся scripts
- systemctl cat логика: unit файлы валидны синтаксически
- rg 'start\.sh|start_node_agent' --glob '!CHANGELOG.md' должен быть чист или только docs/history
- Не сломать ap_ensure_venv / Ubuntu 3.12 / Debian 3.13
```

---

## Чеклист

- [ ] Unit’ы не ссылаются на start.sh
- [ ] `start.sh` / `start_node_agent.sh` удалены
- [ ] Restart/status через systemctl везде в коде продукта
- [ ] panel_restart_command → systemctl
- [ ] CI обновлён
- [ ] python-runtime сохранён

---

## Проверки

```bash
rg -n 'start\.sh|start_node_agent\.sh' --glob '!CHANGELOG.md' --glob '!docs/plans/**' || echo 'clean'
bash -n install.sh scripts/*.sh
# синтаксис unit (если systemd-analyze доступен):
systemd-analyze verify systemd/adminpanelaz.service systemd/adminpanelaz-node.service 2>/dev/null || true
source scripts/python-runtime.sh && ap_python_candidate_versions
```

---

## Дальше

→ [05-docs-defaults-changelog.md](05-docs-defaults-changelog.md) (если ещё не сделан)  
→ затем [06-acceptance-smoke.md](06-acceptance-smoke.md)
