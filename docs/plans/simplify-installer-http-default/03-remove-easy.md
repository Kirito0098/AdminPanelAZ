# 03 — Удалить простой установщик (easy)

**Порядок:** после [02-strip-wizard-steps.md](02-strip-wizard-steps.md).  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Удалить `install-easy.sh` + easy-wizard; остаётся один путь `install.sh`.
>
> **Не трогать** systemd/`start.sh` в этом этапе ([04](04-systemd-delete-start-sh.md)).  
> **Python runtime:** Ubuntu 3.12 / Debian 3.13 — не ломать.

---

## Промпт (копировать в Agent)

```
Этап 03 плана simplify-installer-http-default.
Спека: docs/plans/simplify-installer-http-default/README.md
Промпт: docs/plans/simplify-installer-http-default/03-remove-easy.md

1. Удали install-easy.sh и scripts/install-easy-wizard.sh.
2. Убери --easy / source easy-wizard / меню «простой установщик» из install.sh и scripts/install-ui.sh.
3. Обнови все docs/README/PROJECT_MAP/ссылки: только install.sh (в т.ч. StatusOpenVPN «install → UI»).
4. Обнови CI shellcheck (.github/workflows/ci.yml) — убрать install-easy.sh.
5. Тесты scripts/test-install-*.sh — убрать/переписать кейсы easy и старые HTTPS-ветки мастера.

Не трогай systemd/start.sh в этом этапе (этап 04).
Сохрани python-runtime.

Проверки: rg install-easy по репо = пусто (кроме CHANGELOG истории); bash -n install.sh scripts/install-ui.sh.
```

---

## Чеклист

- [ ] Файлы easy удалены
- [ ] Нет `--easy` в help
- [ ] README быстрый старт → только `install.sh`
- [ ] CI/shellcheck обновлён
- [ ] `rg install-easy` только в архивных записях CHANGELOG (допустимо)

---

## Проверки

```bash
rg -n 'install-easy|--easy|install-easy-wizard' --glob '!CHANGELOG.md' || echo 'clean'
bash -n install.sh scripts/install-ui.sh
```

---

## Дальше

→ [04-systemd-delete-start-sh.md](04-systemd-delete-start-sh.md)  
(параллельно после 03 можно начать docs: [05-docs-defaults-changelog.md](05-docs-defaults-changelog.md))
