# AdminPanelAZ — правила для агента

Источник правды по процессу — **always-on rules** в `.cursor/rules/` (агент читает их как обычные файлы). Этот файл — краткая карта для агентов, которые смотрят в `.agents/`.

## Обязательно до работы

1. **`.cursor/rules/use-skills.mdc`** — какой skill читать, маршрутизация и процесс; тесты только на критических узлах.
2. **`.cursor/rules/lean-code.mdc`** — проверки на границах, без «на всякий случай».
3. **`.cursor/rules/release-train-branching.mdc`** — ветки `release/X.Y.Z`, не фичи в `main`.

Пост о релизе в Telegram — **`.cursor/rules/telegram-release-post.mdc`** (по запросу).

Личная синхронизация с Gitea настраивается на сервере и в репозиторий не попадает.

## Project skills (в репо)

Лежат в `.cursor/skills/` (в `.agents/skills/` — относительные symlink’и на них):

| Skill | Зачем |
| ------- | -------- |
| `tdd` | Точечная регрессия на критическом узле |
| `karpathy-ponytail` | Думать до кода, ладдер простоты, хирургические правки |
| `react-best-practices` | Perf React (Vite SPA — без Next `server-*`) |
| `vercel-composition-patterns` | Раздутые boolean-пропсы |
| `web-design-guidelines` | Чеклист UI/a11y по коду |
| `webapp-testing` | Проверка UI в браузере |
| `split-design-spec` | Разбить большой design-спек |
| `tui-design` | CLI / консольное меню |
| `cli-toolbox` | fd/rg/bat/sd/yq/jaq/delta вместо find/grep/cat/sed |

## MCP и локальная обёртка

Агенты — **Zoo Code** и **Cursor**; правила, скиллы и шаблон MCP лежат в репозитории
(корневой [`AGENTS.md`](../AGENTS.md), `.cursor/rules/`, `.cursor/skills/`).

- Cursor берёт серверы из локального `.cursor/mcp.json` (шаблон — `.cursor/mcp.json.example`);
  Zoo Code — из настроек MCP своего клиента. Пути и токены — только локально, в git не попадают.
- `.agents/mcp_config.json.example` — шаблон в формате `mcpServers` (симлинк на
  `.cursor/mcp.json.example`); копируется в `.agents/mcp_config.json`.
- `.agents/bin/mcp` — локальная обёртка (не в git): список серверов, инструменты, ручной вызов.
  Конфиг ищется по порядку: `$MCP_CONFIG`, `.agents/mcp_config.json`, `.cursor/mcp.json`,
  `.cursor/mcp.json.example`.
- Плагины Marketplace (`superpowers`, `pstack`, `impeccable`) не используются: всё нужное — в репозитории.

## Тесты

Новые тесты — только auth/JWT/2FA, публичные конфиги, webhook Telegram, nginx/firewall/install, бэкапы, node agent, VPN-клиенты и лимиты. UI и тексты — без новых тестов.
