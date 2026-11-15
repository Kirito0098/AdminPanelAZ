#!/usr/bin/env bash
# Ставит интерфейс панели и Mini App, собранный в CI (GitHub Release), без npm и Node на сервере.
# Распаковывает в соседние каталоги и подменяет двумя переименованиями: при сбое старый интерфейс цел.
# Сборка из релиза помнит свой коммит (frontend/dist/.build-info.json) — чужой коммит не ставится без --force.
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
GITHUB_REPO="${GITHUB_REPO:-Kirito0098/AdminPanelAZ}"
INSTALL_DIR="${INSTALL_DIR:-/opt/AdminPanelAZ}"
TAG=""
ARCHIVE=""
FORCE=false
RESTART=true

usage() {
  cat <<'EOF'
Usage: panel-frontend-deploy.sh [--tag vX.Y.Z | --file path.tar.gz] [опции]

  --tag TAG       тег релиза на GitHub (по умолчанию — тег текущего HEAD)
  --file PATH     готовый tar.gz (офлайн, scp с другой машины)
  --repo OWNER/REPO  репозиторий релизов (по умолчанию Kirito0098/AdminPanelAZ)
  --dir PATH      каталог установки (по умолчанию /opt/AdminPanelAZ)
  --force         ставить сборку, даже если она для другого коммита
  --no-restart    не перезапускать панель
  -h, --help      эта справка
EOF
}

die() {
  echo "ОШИБКА: $*" >&2
  exit 1
}

info() {
  echo "$*"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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
[[ -d "$INSTALL_DIR/.git" ]] || die "не найден git-репозиторий в $INSTALL_DIR"

if [[ -z "$ARCHIVE" && -z "$TAG" ]]; then
  TAG="$(git -C "$INSTALL_DIR" describe --tags --exact-match 2>/dev/null)" \
    || die "HEAD не на теге — укажите --tag vX.Y.Z или --file path.tar.gz"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
chmod 755 "$TMP_DIR"

if [[ -z "$ARCHIVE" ]]; then
  [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]] || die "ожидается тег вида vX.Y.Z, получено: $TAG"
  command -v curl >/dev/null 2>&1 || die "нужен curl (или передайте --file)"
  NAME="adminpanelaz-frontend-$TAG.tar.gz"
  BASE="https://github.com/$GITHUB_REPO/releases/download/$TAG"
  ARCHIVE="$TMP_DIR/$NAME"
  info "Скачивание $BASE/$NAME…"
  curl -fsSL "$BASE/$NAME" -o "$ARCHIVE" || die "не удалось скачать релиз $TAG (нет такого тега или нет доступа к GitHub)"
  if curl -fsSL "$BASE/$NAME.sha256" -o "$TMP_DIR/$NAME.sha256"; then
    (cd "$TMP_DIR" && sha256sum -c --quiet "$NAME.sha256") || die "контрольная сумма не совпала"
    info "Контрольная сумма: ок"
  else
    info "Файл .sha256 не найден — пропускаю проверку суммы"
  fi
fi

[[ -f "$ARCHIVE" ]] || die "нет файла $ARCHIVE"
tar tzf "$ARCHIVE" >/dev/null 2>&1 || die "не удалось прочитать архив $ARCHIVE"

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
if [[ -z "$BUILT_COMMIT" ]]; then
  info "В сборке нет .build-info.json — коммит не проверить"
elif [[ "$BUILT_COMMIT" != "$HEAD_COMMIT" ]]; then
  if [[ "$FORCE" != true ]]; then
    die "сборка для коммита ${BUILT_COMMIT:0:12}, а на сервере ${HEAD_COMMIT:0:12}: обновите код или добавьте --force"
  fi
  info "ВНИМАНИЕ: сборка для коммита ${BUILT_COMMIT:0:12}, на сервере ${HEAD_COMMIT:0:12} (--force)"
else
  info "Коммит сборки совпадает с HEAD (${HEAD_COMMIT:0:12})"
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
