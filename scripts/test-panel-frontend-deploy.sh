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
# curl — отдаёт файлы из $CURL_FILES по имени из URL, иначе 404 (как GitHub без ассета).
cat >"$BIN/curl" <<'EOF'
#!/usr/bin/env bash
url="" out=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --max-time) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
name="${url##*/}"
echo "$url" >>"$CURL_LOG"
[[ -f "$CURL_FILES/$name" ]] || exit 22
cp "$CURL_FILES/$name" "$out"
EOF
chmod +x "$BIN/id" "$BIN/systemctl" "$BIN/curl"
SYSTEMCTL_LOG="$TMP/systemctl.log"
CURL_LOG="$TMP/curl.log"
CURL_FILES="$TMP/curl-files"
mkdir -p "$CURL_FILES"
export SYSTEMCTL_LOG CURL_LOG CURL_FILES
# Ожидание свежей сборки в тестах не нужно: одна попытка без паузы.
export FRONTEND_ARTIFACT_ATTEMPTS=1 FRONTEND_ARTIFACT_RETRY_DELAY=0
unset GITHUB_REPO
PATH="$BIN:$PATH"

git_q() { git -c user.email=t@t -c user.name=t -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

# install_tree — установка с уже собранным старым интерфейсом; «GitHub» очищается
install_tree() {
  rm -rf "${TMP:?}/install" "${TMP:?}/curl-files"
  mkdir -p "$TMP/curl-files"
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

# publish_asset <имя> — кладёт архив и его .sha256 в «GitHub» (каталог для стаба curl)
publish_asset() {
  local name="$1"
  cp "$TMP/$name" "$CURL_FILES/$name"
  (cd "$CURL_FILES" && sha256sum "$name" >"$name.sha256")
}

channel_url() {
  echo "releases/download/frontend-builds/adminpanelaz-frontend-$(head_commit).tar.gz"
}

echo "[test] канал по коммиту: ассет скачивается по sha из frontend-builds, каталоги подменяются"
install_tree
git_q -C "$TMP/install" remote add origin https://github.com/owner/repo.git
make_archive "$(head_commit)" "adminpanelaz-frontend-$(head_commit).tar.gz"
publish_asset "adminpanelaz-frontend-$(head_commit).tar.gz"
: >"$CURL_LOG"
bash "$SCRIPT" --commit HEAD --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1 \
  || fail "канал не сработал: $(cat "$TMP/out")"
grep -q "$(channel_url)" "$CURL_LOG" || fail "неверный URL канала: $(cat "$CURL_LOG")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == new ]] || fail "dist не обновлён из канала"
[[ "$(cat "$TMP/install/backend/app/static/tg_mini/index.html")" == new ]] || fail "tg_mini не обновлён из канала"
echo "  OK"

echo "[test] канал: сборки для коммита нет — код 3, старый интерфейс цел"
install_tree
git_q -C "$TMP/install" remote add origin https://github.com/owner/repo.git
set +e
bash "$SCRIPT" --commit HEAD --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 3 ]] || fail "ожидался код 3 (нет сборки), получен $rc: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == old ]] || fail "интерфейс подменён без сборки"
echo "  OK"

echo "[test] канал: у ассета нет .sha256 — отказ (код 1), сборка не ставится"
install_tree
git_q -C "$TMP/install" remote add origin https://github.com/owner/repo.git
make_archive "$(head_commit)" "adminpanelaz-frontend-$(head_commit).tar.gz"
cp "$TMP/adminpanelaz-frontend-$(head_commit).tar.gz" "$CURL_FILES/"
set +e
bash "$SCRIPT" --commit HEAD --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 1 ]] || fail "ожидался код 1 (нет суммы), получен $rc: $(cat "$TMP/out")"
grep -q "sha256" "$TMP/out" || fail "нет объяснения про сумму: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == old ]] || fail "интерфейс подменён без проверки суммы"
echo "  OK"

echo "[test] канал: контрольная сумма не совпала — отказ (код 1)"
install_tree
git_q -C "$TMP/install" remote add origin https://github.com/owner/repo.git
make_archive "$(head_commit)" "adminpanelaz-frontend-$(head_commit).tar.gz"
cp "$TMP/adminpanelaz-frontend-$(head_commit).tar.gz" "$CURL_FILES/"
printf '%s  %s\n' "0000000000000000000000000000000000000000000000000000000000000000" \
  "adminpanelaz-frontend-$(head_commit).tar.gz" >"$CURL_FILES/adminpanelaz-frontend-$(head_commit).tar.gz.sha256"
set +e
bash "$SCRIPT" --commit HEAD --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 1 ]] || fail "ожидался код 1 (сумма не совпала), получен $rc: $(cat "$TMP/out")"
echo "  OK"

echo "[test] канал: origin не на github.com — код 4 (Gitea-зеркало, локальный клон)"
install_tree
set +e
bash "$SCRIPT" --commit HEAD --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 4 ]] || fail "ожидался код 4 (нет канала), получен $rc: $(cat "$TMP/out")"
grep -q "github.com" "$TMP/out" || fail "нет объяснения про origin: $(cat "$TMP/out")"
echo "  OK"

echo "[test] архив: симлинк отклоняется до подмены"
install_tree
rm -rf "${TMP:?}/build-link"
mkdir -p "$TMP/build-link/frontend/dist/.vite" "$TMP/build-link/backend/app/static/tg_mini"
echo new >"$TMP/build-link/frontend/dist/index.html"
echo '{}' >"$TMP/build-link/frontend/dist/.vite/manifest.json"
printf '{"commit":"%s"}\n' "$(head_commit)" >"$TMP/build-link/frontend/dist/.build-info.json"
ln -s /etc/passwd "$TMP/build-link/frontend/dist/evil"
echo new >"$TMP/build-link/backend/app/static/tg_mini/index.html"
tar czf "$TMP/link.tar.gz" -C "$TMP/build-link" frontend/dist backend/app/static/tg_mini
set +e
bash "$SCRIPT" --file "$TMP/link.tar.gz" --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 1 ]] || fail "архив с симлинком принят: $(cat "$TMP/out")"
grep -q "симлинк" "$TMP/out" || fail "нет объяснения про ссылку: $(cat "$TMP/out")"
[[ "$(cat "$TMP/install/frontend/dist/index.html")" == old ]] || fail "интерфейс подменён архивом с симлинком"
echo "  OK"

echo "[test] архив: посторонний путь отклоняется до подмены"
install_tree
make_archive "$(head_commit)" plain.tar.gz
rm -rf "${TMP:?}/build-extra"
mkdir -p "$TMP/build-extra"
cp -a "${TMP:?}/build/." "$TMP/build-extra/"
echo x >"$TMP/build-extra/README"
tar czf "$TMP/extra.tar.gz" -C "$TMP/build-extra" frontend/dist backend/app/static/tg_mini README
set +e
bash "$SCRIPT" --file "$TMP/extra.tar.gz" --dir "$TMP/install" --no-restart >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 1 ]] || fail "архив с посторонним путём принят: $(cat "$TMP/out")"
grep -q "неожиданный путь" "$TMP/out" || fail "нет объяснения про путь: $(cat "$TMP/out")"
echo "  OK"

echo "All frontend deploy checks passed."
