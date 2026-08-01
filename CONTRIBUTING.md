# Участие в разработке AdminPanelAZ

Краткий гайд для тех, кто помогает с панелью в **Cursor**. Здесь — MCP и skills, которые использует основной мейнтейнер, плюс договорённости по коду.

Пользовательские инструкции (для админов VPN): [`docs/README.md`](docs/README.md).  
Карта кода: [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).  
Безопасность: [`SECURITY.md`](SECURITY.md).

---

## Важно: локальные настройки Cursor не в git

Каталог **`.cursor/`** (MCP, rules, hooks) и **`.codebase-memory/`** в репозиторий **не коммитятся**.  
Skills мейнтейнера лежат вне репо (`~/.cursor/skills-cursor` и т.п.).

Подключайте инструменты **у себя локально** по этому файлу — не копируйте чужие токены и `mcp.json` с секретами в PR.

---

## Рекомендуемые MCP

| MCP | Зачем в этом проекте |
|-----|----------------------|
| **codebase-memory** | Граф кода (~сотни сервисов/роутеров). После крупных рефакторингов — полная переиндексация («Обнови граф» / `index_repository`). |
| **github** | PR, Issues, Actions. Нужны `gh` и авторизация. |
| **context7** | Актуальная документация библиотек (FastAPI, React, Recharts, webauthn, Redis…). |
| **siteaudit** | Smoke по публичному HTTPS: заголовки, CSP, HSTS, cookies. Не для SEO. |
| **cursor-ide-browser** | Встроенный в Cursor: UI-smoke (логин, NOC, настройки, Mini App). |

### Пример `~/.cursor/mcp.json` (или `.cursor/mcp.json` в клоне — файл локальный)

Подставьте свои пути к бинарникам. **Секреты в git не класть.**

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

Альтернатива для **GitHub** (hosted), если Cursor видит env на вашей машине:

```json
"github": {
  "url": "https://api.githubcopilot.com/mcp/",
  "headers": {
    "Authorization": "Bearer ${env:GITHUB_PERSONAL_ACCESS_TOKEN}"
  }
}
```

На **Cursor Remote / SSH** переменные из `~/.bashrc` часто **не** попадают в extension host: пустой Bearer → ошибка вроде `SSE ... 400`. Надёжнее stdio-сервер, который сам берёт токен из `gh auth token` (обёртка вокруг [github-mcp-server](https://github.com/github/github-mcp-server)), либо PAT прямо в локальном (не коммитимом) `mcp.json`.

### Одноразовая авторизация

```bash
# GitHub CLI — и для MCP, и для PR-скиллов
gh auth login

# Context7 — Settings → MCP → context7 → OAuth
# codebase-memory / siteaudit — поставить CLI (codebase-memory-mcp, uvx) по их README
```

После правок MCP: Reload Window / перезапуск Cursor, зелёные точки в **Settings → MCP**.

---

## Рекомендуемые skills

Подключайте/используйте те же сценарии, что и мейнтейнер:

| Skill | Когда |
|-------|--------|
| **review-security** | Auth, 2FA/passkey, CSP, rate limit, IP whitelist, публичная раздача конфигов, node agent. |
| **canvas** | Архитектура, метрики, отчёты по мёртвому коду — вместо длинных markdown-таблиц. |
| **babysit** + **review-bugbot** | Довести PR до зелёного CI. |
| **split-to-prs** | Большая фича → несколько reviewable PR. |
| **shell** | `install.sh`, systemd, nginx, firewall, host-ops. |
| **create-rule** / **create-hook** / **automate** / **loop** | По необходимости, только локально. |

Не обязательны для продукта: skills про Cursor SDK / statusline / CLI config IDE.

---

## Договорённости по коду

1. **Границы хоста:** не трогать `/root/antizapret` и живой VPN runtime без явной задачи. VPN-операции — через **LocalAdapter / RemoteAdapter** (`node_adapter`), а не хардкод путей контроллера.
2. **Документация:** пользовательские тексты — простой русский в `docs/` и `docs/nastrojki/`. Новые/переименованные страницы и секции настроек — обновить соответствующий user-doc и таблицы в [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md).
3. **API:** тонкие роутеры, логика в `backend/app/services/`; фронт ходит в API через `frontend/src/api/client.ts`.
4. **Фичи:** учитывать feature toggles и активный узел (`FeatureModulesContext`, `NodeContext`).
5. **Секреты:** `.env`, ключи, `*.pem`, GeoIP `*.mmdb`, граф `.codebase-memory/` — только локально.
6. **Проверки:** как в CI / pre-commit — ruff, bandit, eslint (advisory), shellcheck для `install.sh` и `scripts/*.sh`.

Security-критичные зоны (auth, middleware, public download, telegram webhook, rate limit): перед «готово» имеет смысл прогнать **review-security**.

---

## Быстрый старт для разработчика

1. Клон репозитория, Python/Node как в README / `install.sh` (или локальный venv + `frontend` npm).
2. Прочитать [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) и [`SECURITY.md`](SECURITY.md).
3. Подключить MCP и skills из таблиц выше.
4. Не коммитить `.cursor/`, `.env`, БД, граф памяти.
5. PR: понятное описание, зелёный CI; крупные изменения — через **split-to-prs**.

Вопросы и идеи по продукту: [Fider](https://claymore0098.fider.io/). Баги безопасности — см. [`SECURITY.md`](SECURITY.md).
