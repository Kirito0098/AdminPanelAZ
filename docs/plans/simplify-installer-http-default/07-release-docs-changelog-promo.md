# 07 — Релиз: docs, CHANGELOG, версия, telegram promo

**Порядок:** после зелёной приёмки [06-acceptance-smoke.md](06-acceptance-smoke.md).  
**Спека:** [README.md](README.md) · **Индекс:** [PROMPTS.md](PROMPTS.md)

---

## Общий контекст

> Финальный релизный этап плана. Релиз вырезан как **2.18.0** (см. badge/CHANGELOG).
>
> Обязательно:
> 1. Обновить **все** пользовательские инструкции и README.
> 2. Заполнить `CHANGELOG.md` и **вырезать версию** из Unreleased.
> 3. Проставить версию проекта в местах синхронизации.
> 4. Перегенерировать `docs/assets/telegram-promo/05-whats-new.png` под новый релиз.
>
> Python в docs: Ubuntu **3.12** / Debian **3.13**.

---

## Промпт (копировать в Agent)

```
Этап 07 плана simplify-installer-http-default — РЕЛИЗ.
Спека: docs/plans/simplify-installer-http-default/README.md
Промпт: docs/plans/simplify-installer-http-default/07-release-docs-changelog-promo.md

Предпосылка: этапы 01–06 зелёные (HTTP-default install, без easy, systemd без start.sh).

1) Документация — полный проход
- Пройди README.md (корень), docs/README.md, docs/** (особенно nastrojki/set-i-publikaciya,
  установка/быстрый старт, SECURITY.md, PROJECT_MAP если есть).
- Убери устаревшее: install-easy, шаг HTTPS в install, start.sh watchdog, «закрой 8000 только nginx»,
  вопросы APP_ENV / workers / firewall / mTLS в install.
- Зафиксируй новый UX: install → http://IP:port → HTTPS/домен в «Адрес сайта и HTTPS»;
  Python Ubuntu 3.12 / Debian 3.13 автоматически.
- Обнови любые скриншоты/описания мастера установки, если текст врёт.

2) CHANGELOG.md
- Перенеси накопленное из [Unreleased] в новую секцию ## [X.Y.Z] - YYYY-MM-DD
  (X.Y.Z = версия релиза; для этого плана — **2.18.0**; дата = день релиза).
- Заполни кратко (blockquote) + Changed/Removed/Added по факту упрощения install.
- Обнови навигацию сверху и compare-ссылки внизу ([Unreleased] → compare vX.Y.Z...HEAD).
- Очисти Unreleased до пустых заголовков секций (или оставь только то, что не вошло в релиз).

3) Версия проекта
Синхронизируй X.Y.Z везде, где сейчас стоит старая панель-версия:
- README.md: badge «Панель-X.Y.Z», блок «Текущая версия: панель X.Y.Z · node agent …» (node agent
  не бампить, если агент не менялся)
- frontend/package.json (+ package-lock.json version fields, если принято в репо)
- любые другие явные «2.18.0» / предыдущая версия панели в пользовательских docs (не архив CHANGELOG)

Не создавай git tag / gh release, пока пользователь явно не попросит.

4) Telegram promo — docs/assets/telegram-promo/05-whats-new.png
- Перегенерируй картинку инструментом GenerateImage (или эквивалент), сохранив стиль текущего файла:
  тёмный navy фон, cyan акценты, логотип AdminPanel AntiZapret, русский текст,
  layout «Последние обновления».
- Версия на баннере = X.Y.Z; дата = дата релиза.
- 3–4 главных пункта релиза про упрощение установщика, например:
  • HTTP по умолчанию — панель сразу по IP:port
  • Один install.sh — без easy и без выбора HTTPS при установке
  • HTTPS и домен — в настройках панели после установки
  • systemd напрямую / без start.sh (если вошло в релиз)
  • Python 3.12 (Ubuntu) / 3.13 (Debian) автоматически
- Обнови mockup «Обновления и изменения» и подзаголовок под эти темы.
- Перезапиши файл: docs/assets/telegram-promo/05-whats-new.png
- Проверь, что README ссылается на этот путь и секция «Последние обновления» не врёт про старую версию.

5) Статус плана
- docs/plans/simplify-installer-http-default/README.md → статус «реализовано» + версия релиза.

Проверки:
- rg по пользовательским docs: нет install-easy / start.sh watchdog (кроме CHANGELOG истории)
- Версия X.Y.Z совпадает в CHANGELOG header, README badge, frontend/package.json
- Файл 05-whats-new.png существует и визуально про новую версию (не 2.15.0 / не старые mobile-пункты)
```

---

## Чеклист

- [x] Все инструкции и README согласованы с HTTP-default / одним `install.sh` / HTTPS в UI
- [x] `CHANGELOG.md`: секция `[X.Y.Z]` заполнена; Unreleased очищен; compare-ссылки OK
- [x] Версия панели проставлена (README badge + «Текущая версия», `frontend/package.json`)
- [x] `docs/assets/telegram-promo/05-whats-new.png` обновлён под X.Y.Z и темы релиза
- [x] Статус плана → реализовано
- [x] Node agent версию не трогали без необходимости

---

## Проверки

```bash
# Подставь X.Y.Z фактически выданной версии:
VER=2.18.0   # пример
rg -n "Панель-${VER}|панель ${VER}|\"version\": \"${VER}\"" README.md frontend/package.json
rg -n "^## \[${VER}\]" CHANGELOG.md
test -f docs/assets/telegram-promo/05-whats-new.png
rg -n 'install-easy|start\.sh watchdog' README.md docs/ SECURITY.md --glob '!**/plans/**' || echo 'user docs clean'
# Визуально: открой 05-whats-new.png — версия и пункты = этот релиз, не 2.15.0 mobile
```

---

## Заметки по картинке

- Референс стиля: текущий `docs/assets/telegram-promo/05-whats-new.png` (тёмный dashboard, cyan).
- Не копировать контент v2.15.0 (mobile / HA Mini App) — только темы **этого** релиза.
- Соотношение сторон близко к текущему (широкий promo ~16:9 / banner).
- После генерации: `filename` = `05-whats-new.png`, положить/заменить в `docs/assets/telegram-promo/`.

---

## Готово

Релизный контент готов. Tag/`gh release` — отдельным запросом пользователя.
