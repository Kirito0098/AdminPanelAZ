# Участие в разработке AdminPanelAZ

Гайд для тех, кто помогает с панелью в **Cursor**: какие MCP и skills использует мейнтейнер, **зачем** каждый из них, и договорённости по коду.

Пользовательские инструкции (для админов VPN): [`docs/README.md`](docs/README.md).  
Карта кода: [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).  
Безопасность: [`SECURITY.md`](SECURITY.md).

---

## Важно: локальные настройки Cursor не в git

Каталог **`.cursor/`** (MCP, rules, hooks) и **`.codebase-memory/`** в репозиторий **не коммитятся**.  
Skills мейнтейнера лежат вне репо (`~/.agents/skills/`, `~/.cursor/skills-cursor` и т.п.).

Подключайте инструменты **у себя локально** по этому файлу — не копируйте чужие токены и `mcp.json` с секретами в PR.

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
| **create-rule** | Локальные правила проекта (`.cursor/rules/`) — постоянный контекст агента; в git AdminPanelAZ не коммитим. |
| **create-hook** | Хуки на события агента (например напоминание обновить docs после правок UI). |
| **automate** | Создать **Cursor Automation** (расписание/триггеры в Cursor), не GitHub Actions репо. |
| **loop** | Повторять проверку по интервалу (`/loop 5m …`) — удобно для CI/smoke. |

Обычно **не** нужны для работы над панелью: `sdk`, `statusline`, `update-cli-config`, `update-cursor-settings`, `onboard`, `migrate-to-builds`, `create-subagent`, `create-skill` (мета-инструменты Cursor/IDE).

---

## Superpowers ([obra/superpowers](https://github.com/obra/superpowers)) — зачем каждый

**Что это:** методология *как вести разработку с агентом* (не security-библиотека). ~14 skills. Ставится глобально, не в git репо:

```bash
npx skills add obra/superpowers -g -a cursor -s '*' -y
```

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

Типичный поток: `brainstorming` → `writing-plans` → (`using-git-worktrees`) → `subagent-driven-development` / `executing-plans` + `test-driven-development` → `verification-before-completion` → `finishing-a-development-branch`.

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
Процесс фичи/бага          → Superpowers (brainstorm → plan → TDD → verify)
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
6. **Проверки:** как в CI / pre-commit — ruff, bandit, eslint (advisory), shellcheck для `install.sh` и `scripts/*.sh`.

Security-критичные зоны (auth, middleware, public download, telegram webhook, rate limit): перед «готово» — **review-security**.

---

## Быстрый старт для разработчика

1. Клон репозитория, Python/Node как в README / `install.sh` (или локальный venv + `frontend` npm).
2. Прочитать [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) и [`SECURITY.md`](SECURITY.md).
3. Подключить MCP и skills из разделов выше (локально).
4. Не коммитить `.cursor/`, `.env`, БД, граф памяти, `~/.agents/skills/`.
5. PR: понятное описание, зелёный CI; крупные изменения — через **split-to-prs** / Superpowers finish-branch.

Вопросы и идеи по продукту: [Fider](https://claymore0098.fider.io/). Баги безопасности — см. [`SECURITY.md`](SECURITY.md).
