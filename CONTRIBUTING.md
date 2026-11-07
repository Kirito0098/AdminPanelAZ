# Участие в разработке AdminPanelAZ

Гайд для тех, кто помогает с панелью: какие MCP и skills использует мейнтейнер, **зачем** каждый из них, и договорённости по коду. Агент — **DSH**: правила и каталог скиллов лежат в репозитории и читаются как обычные файлы, а MCP-серверы подключает профиль DSH на машине оператора.

Пользовательские инструкции (для админов VPN): [`docs/README.md`](docs/README.md).
Карта кода: [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).
Безопасность: [`SECURITY.md`](SECURITY.md).
Выжимка правил для агента: [`AGENTS.md`](AGENTS.md).

---

## Agent starter pack (уже в git)

| Путь | Что |
| ------ | ----- |
| `.cursor/rules/` | `use-skills`, `lean-code`, `release-train-branching`, `gitea-agent-sync`, `telegram-release-post`. Каталог остался от Cursor, но это просто markdown-правила — DSH читает их как обычные файлы |
| `.cursor/skills/` | project skills: `tdd`, `ponytail-review`, `react-best-practices`, `vercel-composition-patterns`, `web-design-guidelines`, `webapp-testing`, `split-design-spec`, `tui-design` |
| `.agents/skills/` | те же скиллы относительными симлинками на `.cursor/skills/` |
| `.agents/skills-lock.json` | пин стороннего скилла `tui-design` (source `gfargo/skills`) |
| `.cursor/mcp.json.example` | шаблон MCP **без** секретов |
| `.agents/mcp_config.json.example` | тот же шаблон для обёртки `.agents/bin/mcp` (симлинк на файл выше) |
| `.agents/AGENTS.md` | краткая карта для агентов, которые смотрят в `.agents/` |

**Не в git (локально):** `.cursor/mcp.json`, `.agents/mcp_config.json`, `.agents/bin/`, `.codebase-memory/`, `docs/plans/`, `docs/superpowers/`, `.env`, `*.db`.

Токены и личные MCP-конфиги в PR не кладём: пути, ключи и авторизация живут только на машине оператора.

---

## Профиль DSH

Профиль — `~/.dsh/profiles/<id>/cordis.patch.yml`, на машине оператора, не в репозитории. В нём:

- воркспейс `remote-ssh` с кодом на сервере (`/opt/AdminPanelAZ`);
- записи `@deepseek-ai/dsh-mcp-client` — по одной на MCP-сервер;
- модель, локаль, настройки клиента.

Если MCP не виден в сессии — смотреть надо профиль, а не `.cursor/mcp.json`: агент берёт серверы из профиля. Новые плагины в патч добавляются только через `insert:` — запись с одним `id` считается переопределением существующей и молча пропускается.

---

## MCP — зачем каждый

MCP даёт агенту доступ к внешним сервисам и индексам. Без них остаётся только чтение файлов и shell.

| Сервер (`serverName`) | Зачем | Когда |
| --- | --- | --- |
| `codebase_memory` | Граф символов: функции, классы, вызовы, HTTP-роуты, импорты. `search_graph`, `trace_path`, `get_code_snippet`, `get_architecture` | Навигация по незнакомому коду. После крупных рефакторингов и удаления модулей — переиндексация, иначе граф ссылается на удалённые файлы |
| `github` | PR, issues, GitHub Actions и комментарии прямо из чата | Посмотреть PR, статус CI, triage комментариев. Только чтение |
| `context7` | Актуальная документация библиотек | Правите интеграцию с FastAPI / React / Recharts / webauthn / redis — не гадаете API по памяти модели |
| `playwright` | Браузер: клики, ввод, снимки DOM и экрана, логи консоли | UI-правки: логин, 2FA, NOC, Mini App, мастера настроек. В jsdom порталы и Radix-меню не воспроизводятся |
| `siteaudit` | Audit публичного URL: HTTPS, HSTS, CSP, cookies, SSL | После смены CSP/HSTS и публикации домена |
| `lazyweb` | Подбор референсов UI | Только когда нужны примеры интерфейсов |

`codebase_memory`, `github`, `playwright` и `siteaudit` запускаются **по SSH на тот же хост, где лежит код**, поэтому граф и индексы — серверные, а не по локальному зеркалу.

`siteaudit` и `lazyweb` тяжёлые и в обычной работе висят в каждом запросе зря: держите их выключенными в профиле и включайте на время аудита сайта и подбора референсов.

### Шаблон `mcp.json`

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

Для GitHub с токеном в заголовке:

```json
"github": {
  "url": "https://api.githubcopilot.com/mcp/",
  "headers": {
    "Authorization": "Bearer ${env:GITHUB_PERSONAL_ACCESS_TOKEN}"
  }
}
```

```bash
gh auth login        # github-mcp-stdio берёт токен из gh
```

### Проверить сервер из терминала

Обёртка `.agents/bin/mcp` (локальная, не в git) поднимает сервер на один вызов и печатает ответ:

```bash
.agents/bin/mcp servers                        # список серверов из конфига
.agents/bin/mcp tools codebase_memory          # инструменты сервера
.agents/bin/mcp tools codebase_memory search_graph   # JSON-схема аргументов
.agents/bin/mcp call codebase_memory search_graph '{"query": "node_sync"}'
```

Конфиг ищется по порядку: `$MCP_CONFIG` → `.agents/mcp_config.json` → `.cursor/mcp.json` → `.cursor/mcp.json.example`.

---

## Skills — где лежат и что вызывать

| Где | Что |
| ----- | ----- |
| `~/.dsh/skills/<name>/` | глобальные скиллы DSH: процесс, инженерные приёмы, тексты, фронт. Подхватываются без настройки |
| `.cursor/skills/<name>/` | проектные скиллы из этого репозитория: `tdd`, `ponytail-review`, `react-best-practices`, `vercel-composition-patterns`, `web-design-guidelines`, `webapp-testing`, `split-design-spec`, `tui-design` |
| `~/.dsh/skills-extra/security/` | security-пак, **не подключён** (см. ниже) |

Скилл — это каталог с `SKILL.md` и frontmatter (`name`, `description`); описание нужно, чтобы агент выбрал скилл по ситуации, а не по названию.

**Маршрутизация «ситуация → skill»** — [`use-skills.mdc`](.cursor/rules/use-skills.mdc) (always-on правило) и каталог `~/.dsh/skills/skills-catalog/SKILL.md`; короткая таблица для агента — в [`AGENTS.md`](AGENTS.md). При расхождении верь каталогу.

### Процессные скиллы (глобальные)

| Skill | Зачем |
| ------- | -------- |
| **`brainstorming`** | До кода: уточнить цель и ограничения, 2–3 подхода, получить апрув дизайна |
| **`writing-plans`** | Разбить одобренный дизайн на задачи с путями файлов и шагами проверки |
| **`executing-plans`** | Выполнить готовый план с чекпоинтами и отчётом |
| **`systematic-debugging`** | Баг и красный тест: сначала root cause, не «подкрутить симптом» |
| **`verification-before-completion`** | Запрет говорить «готово» без реальных прогонов проверок |
| **`requesting-code-review`** / **`receiving-code-review`** | Запросить ревью по плану / разобрать пришедшие замечания по существу |
| **`ponytail-review`** | Свой новый код: что удалить как переусложнение |
| **`architect`** | Типы и границы модулей до кода |
| **`blast-radius`** | Маленький дифф — что ещё сломается за его пределами |
| **`interrogate`** | Сами атакуем дифф перед merge |
| **`explain`** | «Как работает подсистема», «почему так» |
| **`technical-writing`** / **`unslop`** | Docs, README, CHANGELOG, PR-описание; чистка AI-штампов в прозе |
| **`typescript-best-practices`** | Frontend `.ts` / `.tsx` |
| **`benchmark-checklist`** | Замер перфа и лимитов до публикации цифры |
| **`recall`** / **`figure-it-out`** / **`correct`** | «Где я остановился» / нет подходящего playbook / повторяющаяся ошибка агентов в репо |

### Проектные скиллы (в репозитории)

| Skill | Зачем |
| ------- | -------- |
| `tdd` | Точечная регрессия на критическом узле; вызывается только когда тест дешёвый и путь ясен |
| `ponytail-review` | Убрать переусложнение перед «готово» |
| `react-best-practices` | Perf React для Vite SPA: правила `server-*` и `rendering-hydration-*` неприменимы |
| `vercel-composition-patterns` | Компонент оброс boolean-пропсами (4+ флагов режима) |
| `web-design-guidelines` | Чеклист UI и a11y по коду |
| `webapp-testing` | Проверить UI в браузере через Playwright |
| `split-design-spec` | Разбить большой design-спек по папкам |
| `tui-design` | `install.sh`, консольное меню, CLI |

### Поток работы

```text
Новая фича / новый экран / эндпоинт / схема данных
  → brainstorming → writing-plans → «да» пользователя
  → executing-plans
  → verification-before-completion (+ security-скилл, если дифф трогает критичное)
  → коммит в ветку release/X.Y.Z

Баг / «не работает» / красный CI
  → systematic-debugging
  → дешёвый локальный тест → project tdd (если путь теста ясен)

Мелочь: 1–2 файла без нового поведения (пункт меню, вкладки, подписи, вёрстка, мелкий баг)
  → без процессных скиллов: план в чате на 2–5 пунктов → прогоны
```

`tdd` есть и в проектном pack, и среди глобальных скиллов — читаем **проектный** `.cursor/skills/tdd`: в нём список критических узлов и «prefer no new test over a bad test».

---

## Security-скиллы

Пак в [`Anthropic Cybersecurity Skills`](https://github.com/mukul975/Anthropic-Cybersecurity-Skills) — узкие playbooks с маппингом на MITRE ATT&CK, NIST CSF, ATLAS, D3FEND. Это **не** замена security-ревью диффа.

Лежит в `~/.dsh/skills-extra/security/` и специально не подключён: иначе 18 описаний висят в каждом запросе. Подключить на время аудита и убрать после:

```bash
cp -r ~/.dsh/skills-extra/security/* ~/.dsh/skills/
```

Только для **своей** панели и авторизованного тестирования. Точечный аудит поверхности: JWT → `testing-jwt-token-security`; подпись и верификация → `implementing-jwt-signing-and-verification`; CORS → `testing-cors-misconfiguration`; CSRF → `performing-csrf-attack-simulation`; WebSocket → `testing-websocket-api-security`; обход путей → `performing-directory-traversal-testing`; Host → `testing-for-host-header-injection`; XSS → `testing-for-xss-vulnerabilities`; BAC/IDOR → `testing-for-broken-access-control`; заголовки → `performing-security-headers-audit`; API auth → `testing-api-authentication-weaknesses`; OWASP API → `testing-api-security-with-owasp-top-10`; CI → `securing-github-actions-workflows`; секреты → `implementing-secret-scanning-with-gitleaks`; харденинг хоста → `hardening-linux-endpoint-with-cis-benchmark`; passkey → `implementing-passwordless-authentication-with-fido2`; лимиты → `implementing-api-rate-limiting-and-throttling`.

### Какие группы полезны именно здесь

| Группа | Зачем для AdminPanelAZ |
| -------- | ------------------------ |
| JWT / OAuth / сессии | Панель на JWT + refresh cookie, Telegram OAuth, passkeys рядом с сессиями |
| API abuse / rate limit | В проекте есть auth и global API rate limit (memory/Redis) — сверять дизайн и обходы |
| Web/API OWASP (CSRF, SSRF, XSS) | Публичная раздача конфигов, webhook’и, SSRF-риски к node agent и внешним URL |
| Secrets / supply chain | Не допустить токены и ключи в git; аудит зависимостей рядом с pip-audit/npm audit в CI |
| TLS / HTTPS | Публикация через nginx/Let’s Encrypt — согласовать с `siteaudit` и `SECURITY.md` |
| AI/MCP (tool poisoning, prompt injection) | У контрибьюторов MCP и скиллы с полными правами агента — понимать риски tooling |

Остальные сотни скиллов (чужие cloud IAM, ICS, red-team C2) без явной задачи не вызываем. Dual-use/offensive — только против систем с правом на тест.

---

## Как это стыкуется

```text
Навигация по коду          → codebase_memory
Доки библиотеки            → context7
PR / CI / GitHub           → github
UI глазами                 → playwright
HTTPS заголовки домена     → siteaudit
Референсы интерфейсов      → lazyweb
Фича (план)                → brainstorming → writing-plans → «да»
Фича (после «да»)          → executing-plans
Баг                        → systematic-debugging (+ project tdd)
Перед «готово»             → verification-before-completion
Свой новый код             → ponytail-review
Security диффа             → security-пак, точечно
Проверить UI после правок  → webapp-testing / playwright
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

Security-критичные зоны (auth, middleware, public download, telegram webhook, rate limit): перед «готово» — security-скилл из пака.

---

## Быстрый старт для разработчика

1. Клон репозитория, Python/Node как в README / `install.sh` (или локальный venv + `frontend` npm).
2. Открыть `/opt/AdminPanelAZ` в DSH и прочитать [`AGENTS.md`](AGENTS.md) + [`use-skills.mdc`](.cursor/rules/use-skills.mdc) — оттуда берётся выбор скилла и команды проверок.
3. MCP: скопировать `.cursor/mcp.json.example` → `.cursor/mcp.json`, поправить пути команд под свою ОС; в профиле DSH описать те же серверы записями `dsh-mcp-client`. Один раз — `gh auth login`.
4. Проверить серверы: `.agents/bin/mcp servers` (список) и `mcp tools <server>` (инструменты).
5. Команды прогонов — в [`AGENTS.md`](AGENTS.md), раздел «Команды проверок»: ruff, точечный pytest, `npm run typecheck && npm run lint`, для UI — `npm run build:all`.
6. PR: понятное описание, зелёный CI. Крупные изменения — отдельными reviewable коммитами, ветка — активная `release/X.Y.Z`.

Вопросы и идеи по продукту: [Fider](https://claymore0098.fider.io/). Баги безопасности — см. [`SECURITY.md`](SECURITY.md).
