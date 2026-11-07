---
name: cli-toolbox
description: "Терминал: поиск, диапазон строк, замена, YAML/JSON, diff через fd/rg/bat/sd/yq."
---

# CLI-инструменты сервера

На сервере стоят быстрые замены стандартных утилит. Правило простое: нужен поиск, замена,
просмотр файла или разбор конфига — берём инструмент из таблицы, а не `find` / `grep` /
`cat` / `sed` / `python -c`.

| Задача                         | Было                           | Стало               |
| ------------------------------ | ------------------------------ | ------------------- |
| найти файлы по имени/типу      | `find . -name '*.py'`          | `fd -e py`          |
| поиск по содержимому           | `grep -rn foo .`               | `rg -n foo`         |
| показать файл / диапазон строк | `cat f`, `sed -n '120,180p' f` | `bat -r 120:180 f`  |
| замена в файле                 | `sed -i 's/a/b/g' f`           | `sd 'a' 'b' f`      |
| YAML / TOML / properties       | ручной разбор, `python -c`     | `yq`                |
| JSON                           | `python -m json.tool`          | `jaq` / `jq`        |
| diff глазами                   | `git diff`                     | `git diff \| delta` |
| Python: линт / запуск          | `python -m ...`                | `ruff`, `uv run`    |
| JS/TS/JSON: быстрая проверка   | —                              | `biome`             |

## Поиск: `rg`

```bash
rg -n "def create_client" backend/app          # строка + номер
rg -t py -n "except Exception" backend/        # только python
rg -l "node_sync" backend frontend             # только имена файлов
rg -C 3 -n "TRAFFIC_LIMIT" backend/app         # контекст
rg -F -n "a.b(c)" .                            # литерал, без регекспа
rg --files -g '!dist' -g '!node_modules'       # вместо find | grep
```

- `rg` уважает `.gitignore`: `.codebase-memory/`, `.roo/`, `.agents/bin/`, `dist/` не находятся.
  Нужно заглянуть внутрь — `rg -uuu` (или `--no-ignore`).
- Кириллица в коде ошибок и логах — `rg -n "Не удалось" backend`.
- Не `grep | head -20`, а `rg -m 20` (лимит совпадений на файл).

## Поиск файлов: `fd`

```bash
fd -e py -e ts -t f            # по расширению, только файлы
fd -d 2 -t d                   # глубина 2, только каталоги
fd -H '\.env'                  # включить скрытые
fd -g '*.spec.tsx' frontend    # glob
fd -e py -x ruff check {}      # по одному файлу на вызов
```

## Просмотр: `bat`

```bash
bat -r 120:180 backend/app/main.py     # диапазон строк — вместо sed -n
bat -l yaml -r 1:60 deploy/compose.yml # явный язык подсветки
git diff | bat -l diff                 # подсветка дифа
```

В пайпах и для машинного вывода — `--paging=never --style=plain`, иначе получите ANSI-мусор
вместо текста. Для чтения файла целиком всё равно предпочитать `get_code_snippet` / `read_file`:
у `bat` нет структуры, он не экономит контекст.

## Замена: `sd`

```bash
sd -p 'old' 'new' file            # -p: показать, что изменится, файл не трогать
sd -s 'a.b(c)' 'x' file           # -s: литерал, без регекспа
sd 'version = "1"\n' 'version = "2"\n' pyproject.toml
```

- По умолчанию `sd` — регексп; на точках, скобках и `$` нужен `-s`.
- Сначала `-p` (preview), потом без него. Массовые правки через `fd -x sd ...` — только когда
  уверен в шаблоне: откат делать нечем, git покажет.
- Внутри markdown-таблиц и длинных строк `sd` удобнее `apply_diff`: не переформатирует файл.

## Конфиги: `yq`, `jaq`

```bash
yq '.services.web.image' deploy/compose.yml        # вытащить значение
yq -o=json '.' deploy/compose.yml | jaq -S '.'     # YAML -> сортированный JSON
yq -i '.a.b = "c"' file.yml                        # in-place (осторожно, это запись)
jaq -r '.scripts.build' frontend/package.json
jaq '.mcpServers | keys' .roo/mcp.json
jaq -S '.scripts' frontend/package.json            # -S: стабильный порядок ключей
```

- `yq` — v4 (mikefarah), синтаксис v4: `yq 'e .path'`, старый `yq r` не работает.
- `jaq` — Rust-клон `jq`, флаги как у `jq`; `jq` тоже установлен, разницы для нас нет.
- Читать YAML `bat`-ом для «понять, что там» дешевле, чем `yq .` целиком.

## Diff: `delta`

```bash
git diff | delta                     # цветной разбор
git diff --stat && git diff | delta --side-by-side
git show HEAD | delta                # последний коммит
git log -p -2 -- backend/app | delta
```

`core.pager` в git не переписан — `delta` вызывается явно. Exit code у `delta` — от себя,
а не от `git diff`: проверять дифф на пустоту нужно по `git diff --quiet`.

## Python: `ruff`, `uv`

```bash
ruff check backend/                  # быстрый линт
ruff check --select I --fix backend/ # сортировка импортов
ruff format --diff backend/app/x.py  # показать формат, не писать
uv run --project backend python -c '...'   # запуск в окружении проекта
uv tool list                         # что установлено глобально
```

Проверки проекта — **строго** из `AGENTS.md`: `backend/.venv/bin/ruff` (0.16.2), не глобальный
`ruff` 0.17.4. Версии правил разные — глобальным линтом можно получить «новые» замечания и
начать править код под другой ruff. Глобальный — для ad-hoc разбора одного файла.

## JS/TS/JSON: `biome`

```bash
biome check frontend/src/lib/api.ts     # диагностика одного файла
biome format --write file.json          # форматирование JSON/TS
biome check --reporter=summary frontend/src
```

Линт проекта — `npm run lint` (eslint, `--quiet`), типы — `npm run typecheck`. `biome`
не заменяет их и не должен менять стиль проекта: в `frontend/` нет `biome.json`, поэтому
конфиг по умолчанию отличается от принятого в репозитории. `biome` — для одноразовых
проверок и для JSON-файлов вне проекта.

## Где что лежит и как переустановить

| Инструмент                       | Версия                                   | Откуда                                             |
| -------------------------------- | ---------------------------------------- | -------------------------------------------------- |
| `fd`, `rg`, `bat`, `delta`, `sd` | 9.0.0 / 14.1.0 / 0.24.0 / 0.16.5 / 1.0.0 | `apt-get install fd-find ripgrep bat git-delta sd` |
| `yq`                             | v4.54.2                                  | GitHub release → `/usr/local/bin/yq`               |
| `jaq`                            | 3.1.2                                    | GitHub release → `/usr/local/bin/jaq`              |
| `ruff`                           | 0.17.4                                   | `uv tool install ruff`                             |
| `biome`                          | 2.6.6                                    | `npm i -g @biomejs/biome`                          |
| `uv`                             | 0.12.3                                   | уже стоял (`/root/.local/bin/uv`)                  |

На Debian/Ubuntu бинарники называются `fdfind` и `batcat` — на них сделаны симлинки
`/usr/local/bin/fd` и `/usr/local/bin/bat`. Если симлинк пропал, команды `fd`/`bat` не найдутся.

Проверка одной строкой:

```bash
for c in fd rg bat sd delta yq jaq jq ruff uv node npm biome; do printf '%-6s ' "$c"; command -v "$c" || echo MISSING; done
```
