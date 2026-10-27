# AdminPanelAZ — правила для агента

Источник правды по процессу — **always-on rules** в `.cursor/rules/` (читаются Cursor автоматически). Этот файл — краткая карта для агентов, которые смотрят в `.agents/`.

## Обязательно до работы

1. **`.cursor/rules/use-skills.mdc`** — какой skill читать; вилка Superpowers ↔ pstack; тесты только на критических узлах.
2. **`.cursor/rules/lean-code.mdc`** — проверки на границах, без «на всякий случай».
3. **`.cursor/rules/release-train-branching.mdc`** — ветки `release/X.Y.Z`, не фичи в `main`.
4. **`.cursor/rules/gitea-agent-sync.mdc`** — что в GitHub vs личный Gitea.

Пост о релизе в Telegram — **`.cursor/rules/telegram-release-post.mdc`** (по запросу).

## Project skills (в репо)

Лежат в `.cursor/skills/` (в `.agents/skills/` — относительные symlink’и на них):

| Skill | Зачем |
|-------|--------|
| `tdd` | Точечная регрессия на критическом узле (не Superpowers TDD) |
| `ponytail-review` | Убрать переусложнение перед «готово» |
| `react-best-practices` | Perf React (Vite SPA — без Next `server-*`) |
| `vercel-composition-patterns` | Раздутые boolean-пропсы |
| `web-design-guidelines` | Чеклист UI/a11y по коду |
| `webapp-testing` | Проверка UI в браузере |
| `split-design-spec` | Разбить большой design-спек |
| `tui-design` | CLI / консольное меню |

## Плагины и опциональное (не в git)

Ставятся локально — см. [`CONTRIBUTING.md`](../CONTRIBUTING.md):

- Marketplace: **superpowers**, **pstack** (`/setup-pstack` один раз)
- По желанию: `site-architecture`, cyber-skills, **impeccable** (дизайн UI — если нужен)
- MCP: скопировать `.cursor/mcp.json.example` → `.cursor/mcp.json` и поправить пути/токены (**не коммитить**)

## Тесты

Новые тесты — только auth/JWT/2FA, публичные конфиги, webhook Telegram, nginx/firewall/install, бэкапы, node agent, VPN-клиенты и лимиты. UI и тексты — без новых тестов.
