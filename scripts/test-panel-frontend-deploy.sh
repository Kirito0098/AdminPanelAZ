#!/usr/bin/env bash
# panel-frontend-deploy.sh ставит готовый dist из релиза: проверка коммита, подмена каталогов,
# сохранение старого интерфейса при отказе. systemctl и id подменены — на хосте ничего не трогаем.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/panel-frontend-deploy.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

BIN="$TMP/bin"
mkdir -p "$BIN"
cat >"$BIN/id" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == "-u" ]] && echo 0 || exec /usr/bin/id "$@"
EOF
cat >"$BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$SYSTEMCTL_LOG"
EOF
chmod +x "$BIN/id" "$BIN/systemctl"
SYSTEMCTL_LOG="$TMP/systemctl.log"
export SYSTEMCTL_LOG
PATH="$BIN:$PATH"

git_q() { git -c user.email=t@t -c user.name=t -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

# install_tree — установка с уже собранным старым интерфейсом
install_tree() {
  rm -rf "${TMP:?}/install"
  mkdir -p "$TMP/install/frontend/dist" "$TMP/install/backend/app/static/tg_mini"
  echo old >"$TMP/install/frontend/dist/index.html"
  echo old >"$TMP/install/frontend/dist/OLD-MARKER"
  echo old >"$TMP/install/backend/app/static/tg_mini/index.html"
  git_q init "$TMP/install"
  git_q -C "$TMP/install" commit --allow-empty -m init
}

head_commit() {
  git -C "$TMP/install" rev-parse HEAD
}

# make_archive <коммит> — tar.gz как в релизе
make_archive() {
  local commit="$1" name="$2"
  rm -rf "${TMP:?}/build"
  mkdir -p "$TMP/build/frontend/dist/.vite" "$TMP/build/backend/app/static/tg_mini"
  echo new >"$TMP/build/frontend/dist/index.html"
  echo '{}' >"$TMP/build/frontend/dist/.vite/manifest.json"
  printf '{"version":"test","commit":"%s"}\n' "$commit" >"$TMP/build/frontend/dist/.build-info.json"
  echo new >"$TMP/build/backend/app/static/tg_mini/index.html"
  tar czf "$TMP/$name" -C "$TMP/build" frontend/dist backend/app/static/tg_mini
}

echo "[test] сборка для текущего коммита: каталоги подменяются, старые файлы уходят"
install_tree
make_archive "$(head_commit)" ok.tar.gz
: >"$SYSTEMCTL_LOG"
bash "$SCRIPT" --file "$TMP/ok.tar.gz" --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1 \
  || fail "деплой завершился ошибкой: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == new ]] || fail "frontend/dist не обновлён"
[[ ! -e "$TMP/install/frontend/dist/OLD-MARKER" ]] || fail "в dist остался файл старой сборки"
[[ "$(cat "$TMP/install/backend/app/static/tg_mini/index.html")" == new ]] || fail "tg_mini не обновлён"
[[ -f "$TMP/install/frontend/dist/.build-info.json" ]] || fail "метка сборки не скопирована"
[[ ! -s "$SYSTEMCTL_LOG" ]] || fail "--no-restart перезапустил панель: $(cat "$SYSTEMCTL_LOG")"
echo "  OK"

echo "[test] сборка для другого коммита: отказ, старый интерфейс цел"
install_tree
make_archive 0000000000000000000000000000000000000000 other.tar.gz
set +e
bash "$SCRIPT" --file "$TMP/other.tar.gz" --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" != 0 ]] || fail "чужой коммит установлен без --force"
grep -q "обновите код или добавьте --force" "$TMP/out" || fail "нет объяснения про коммит: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == old ]] || fail "интерфейс подменён при отказе"
[[ -f "$TMP/install/frontend/dist/OLD-MARKER" ]] || fail "старая сборка потеряна при отказе"
echo "  OK"

echo "[test] сборка для другого коммита с --force: ставится"
install_tree
make_archive 0000000000000000000000000000000000000000 other.tar.gz
bash "$SCRIPT" --file "$TMP/other.tar.gz" --dir "$TMP/install" --force --no-restart >"$TMP/out" 2>&1 \
  || fail "деплой с --force завершился ошибкой: $(cat "$TMP/out")"
grep -q -- "--force" "$TMP/out" || fail "нет предупреждения о чужом коммите: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == new ]] || fail "интерфейс не обновлён с --force"
echo "  OK"

echo "[test] архив без manifest.json: отказ до подмены"
install_tree
make_archive "$(head_commit)" broken.tar.gz
rm -rf "${TMP:?}/build2"
mkdir -p "$TMP/build2/frontend/dist" "$TMP/build2/backend/app/static/tg_mini"
echo new >"$TMP/build2/frontend/dist/index.html"
echo new >"$TMP/build2/backend/app/static/tg_mini/index.html"
tar czf "$TMP/broken.tar.gz" -C "$TMP/build2" frontend/dist backend/app/static/tg_mini
set +e
bash "$SCRIPT" --file "$TMP/broken.tar.gz" --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" != 0 ]] || fail "архив без manifest.json принят"
grep -q "manifest.json" "$TMP/out" || fail "нет объяснения про manifest: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == old ]] || fail "интерфейс подменён без manifest"
echo "  OK"

echo "All frontend deploy checks passed."
