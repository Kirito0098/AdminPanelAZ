# Участие в разработке AdminPanelAZ

Гайд для тех, кто помогает с панелью в **Cursor**: какие MCP и skills использует мейнтейнер, **зачем** каждый из них, и договорённости по коду.

Пользовательские инструкции (для админов VPN): [`docs/README.md`](docs/README.md).  
Карта кода: [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).  
Безопасность: [`SECURITY.md`](SECURITY.md).

---

## Agent starter pack (уже в git)

После клона в репо уже есть curated pack для Cursor:

| Путь | Что |
|------|-----|
| `.cursor/rules/` | `use-skills`, `lean-code`, `release-train-branching`, … |
| `.cursor/skills/` | project skills: `tdd`, `ponytail-review`, React/Vercel UI, `webapp-testing`, `tui-design`, … |
| `.cursor/mcp.json.example` | шаблон MCP **без** секретов |
| `.agents/AGENTS.md` | краткая карта; skills — symlink на `.cursor/skills/` |

**Не в git (локально):** `.cursor/mcp.json`, `.cursor/settings.json`, `.codebase-memory/`, `docs/superpowers/`, тяжёлый **impeccable** (если поставите сами).

```bash
cp .cursor/mcp.json.example .cursor/mcp.json   # поправить пути команд под свою машину
# Marketplace: Plugins → superpowers, pstack; затем /setup-pstack
```

Чужие токены и личный `mcp.json` в PR не класть.

### Промпт для ИИ после клона (вставить в Agent)

Обычно достаточно открыть проект в Cursor и **вставить блок ниже одним сообщением** — агент сам поставит плагины, MCP и опциональные skills по этому гайду.

```text
Настрой эту машину для разработки AdminPanelAZ с Cursor Agent.

Сначала прочитай CONTRIBUTING.md и .cursor/rules/use-skills.mdc — не выдумывай шаги мимо них.

Сделай по порядку и в конце дай чеклист «готово / нужно подтверждение / не вышло»:

1) Убедись, что в репо уже есть starter pack: .cursor/rules/, .cursor/skills/, .agents/AGENTS.md, .cursor/mcp.json.example. Если чего-то нет — скажи.

2) Плагины Cursor Marketplace (если ещё нет): установи superpowers и pstack (tool install_plugin или скажи мне нажать Install в UI). Не ставь obra/superpowers второй раз через npx skills — будет дубль.

3) MCP локально: если нет .cursor/mcp.json — скопируй из .cursor/mcp.json.example. Подставь рабочие команды под ЭТУ ОС (which / path): codebase-memory-mcp, uvx+siteaudit, github-mcp-stdio или hosted GitHub MCP. Секреты и токены в файл не пиши; для GitHub рассчитай на `gh auth login` / `gh auth token`. .cursor/mcp.json в git не коммить.

4) Опциональные skills (поставь, если меня не против; можно спросить одним вопросом):
   - npx skills add coreyhaines31/marketingskills@site-architecture -g -a cursor -y
   - cyber-skills точечно НЕ ставь все ~800; достаточно review-security из Cursor + при security-работе команды из CONTRIBUTING.
   - impeccable не ставь по умолчанию (тяжёлый, в pack его нет).

5) Напомни мне один раз вручную: в чате выполнить /setup-pstack (выбор моделей pstack).

6) Кратко объясни вилку: фичи → Superpowers brainstorm/plan; баги → systematic-debugging + project tdd; rigor/PR → /poteto-mode. Project tdd = .cursor/skills/tdd, не плагинный дубль.

Не трогай .env, не коммить секреты, не пушь. Код панели не рефакторь — только tooling.
```

После этого один раз вручную: **`/setup-pstack`**. Если агент попросит подтвердить Install плагина — нажми Approve.

---

## MCP — зачем каждый

MCP даёт агенту доступ к внешним сервисам и индексам. Без них остаётся только чтение файлов и shell.

### codebase-memory

**Зачем:** AdminPanelAZ большой (~десятки роутеров, сотни сервисов). Обычный `grep` часто не видит связи «роут → сервис → адаптер узла».

**Что делает:** держит граф символов (функции, классы, вызовы, HTTP-роуты, импорты). Агент ищет по графу, смотрит архитектуру, пути между сущностями.

**Когда:** навигация по незнакомому коду; после крупных рефакторингов / удаления модулей — переиндексация («Обнови граф» / `index_repository`), иначе граф ссылается на удалённые файлы.

### github

**Зачем:** PR, Issues, GitHub Actions и комментарии из чата без ручного копирования URL.

**Что делает:** официальный GitHub MCP (у мейнтейнера — stdio + `gh auth token`; на обычной машине можно hosted URL + PAT).

**Когда:** открыть/посмотреть PR, статус CI, triage комментариев вместе со skills `babysit` / `review-*`.

**Замечание (Cursor Remote/SSH):** `${env:GITHUB_PERSONAL_ACCESS_TOKEN}` из `~/.bashrc` часто **не** виден extension host → пустой Bearer и ошибка вроде `SSE ... 400`. Надёжнее обёртка, которая сама вызывает `gh auth token`, либо PAT в локальном (не коммитимом) конфиге.

### context7

**Зачем:** не гадать API FastAPI / React / Recharts / webauthn / redis по устаревшей «памяти» модели.

**Что делает:** подтягивает актуальную документацию библиотек по запросу.

**Когда:** пишете или правите интеграцию с внешней библиотекой, миграции API, нестандартные опции.

### siteaudit

**Зачем:** быстро проверить, что **публичная** панель отдаёт нормальные security-заголовки после публикации HTTPS / смены nginx.

**Что делает:** audit URL (HTTPS, HSTS, CSP, cookies, SSL). SEO/competitor-функции для этого продукта не нужны.

**Когда:** после `Настройки → Адрес сайта и HTTPS`, смены CSP/HSTS, перед релизом на домен.

### cursor-ide-browser (встроенный)

**Зачем:** UI панели нельзя надёжно проверить только по коду (логин, 2FA, NOC, Mini App, мастера настроек).

**Что делает:** открывает страницу, клики, ввод, снимки DOM/экрана.

**Когда:** регрессии UI, проверка копирайта/флоу после правок фронта.

### cursor-app-control (встроенный)

**Зачем:** служебные действия самого Cursor (корень workspace, диалоги, открытие ресурсов/автоматизаций). Для продуктового кода панели почти не нужен — просто есть в среде.

---

### Пример локального `mcp.json`

Подставьте свои пути. **Секреты в git не класть.**

```json
{
  "mcpServers": {
    "codebase-memory-mcp": {
      "command": "codebase-memory-mcp"
    },
    "siteaudit": {
      "command": "uvx",
      "args": ["--from", "siteaudit-mcp", "siteaudit"]
    },
    "github": {
      "command": "github-mcp-stdio"
    },
    "context7": {
      "url": "https://mcp.context7.com/mcp/oauth"
    }
  }
}
```

Альтернатива GitHub (hosted), если Cursor видит env:

```json
"github": {
  "url": "https://api.githubcopilot.com/mcp/",
  "headers": {
    "Authorization": "Bearer ${env:GITHUB_PERSONAL_ACCESS_TOKEN}"
  }
}
```

```bash
gh auth login
# Context7: Settings → MCP → context7 → OAuth
```

После правок: Reload Window, зелёные точки в **Settings → MCP**.

---

## Skills Cursor (встроенные) — зачем каждый

Это playbooks самого Cursor (`~/.cursor/skills-cursor/`). Агент читает skill и следует процессу.

| Skill | Зачем используется |
|-------|--------------------|
| **review-security** | Security-ревью **диффа** ветки: auth, 2FA/passkey, CSP, rate limit, whitelist, публичная раздача конфигов, node agent, webhook Telegram. Перед merge чувствительных изменений. |
| **review-bugbot** | Автоматический bug-oriented review диффа (логика, регрессии), отдельно от security. |
| **review** | Выбор между Bugbot и Security, если нужен один из двух. |
| **babysit** | Довести открытый PR до merge-ready: конфликты, комментарии, красный CI в цикле (нужен `gh` / github MCP). |
| **canvas** | Отдать результат анализа **визуально** (архитектура, метрики, таблицы) рядом с чатом, а не простынёй markdown. |
| **split-to-prs** | Большая ветка/чат → несколько маленьких reviewable PR без потери работы. |
| **shell** (`/shell`) | Выполнить команду **буквально** (install/systemd/firewall), без «улучшений» агентом. |
| **create-rule** | Новые always-on правила в `.cursor/rules/` (pack уже в git). |
| **create-hook** | Хуки на события агента (например напоминание обновить docs после правок UI). |
| **automate** | Создать **Cursor Automation** (расписание/триггеры в Cursor), не GitHub Actions репо. |
| **loop** | Повторять проверку по интервалу (`/loop 5m …`) — удобно для CI/smoke. |

Обычно **не** нужны для работы над панелью: `sdk`, `statusline`, `update-cli-config`, `update-cursor-settings`, `onboard`, `migrate-to-builds`, `create-subagent`, `create-skill` (мета-инструменты Cursor/IDE).

---

## Superpowers ([obra/superpowers](https://github.com/obra/superpowers)) — зачем каждый

**Что это:** методология *как вести разработку с агентом* (не security-библиотека). ~14 skills. Ставится глобально, не в git репо — **плагином Cursor** `superpowers` из Marketplace (**Settings → Plugins**). Плагин обновляется вместе с Cursor и кладёт skills в `~/.cursor/plugins/cache/…`.

Если плагин уже стоит, **не** ставьте пакет ещё и через `npx skills add obra/superpowers`: каждый skill окажется в списке агента дважды, и он хуже выбирает нужный. Остался старый дубль в `~/.agents/skills/` — удалите его:

```bash
npx skills remove -g -y brainstorming dispatching-parallel-agents executing-plans \
  finishing-a-development-branch receiving-code-review requesting-code-review \
  subagent-driven-development systematic-debugging test-driven-development \
  using-git-worktrees using-superpowers verification-before-completion \
  writing-plans writing-skills
```

Без плагина (другой агент, не Cursor) — `npx skills add obra/superpowers -g -a cursor -s '*' -y`, но только один из двух способов.

**Зачем пакет в целом:** чтобы агент не прыгал сразу в код, а проходил цикл: понять задачу → дизайн → план → TDD → ревью → доказательства → закрытие ветки. Для крупных фич AdminPanelAZ (HA, HTTPS, Telegram, multi-node) это снижает «сломали соседний модуль».

| Skill | Зачем |
|-------|--------|
| **using-superpowers** | Точка входа: сначала проверить, какой skill подходит, и вызвать его до действий. Без этого остальные Superpowers skills часто игнорируются. |
| **brainstorming** | До кода: уточнить цель, ограничения, 2–3 подхода, получить апрув дизайна. Нужен, чтобы не начать пилить не ту фичу. |
| **writing-plans** | Разбить одобренный дизайн на мелкие задачи с путями файлов и шагами проверки — план для «младшего инженера без контекста». |
| **executing-plans** | Выполнить уже написанный план в сессии с checkpoint’ами и отчётом. |
| **subagent-driven-development** | Гнать план через свежих субагентов на задачу + ревью соответствия спеке и качества кода; держать координацию в основном чате. |
| **test-driven-development** | RED → GREEN → REFACTOR: сначала падающий тест, потом минимальный код. Для панели — особенно backend (pytest) и критичная логика лимитов/auth. |
| **systematic-debugging** | Баг/красный тест: сначала root cause, не «подкрутить симптом». Полезно на гонках узлов, nginx/HTTPS, sync. |
| **verification-before-completion** | Запрет говорить «готово» без реальных команд проверки (ruff, тесты, health). Совпадает с духом CI проекта. |
| **requesting-code-review** | Между задачами/перед merge: структурированный запрос ревью по плану и критериям. |
| **receiving-code-review** | Разбор чужого ревью: проверять замечания по существу, не соглашаться вслепую и не игнорировать валидное. |
| **dispatching-parallel-agents** | Независимые куски работы (например фронт-копирайт и backend-схема) параллельно, без общей порчи контекста. |
| **using-git-worktrees** | Изолированная ветка/worktree, чтобы не мешать основному дереву и параллельным экспериментам. |
| **finishing-a-development-branch** | Когда задачи и тесты зелёные: выбор merge / PR / оставить / выбросить и аккуратный cleanup. |
| **writing-skills** | Писать или править собственные skills по дисциплине TDD для процессов (редко нужно контрибьютору панели). |

Типичный поток фичи: `brainstorming` → `writing-plans` → (`using-git-worktrees`) → `subagent-driven-development` / `executing-plans` → `verification-before-completion` → `finishing-a-development-branch`.

**TDD:** для точечной регрессии — проектный **`tdd`** (`.cursor/skills/tdd`). Superpowers `test-driven-development` в этот поток **не** входит (полная TDD-дисциплина на каждую фичу — только по явной просьбе). Подробная вилка Superpowers ↔ pstack — в правиле `use-skills`.

---

## pstack ([cursor/plugins · pstack](https://cursor.com/marketplace/cursor/pstack)) — зачем

**Что это:** playbook’и и principles от poteto (React core / Cursor): меньше кода, больше доказательств, параллельные агенты. Ставится **плагином** Marketplace (`pstack`), skills в `~/.cursor/plugins/cache/…/pstack/…/skills/`. После установки один раз: **`/setup-pstack`** (модели по ролям).

**Как стыкуется с Superpowers (чтобы агент не путался):**

| Когда | Что звать |
|-------|-----------|
| Новая фича без апрува | Только Superpowers: brainstorm → plan → «да» |
| Реализация после «да» | `executing-plans` / `subagent-driven` **или** `/poteto-mode`, если нужен rigor |
| Баг без `/poteto-mode` | `systematic-debugging` (+ project `tdd` при дешёвом тесте) |
| Явно `/poteto-mode` / «доведи PR» | Только poteto playbook — не мешать finishing/dispatching/swarm вручную |
| Параллель по умолчанию | `dispatching-parallel-agents`; `swarm`/`arena` — только явный вызов |

Не дублируйте весь pstack через `npx skills add` — плагин уже кладёт skills. Имя **`tdd`** есть и в плагине, и в проекте — **всегда** project `.cursor/skills/tdd`. Principles (`principle-*`) не звать отдельно.

| Skill | Зачем для AdminPanelAZ |
|-------|-------------------------|
| **`poteto-mode`** / **`poteto-help`** | Точка входа / выбор playbook (после апрува или на баг/PR). |
| **`architect`** | Типы и границы модулей до кода (API, node sync, adapters). |
| **`blast-radius`** | Маленький дифф → что ещё сломает (nginx, clients, install, agent). |
| **`how` / `why` / `teach`** | Разбор подсистем (HA, sync, install, Telegram). |
| **`interrogate`** | Сами атакуем дифф перед merge (чужие комментарии → `receiving-code-review`). |
| **`typescript-best-practices`** | Frontend `.ts` / `.tsx`. |
| **`no-comments` / `unslop` / `technical-writing`** | Чистый код и проза; docs / PR / коммиты. |

---

## site-architecture ([coreyhaines31/marketingskills](https://skills.sh/coreyhaines31/marketingskills/site-architecture)) — меню / IA

```bash
npx skills add coreyhaines31/marketingskills@site-architecture -g -a cursor -y
```

Файлы: `~/.agents/skills/site-architecture`. **Когда:** перестройка сайдбара, маршрутов, «куда положить раздел». Ориентир — IA/навигация. Визуал экрана — `web-design-guidelines` в репо; опционально **impeccable** с Marketplace (в starter pack нет — тяжёлый бинарь, не использовался).

---

## Anthropic Cybersecurity Skills ([mukul975/…](https://github.com/mukul975/Anthropic-Cybersecurity-Skills)) — зачем

**Что это:** ~817 узких security-playbooks (agentskills.io), community-проект с маппингом на MITRE ATT&CK, NIST CSF, ATLAS, D3FEND, AI RMF, F3. **Не** замена `review-security` Cursor.

```bash
npx skills add mukul975/Anthropic-Cybersecurity-Skills -g -a cursor -s '*' -y
npx skills update -g -y   # обновление
```

Файлы: `~/.agents/skills/`. Только для **авторизованного** тестирования и hardening **своей** панели.

**Зачем пакет в целом:** дать агенту пошаговые методики аналитика (JWT, SSRF, secrets, TLS, rate limit, OWASP API…), которых нет в общем чате. Агент выбирает skill по description и идёт по workflow.

**Зачем не тащить всё в каждый PR:** большинство доменов (AD, OT/ICS, мобилка, malware sandbox) к AdminPanelAZ не относятся. Для обычных PR достаточно `review-security` + `SECURITY.md`. Cyber-skills — точечно, когда явно тестируете/усиливаете security-поверхность.

### Какие группы skills полезны именно здесь

| Группа (примеры имён) | Зачем для AdminPanelAZ |
|------------------------|-------------------------|
| JWT / OAuth / session (`testing-jwt-token-security`, `exploiting-jwt-…`, `testing-oauth2-…`) | Панель на JWT + refresh cookie, Telegram OAuth, passkeys рядом с сессиями. |
| API abuse / rate limit (`implementing-api-rate-limiting-…`, `performing-api-rate-limiting-bypass`) | В проекте есть auth и global API rate limit (memory/Redis) — сверять дизайн и обходы. |
| Web/API OWASP (`conducting-api-security-testing`, CSRF/SSRF/XSS skills) | Публичная раздача конфигов, webhook’и, SSRF-риски к node agent / внешним URL. |
| Secrets / supply chain (`implementing-secret-scanning-…`, SBOM, dependency confusion) | Не допустить токены/ключи в git; аудит зависимостей рядом с pip-audit/npm audit в CI. |
| TLS / HTTPS (`performing-ssl-tls-security-assessment`, TLS 1.3 skills) | Публикация через nginx/Let’s Encrypt — согласовать с `siteaudit` и `SECURITY.md`. |
| AI/MCP (`auditing-mcp-servers-for-tool-poisoning`, prompt-injection skills) | У контрибьюторов сами MCP/skills с полными правами агента — понимать риски tooling. |

Остальные сотни skills (cloud IAM чужих провайдеров, ICS, red-team C2 и т.д.) можно не вызывать без явной задачи. Dual-use/offensive skills — **только** против систем с правом на тест.

---

## Как это стыкуется

```text
Навигация по коду          → codebase-memory
Доки библиотеки            → context7
PR / CI / GitHub           → github + babysit / review-*
UI глазами                 → browser
HTTPS заголовки домена     → siteaudit
Меню / IA                  → site-architecture (опц.); экран → web-design-guidelines (+ impeccable опц.)
Фича (план)                → Superpowers brainstorm → plan → «да»
Фича (после «да»)          → executing-plans / subagent-driven  или  /poteto-mode (rigor)
Баг без poteto             → systematic-debugging (+ project tdd)
Явно /poteto-mode          → только poteto playbook
Security диффа PR          → review-security
Глубокий security playbook → Anthropic Cybersecurity Skills (точечно)
```

---

## Договорённости по коду

1. **Границы хоста:** не трогать `/root/antizapret` и живой VPN runtime без явной задачи. VPN-операции — через **LocalAdapter / RemoteAdapter** (`node_adapter`), а не хардкод путей контроллера.
2. **Документация:** пользовательские тексты — простой русский в `docs/` и `docs/nastrojki/`. Новые/переименованные страницы и секции настроек — обновить соответствующий user-doc и таблицы в [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).
3. **API:** тонкие роутеры, логика в `backend/app/services/`; фронт ходит в API через `frontend/src/api/client.ts`.
4. **Фичи:** учитывать feature toggles и активный узел (`FeatureModulesContext`, `NodeContext`).
5. **Секреты:** `.env`, ключи, `*.pem`, GeoIP `*.mmdb`, граф `.codebase-memory/` — только локально.
6. **Проверки:** как в CI — ruff, bandit, eslint (advisory), shellcheck `-S warning` для `install.sh` и `scripts/*.sh`.
7. **Ключ NodeSource:** `install.sh` принимает ключ репозитория NodeSource только с отпечатком `NODESOURCE_KEY_FINGERPRINT`. Если NodeSource сменит ключ, установка Node.js остановится с ошибкой «Ключ NodeSource не совпал». Тогда сверить новый отпечаток с [инструкцией NodeSource](https://github.com/nodesource/distributions) и обновить `NODESOURCE_KEY_FINGERPRINT` в `install.sh` и `NODESOURCE_FPR` в `scripts/test-install-nodejs-lts.sh`.
8. **Ветки релиза и Dependabot:** изменения идут в `release/X.Y.Z`, в `main` — одним PR, когда релиз готов. Создав новую `release/X.Y.Z`, первым коммитом в ней переключите `target-branch` в `.github/dependabot.yml` на эту ветку. Dependabot читает файл только из `main`, поэтому новое значение заработает после merge этой ветки в `main`; до этого его PR в старую ветку релиза закрывайте без merge.

Security-критичные зоны (auth, middleware, public download, telegram webhook, rate limit): перед «готово» — **review-security**.

---

## Быстрый старт для разработчика

1. Клон репозитория, Python/Node как в README / `install.sh` (или локальный venv + `frontend` npm).
2. Открыть папку в **Cursor** → новый Agent-чат → вставить промпт из раздела **«Промпт для ИИ после клона»** выше → Approve на установку плагинов.
3. Один раз вручную: **`/setup-pstack`**. При необходимости `gh auth login`.
4. Пробежать [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) и [`SECURITY.md`](SECURITY.md).
5. Не коммитить `.cursor/mcp.json`, `.env`, БД, граф памяти; правки rules/skills из pack — в PR нормально.
6. PR: понятное описание, зелёный CI; крупные изменения — через **split-to-prs** / Superpowers finish-branch.

Вопросы и идеи по продукту: [Fider](https://claymore0098.fider.io/). Баги безопасности — см. [`SECURITY.md`](SECURITY.md).
