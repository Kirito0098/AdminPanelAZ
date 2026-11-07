# AdminPanelAZ — правила для агента

Источник правды по процессу — **always-on rules** в `.cursor/rules/` (агент читает их как обычные файлы). Этот файл — краткая карта для агентов, которые смотрят в `.agents/`.

## Обязательно до работы

1. **`.cursor/rules/use-skills.mdc`** — какой skill читать; вилка Superpowers ↔ pstack; тесты только на критических узлах.
2. **`.cursor/rules/lean-code.mdc`** — проверки на границах, без «на всякий случай».
3. **`.cursor/rules/release-train-branching.mdc`** — ветки `release/X.Y.Z`, не фичи в `main`.
4. **`.cursor/rules/gitea-agent-sync.mdc`** — что в GitHub vs личный Gitea.

Пост о релизе в Telegram — **`.cursor/rules/telegram-release-post.mdc`** (по запросу).

## Project skills (в репо)

Лежат в `.cursor/skills/` (в `.agents/skills/` — относительные symlink’и на них):

| Skill | Зачем |
| ------- | -------- |
| `tdd` | Точечная регрессия на критическом узле (не Superpowers TDD) |
| `ponytail-review` | Убрать переусложнение перед «готово» |
| `react-best-practices` | Perf React (Vite SPA — без Next `server-*`) |
| `vercel-composition-patterns` | Раздутые boolean-пропсы |
| `web-design-guidelines` | Чеклист UI/a11y по коду |
| `webapp-testing` | Проверка UI в браузере |
| `split-design-spec` | Разбить большой design-спек |
| `tui-design` | CLI / консольное меню |

## MCP и локальная обёртка

Агент — **DSH**; правила и маршрутизация скиллов описаны в корневом [`AGENTS.md`](../AGENTS.md).
Профиль DSH, скиллы и MCP-серверы живут на машине оператора (`~/.dsh/`) и в репозиторий не попадают.

- Серверы подключает `dsh-mcp-client` из профиля DSH (`~/.dsh/profiles/<id>/cordis.patch.yml`),
  а не `.cursor/mcp.json`.
- `.agents/mcp_config.json.example` — шаблон в формате `mcpServers` (симлинк на
  `.cursor/mcp.json.example`); копируется в `.agents/mcp_config.json`.
- `.agents/bin/mcp` — локальная обёртка (не в git): список серверов, инструменты, ручной вызов.
  Конфиг ищется по порядку: `$MCP_CONFIG`, `.agents/mcp_config.json`, `.cursor/mcp.json`,
  `.cursor/mcp.json.example`.
- Marketplace Cursor (`superpowers`, `pstack`, `site-architecture`, `impeccable`) больше не используется — Cursor удалён.

## Тесты

Новые тесты — только auth/JWT/2FA, публичные конфиги, webhook Telegram, nginx/firewall/install, бэкапы, node agent, VPN-клиенты и лимиты. UI и тексты — без новых тестов.
