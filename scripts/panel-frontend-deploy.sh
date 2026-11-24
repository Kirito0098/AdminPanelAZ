#!/usr/bin/env bash
# Ставит интерфейс панели и Mini App, собранный в CI (GitHub Release), без npm и Node на сервере.
# Каналов два: релиз по тегу (--tag) и сборка по коммиту (--commit) из pre-release «frontend-builds»,
# который наполняет CI на каждый push в main/release/**.
# Распаковывает в соседние каталоги и подменяет двумя переименованиями: при сбое старый интерфейс цел.
# Сборка помнит свой коммит (frontend/dist/.build-info.json) — чужой коммит не ставится без --force.
# Коды возврата: 0 — поставлено, 3 — сборки нет, 4 — канал недоступен, 1 — сборка не прошла проверку.
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
# Репозиторий берётся из origin; переменная нужна только для ручного запуска с чужим remote.
GITHUB_REPO="${GITHUB_REPO:-}"
FALLBACK_GITHUB_REPO="Kirito0098/AdminPanelAZ"
BUILDS_CHANNEL="frontend-builds"
INSTALL_DIR="${INSTALL_DIR:-/opt/AdminPanelAZ}"
TAG=""
COMMIT=""
ARCHIVE=""
FORCE=false
RESTART=true
# Пуш и обновление подряд — обычный сценарий: CI публикует сборку через несколько минут, поэтому ждём.
WAIT_ATTEMPTS="${FRONTEND_ARTIFACT_ATTEMPTS:-6}"
WAIT_SECONDS="${FRONTEND_ARTIFACT_RETRY_DELAY:-20}"

usage() {
  cat <<'EOF'
Usage: panel-frontend-deploy.sh [--commit [SHA] | --tag vX.Y.Z | --file path.tar.gz] [опции]

  --commit [SHA]  сборка для коммита из канала frontend-builds (по умолчанию — HEAD)
  --tag TAG       тег релиза на GitHub (по умолчанию — тег текущего HEAD)
  --file PATH     готовый tar.gz (офлайн, scp с другой машины)
  --repo OWNER/REPO  репозиторий релизов (по умолчанию — origin, если он на github.com)
  --dir PATH      каталог установки (по умолчанию /opt/AdminPanelAZ)
  --force         ставить сборку, даже если она для другого коммита
  --no-restart    не перезапускать панель
  -h, --help      эта справка

Переменные: FRONTEND_ARTIFACT_ATTEMPTS (6) и FRONTEND_ARTIFACT_RETRY_DELAY (20 с) — сколько раз
и с какой паузой ждать сборку канала, пока CI её не опубликовал.
EOF
}

die() {
  echo "ОШИБКА: $*" >&2
  exit 1
}

# Отказ с кодом: вызывающий отличает «сборки нет» (3) и «канал недоступен» (4) от «не прошло проверку» (1).
die_code() {
  local code="$1"
  shift
  echo "ОШИБКА: $*" >&2
  exit "$code"
}

info() {
  echo "$*"
}

# OWNER/REPO из origin. Не GitHub (Gitea-зеркало, локальный клон) — пусто: чужой сборке не доверяем.
resolve_github_repo() {
  local url
  url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null)" || return 0
  case "$url" in
    https://github.com/*) url="${url#https://github.com/}" ;;
    ssh://git@github.com/*) url="${url#ssh://git@github.com/}" ;;
    git@github.com:*) url="${url#git@github.com:}" ;;
    *) return 0 ;;
  esac
  url="${url%.git}"
  url="${url%/}"
  [[ "$url" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || return 0
  printf '%s' "$url"
}

# Качает ассет канала, ожидая свежую сборку: сразу после push CI ещё собирает (2–5 минут).
fetch_with_wait() {
  local attempt
  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
    if curl -fsSL --max-time 120 "$BASE/$NAME" -o "$ARCHIVE" 2>/dev/null; then
      return 0
    fi
    if ((attempt < WAIT_ATTEMPTS)); then
      info "Сборки для ${COMMIT:0:12} ещё нет (попытка $attempt из $WAIT_ATTEMPTS) — ждём ${WAIT_SECONDS} с…"
      sleep "$WAIT_SECONDS"
    fi
  done
  return 1
}

# В архиве только dist панели и Mini App: без абсолютных путей, «..» и ссылок.
validate_archive() {
  local entry listing="$TMP_DIR/archive.list"
  # Листинг — в файл: `tar … | grep -q` под pipefail даёт SIGPIPE и проверка молча пропускается на большом архиве.
  tar tvzf "$ARCHIVE" >"$listing" || die_code 1 "не удалось прочитать архив $ARCHIVE"
  if grep -qE '^[lh]' "$listing"; then
    die_code 1 "в архиве есть симлинк или жёсткая ссылка"
  fi
  while IFS= read -r entry; do
    if [[ "/$entry/" == *"/../"* ]]; then
      die_code 1 "в архиве недопустимый путь: $entry"
    fi
    case "$entry" in
      frontend/dist | frontend/dist/* | backend/app/static/tg_mini | backend/app/static/tg_mini/*) ;;
      *) die_code 1 "в архиве неожиданный путь: $entry" ;;
    esac
  done < <(tar tzf "$ARCHIVE")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --commit)
      # Значение необязательное: без него берём HEAD, чтобы вызывающему не дублировать git rev-parse.
      if [[ -n "${2:-}" && "${2:-}" != -* ]]; then
        COMMIT="$2"
        shift 2
      else
        COMMIT="HEAD"
        shift
      fi
      ;;
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --file)
      ARCHIVE="${2:-}"
      shift 2
      ;;
    --repo)
      GITHUB_REPO="${2:-}"
      shift 2
      ;;
    --dir)
      INSTALL_DIR="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --no-restart)
      RESTART=false
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "неизвестный аргумент: $1 (см. --help)"
      ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || die "запустите от root: sudo $0 $*"

FRONTEND_DIR="$INSTALL_DIR/frontend"
TG_MINI_DIR="$INSTALL_DIR/backend/app/static/tg_mini"
[[ -d "$INSTALL_DIR/.git" ]] || die_code 4 "не найден git-репозиторий в $INSTALL_DIR"

if [[ -n "$COMMIT" ]]; then
  COMMIT="$(git -C "$INSTALL_DIR" rev-parse --verify "$COMMIT^{commit}" 2>/dev/null)" \
    || die_code 4 "в $INSTALL_DIR нет коммита ${COMMIT} — соберите интерфейс на сервере или укажите --file"
  [[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || die_code 4 "ожидается полный sha коммита, получено: $COMMIT"
elif [[ -z "$ARCHIVE" && -z "$TAG" ]]; then
  TAG="$(git -C "$INSTALL_DIR" describe --tags --exact-match 2>/dev/null)" \
    || die "HEAD не на теге — укажите --commit SHA, --tag vX.Y.Z или --file path.tar.gz"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
chmod 755 "$TMP_DIR"

if [[ -z "$ARCHIVE" ]]; then
  command -v curl >/dev/null 2>&1 || die_code 4 "нужен curl (или передайте --file)"
  if [[ -n "$COMMIT" ]]; then
    REPO="${GITHUB_REPO:-$(resolve_github_repo)}"
    [[ -n "$REPO" ]] || die_code 4 "origin не на github.com — канала сборок нет (--repo, --tag или --file)"
    NAME="adminpanelaz-frontend-$COMMIT.tar.gz"
    BASE="https://github.com/$REPO/releases/download/$BUILDS_CHANNEL"
  else
    REPO="${GITHUB_REPO:-$FALLBACK_GITHUB_REPO}"
    [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]] || die "ожидается тег вида vX.Y.Z, получено: $TAG"
    NAME="adminpanelaz-frontend-$TAG.tar.gz"
    BASE="https://github.com/$REPO/releases/download/$TAG"
  fi
  ARCHIVE="$TMP_DIR/$NAME"
  info "Скачивание $BASE/$NAME…"
  if [[ -n "$COMMIT" ]]; then
    fetch_with_wait || die_code 3 "сборки для ${COMMIT:0:12} нет: CI не собрал или прогон отменён"
    curl -fsSL --max-time 120 "$BASE/$NAME.sha256" -o "$TMP_DIR/$NAME.sha256" \
      || die_code 1 "у сборки ${COMMIT:0:12} нет .sha256 — непроверенную не ставим"
    (cd "$TMP_DIR" && sha256sum -c --quiet "$NAME.sha256") || die_code 1 "контрольная сумма не совпала"
    info "Контрольная сумма: ок"
  else
    curl -fsSL "$BASE/$NAME" -o "$ARCHIVE" || die "не удалось скачать релиз $TAG (нет такого тега или нет доступа к GitHub)"
    if curl -fsSL "$BASE/$NAME.sha256" -o "$TMP_DIR/$NAME.sha256"; then
      (cd "$TMP_DIR" && sha256sum -c --quiet "$NAME.sha256") || die "контрольная сумма не совпала"
      info "Контрольная сумма: ок"
    else
      info "Файл .sha256 не найден — пропускаю проверку суммы"
    fi
  fi
fi

[[ -f "$ARCHIVE" ]] || die "нет файла $ARCHIVE"
tar tzf "$ARCHIVE" >/dev/null 2>&1 || die "не удалось прочитать архив $ARCHIVE"
validate_archive

EXTRACT="$TMP_DIR/extract"
mkdir -p "$EXTRACT"
tar xzf "$ARCHIVE" -C "$EXTRACT"
NEW_DIST="$EXTRACT/frontend/dist"
NEW_TG_MINI="$EXTRACT/backend/app/static/tg_mini"
[[ -f "$NEW_DIST/index.html" ]] || die "в архиве нет frontend/dist/index.html"
[[ -f "$NEW_DIST/.vite/manifest.json" ]] || die "в архиве нет frontend/dist/.vite/manifest.json (нужен для публичных ассетов портала)"
[[ -f "$NEW_TG_MINI/index.html" ]] || die "в архиве нет backend/app/static/tg_mini/index.html"

BUILT_COMMIT="$(sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]*\)".*/\1/p' \
  "$NEW_DIST/.build-info.json" 2>/dev/null | head -n1)"
HEAD_COMMIT="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
EXPECTED_COMMIT="${COMMIT:-$HEAD_COMMIT}"
if [[ -z "$BUILT_COMMIT" ]]; then
  # В канале по коммиту подпись обязательна: без неё нельзя доказать, что сборка от этого кода.
  [[ -z "$COMMIT" ]] || die_code 1 "в сборке нет .build-info.json — коммит не проверить"
  info "В сборке нет .build-info.json — коммит не проверить"
elif [[ "$BUILT_COMMIT" != "$EXPECTED_COMMIT" ]]; then
  if [[ "$FORCE" != true ]]; then
    if [[ -n "$COMMIT" ]]; then
      die_code 1 "сборка для коммита ${BUILT_COMMIT:0:12}, запрошен ${EXPECTED_COMMIT:0:12}"
    fi
    die "сборка для коммита ${BUILT_COMMIT:0:12}, а на сервере ${EXPECTED_COMMIT:0:12}: обновите код или добавьте --force"
  fi
  info "ВНИМАНИЕ: сборка для коммита ${BUILT_COMMIT:0:12}, на сервере ${EXPECTED_COMMIT:0:12} (--force)"
else
  info "Коммит сборки совпадает с HEAD (${EXPECTED_COMMIT:0:12})"
fi

# Подмена: сначала копия в соседний каталог на том же разделе, затем два переименования.
stage_dir() {
  local src="$1" dest="$2"
  rm -rf "$dest"
  cp -a "$src" "$dest"
}

swap_dir() {
  local staged="$1" target="$2" old="$2.old"
  [[ -f "$staged/index.html" ]] || die "в $staged нет index.html"
  rm -rf "$old"
  if [[ -d "$target" ]]; then
    mv "$target" "$old"
  fi
  if ! mv "$staged" "$target"; then
    if [[ -d "$old" ]]; then
      mv "$old" "$target"
    fi
    die "не удалось подменить $target"
  fi
  rm -rf "$old"
}

info "Подмена frontend/dist…"
stage_dir "$NEW_DIST" "$FRONTEND_DIR/dist.next"
swap_dir "$FRONTEND_DIR/dist.next" "$FRONTEND_DIR/dist"

info "Подмена tg_mini…"
stage_dir "$NEW_TG_MINI" "$TG_MINI_DIR.next"
swap_dir "$TG_MINI_DIR.next" "$TG_MINI_DIR"

chown -R "$(stat -c '%u:%g' "$INSTALL_DIR")" "$FRONTEND_DIR/dist" "$TG_MINI_DIR"
find "$FRONTEND_DIR/dist" "$TG_MINI_DIR" -type d -exec chmod 755 {} +
find "$FRONTEND_DIR/dist" "$TG_MINI_DIR" -type f -exec chmod 644 {} +

info "Интерфейс обновлён: $(du -sh "$FRONTEND_DIR/dist" | cut -f1) frontend/dist, $(du -sh "$TG_MINI_DIR" | cut -f1) tg_mini"

if [[ "$RESTART" == true ]]; then
  info "Перезапуск $SERVICE_NAME…"
  systemctl restart "$SERVICE_NAME" || die "systemctl restart $SERVICE_NAME завершился ошибкой"
  sleep 1
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Готово: $SERVICE_NAME перезапущен"
  else
    die "$SERVICE_NAME не активен после перезапуска — проверьте: journalctl -u $SERVICE_NAME -n 50"
  fi
else
  info "Перезапуск пропущен (--no-restart): sudo systemctl restart $SERVICE_NAME"
fi
