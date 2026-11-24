# AdminPanelAZ — правила для агента

Источник правды по процессу — **always-on rules** в `.agents/rules/` (агент читает их как обычные файлы). Этот файл — краткая карта для агентов, которые смотрят в `.agents/`.

## Обязательно до работы

1. **`.agents/rules/use-skills.md`** — какой skill читать, маршрутизация и процесс; тесты только на критических узлах.
2. **`.agents/rules/lean-code.md`** — проверки на границах, без «на всякий случай».
3. **`.agents/rules/release-train-branching.md`** — ветки `release/X.Y.Z`, не фичи в `main`.

Пост о релизе в Telegram — **`.agents/rules/telegram-release-post.md`** (по запросу).

Личная синхронизация с Gitea настраивается на сервере и в репозиторий не попадает.

## Project skills (в репо)

Источник — `.agents/skills/`; в `.agents/` лежат симлинки, разложенные по режимам Zoo Code:

| Skill | Зачем | Режим |
| ------- | -------- | ------- |
| `karpathy-ponytail` | Думать до кода, ладдер простоты, хирургические правки | любой |
| `cli-toolbox` | fd/rg/bat/sd/yq/jaq/delta вместо find/grep/cat/sed | любой |
| `tdd` | Точечная регрессия на критическом узле | Code |
| `react-best-practices` | Perf React + Vite SPA (без Next и SSR) | Code |
| `vercel-composition-patterns` | Раздутые boolean-пропсы | Code |
| `web-design-guidelines` | Чеклист UI/a11y по коду | Code |
| `ui-ux-pro-max` | Меню, навигация, иерархия экранов, адаптив, a11y | Code |
| `frontend-design` | Визуальное направление нового экрана | Code |
| `webapp-testing` | Проверка UI в браузере | Code |
| `surgical-edits` | Доработка — правкой на месте, без второй кнопки/эндпоинта/пайплайна | Code |
| `code-simplifier` | Упростить только текущий дифф, не меняя поведение | Code |
| `tui-design` | CLI / консольное меню | Code |
| `brainstorming` | Вопросы, варианты и дизайн-док до кода | Architect |
| `split-design-spec` | Разбить большой design-спек | Architect |

Паки в `~/.agents/skill-packs/` в автопоиске отключены и читаются вручную:
security-пак (18 скиллов) и `systematic-debugging` для тяжёлых багов.

## MCP и локальная обёртка

Основной агент — **Zoo Code**; правила, скиллы и шаблон MCP лежат в репозитории
(корневой [`AGENTS.md`](../AGENTS.md), `.agents/rules/`, `.agents/skills/`) и читаются как обычные файлы.

- MCP-серверы подключаются в конфиге клиента; локальный `.agents/mcp.json` (шаблон —
  `.agents/mcp.json.example`) читает обёртка. Пути и токены — только локально, в git не попадают.
- `.agents/mcp_config.json.example` — шаблон в формате `mcpServers` (симлинк на
  `.agents/mcp.json.example`); копируется в `.agents/mcp_config.json`.
- `.agents/bin/mcp` — локальная обёртка (не в git): список серверов, инструменты, ручной вызов.
  Конфиг ищется по порядку: `$MCP_CONFIG`, `.agents/mcp_config.json`, `.agents/mcp.json`,
  `.agents/mcp.json.example`.
- Плагины Marketplace (`superpowers`, `pstack`, `impeccable`) не используются: всё нужное — в репозитории.

## Тесты

Новые тесты — только auth/JWT/2FA, публичные конфиги, webhook Telegram, nginx/firewall/install, бэкапы, node agent, VPN-клиенты и лимиты. UI и тексты — без новых тестов.
