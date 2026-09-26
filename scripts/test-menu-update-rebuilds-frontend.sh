#!/usr/bin/env bash
# Обновление из консольного меню должно пересобирать интерфейс, как обновление из панели:
# иначе после git pull новый backend работает со старым собранным фронтендом.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
NPM_LOG="$TMP/npm.log"
mkdir -p "$TMP/git-only-bin" "$TMP/npm-bin"
ln -s "$(command -v git)" "$TMP/git-only-bin/git"
# npm — отдельная программа: шаги после git pull выполняет уже обновлённый скрипт в новом процессе bash.
cat >"$TMP/npm-bin/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $* @ $PWD" >>"$NPM_LOG"
[[ "$*" != "${NPM_FAIL_ON:-none}" ]]
EOF
chmod +x "$TMP/npm-bin/npm"

git_q() { git -c user.email=t@t -c user.name=t -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

# Репозиторий «origin», установка и рабочая копия разработчика для новых коммитов.
# В репозитории лежит проверяемое меню: после git pull установка запускает его с диска.
setup_repos() {
  rm -rf "${TMP:?}/origin.git" "${TMP:?}/install" "${TMP:?}/dev"
  git_q init --bare "$TMP/origin.git"
  git_q clone "$TMP/origin.git" "$TMP/dev"
  mkdir -p "$TMP/dev/frontend/src" "$TMP/dev/scripts"
  echo '{"name":"x"}' >"$TMP/dev/frontend/package.json"
  echo 'export {}' >"$TMP/dev/frontend/src/main.ts"
  cp "$ROOT_DIR/scripts/adminpanel-menu.sh" "$TMP/dev/scripts/"
  echo v1 >"$TMP/dev/version"
  git_q -C "$TMP/dev" add -A
  git_q -C "$TMP/dev" commit -m v1
  git_q -C "$TMP/dev" push origin HEAD:main
  git_q clone "$TMP/origin.git" "$TMP/install"
}

new_upstream_commit() {
  echo "v$RANDOM" >"$TMP/dev/version"
  git_q -C "$TMP/dev" commit -am next
  git_q -C "$TMP/dev" push origin HEAD:main
}

# build_dist [давность]: собранный интерфейс; по умолчанию новее всех исходников
build_dist() {
  mkdir -p "$TMP/install/frontend/dist"
  echo '<html></html>' >"$TMP/install/frontend/dist/index.html"
  touch -d "${1:-now}" "$TMP/install/frontend/dist/index.html"
  if [[ -z "${1:-}" ]]; then
    find "$TMP/install/frontend" -path "$TMP/install/frontend/dist" -prune -o -type f -exec touch -d '-1 hour' {} +
  fi
}

# run_update [npm-доступен] [функция] — функция меню (по умолчанию panel_update) в отдельном bash.
run_update() {
  local npm_available="${1:-true}" fn="${2:-panel_update}" path="$TMP/npm-bin:$PATH"
  [[ "$npm_available" == true ]] || path="$TMP/git-only-bin"
  NPM_LOG="$NPM_LOG" INSTALL_DIR="$TMP/install" VENV_PATH="$TMP/no-venv" FN="$fn" TEST_PATH="$path" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    require_root() { :; }
    panel_uses_systemd() { return 0; }
    systemctl() { echo "systemctl $*"; }
    PATH="$TEST_PATH"
    "$FN"
  ' bash "$ROOT_DIR"
}

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

echo "[test] есть обновление и собранный интерфейс: npm ci, затем build:all в frontend/"
setup_repos
build_dist
new_upstream_commit
: >"$NPM_LOG"
run_update >"$TMP/out" 2>&1 || fail "обновление завершилось ошибкой: $(cat "$TMP/out")"
[[ "$(cat "$NPM_LOG")" == "npm ci @ $TMP/install/frontend"$'\n'"npm run build:all @ $TMP/install/frontend" ]] \
  || fail "вызовы npm: $(cat "$NPM_LOG")"
grep -q "Перезапустите панель" "$TMP/out" || fail "нет подсказки про перезапуск"
echo "  OK"

echo "[test] интерфейс здесь не собирался (сервер только с агентом): npm не вызывается"
setup_repos
new_upstream_commit
: >"$NPM_LOG"
run_update >"$TMP/out" 2>&1 || fail "обновление завершилось ошибкой"
[[ ! -s "$NPM_LOG" ]] || fail "npm вызван без frontend/dist: $(cat "$NPM_LOG")"
run_update >"$TMP/out" 2>&1 || fail "повторное обновление завершилось ошибкой"
[[ ! -s "$NPM_LOG" ]] || fail "npm вызван без frontend/dist при актуальном репозитории: $(cat "$NPM_LOG")"
run_update true panel_restart >"$TMP/out" 2>&1 || fail "перезапуск завершился ошибкой"
! grep -q -- "--update" "$TMP/out" || fail "без frontend/dist предложена пересборка: $(cat "$TMP/out")"
echo "  OK"

echo "[test] репозиторий актуален, интерфейс собран после кода: npm не вызывается"
setup_repos
build_dist
mkdir -p "$TMP/install/frontend/node_modules/x"
touch -d '+1 min' "$TMP/install/frontend/node_modules/x/index.js" "$TMP/install/frontend/.eslintcache"
: >"$NPM_LOG"
run_update >/dev/null 2>&1 || fail "обновление завершилось ошибкой"
[[ ! -s "$NPM_LOG" ]] || fail "npm вызван без обновлений (файлы вне git не считаются): $(cat "$NPM_LOG")"
echo "  OK"

echo "[test] репозиторий актуален, но интерфейс собран до обновления кода (обновление меню 2.25.1): пересборка"
setup_repos
build_dist '-2 hours'
: >"$NPM_LOG"
run_update >"$TMP/out" 2>&1 || fail "обновление завершилось ошибкой: $(cat "$TMP/out")"
[[ "$(cat "$NPM_LOG")" == "npm ci @ $TMP/install/frontend"$'\n'"npm run build:all @ $TMP/install/frontend" ]] \
  || fail "вызовы npm: $(cat "$NPM_LOG")"
grep -q "Перезапустите панель" "$TMP/out" || fail "нет подсказки про перезапуск"
rm -f "$TMP/install/frontend/dist/index.html"
: >"$NPM_LOG"
run_update >/dev/null 2>&1 || fail "обновление без index.html завершилось ошибкой"
[[ -s "$NPM_LOG" ]] || fail "нет index.html — интерфейс не пересобран"
echo "  OK"

echo "[test] интерфейс устарел, сборка не удалась: ошибка с командой для ручной пересборки"
setup_repos
build_dist '-2 hours'
set +e
NPM_FAIL_ON="run build:all" run_update >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" != 0 ]] || fail "сбой сборки не вернул ошибку"
grep -qF "cd $TMP/install/frontend && npm ci && npm run build:all" "$TMP/out" || fail "нет команды: $(cat "$TMP/out")"
! grep -q "Перезапустите панель" "$TMP/out" || fail "после сбоя предложен перезапуск"
echo "  OK"

echo "[test] после git pull шаги обновления выполняет уже обновлённый скрипт меню с диска"
setup_repos
build_dist
printf '#!/usr/bin/env bash\necho "new-menu $*" >>"$NPM_LOG"\nexit 7\n' >"$TMP/dev/scripts/adminpanel-menu.sh"
new_upstream_commit
: >"$NPM_LOG"
set +e
run_update >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$(cat "$NPM_LOG")" == "new-menu --after-pull" ]] || fail "новый скрипт не запущен: $(cat "$NPM_LOG") $(cat "$TMP/out")"
[[ "$rc" == 7 ]] || fail "код возврата нового скрипта потерян: $rc"
echo "  OK"

echo "[test] --restart предупреждает, если интерфейс собран до обновления кода"
setup_repos
build_dist '-2 hours'
: >"$NPM_LOG"
run_update true panel_restart >"$TMP/out" 2>&1 || fail "перезапуск завершился ошибкой: $(cat "$TMP/out")"
grep -q -- "--update" "$TMP/out" || fail "нет предупреждения об устаревшем интерфейсе: $(cat "$TMP/out")"
grep -q "systemctl restart adminpanelaz" "$TMP/out" || fail "панель не перезапущена"
[[ ! -s "$NPM_LOG" ]] || fail "--restart сам запустил сборку"
build_dist
run_update true panel_restart >"$TMP/out" 2>&1 || fail "перезапуск завершился ошибкой"
! grep -q -- "--update" "$TMP/out" || fail "предупреждение при актуальном интерфейсе: $(cat "$TMP/out")"
echo "  OK"

echo "[test] сборка не удалась: ошибка с командой для ручной пересборки, без подсказки про перезапуск"
for step in "ci" "run build:all"; do
  setup_repos
  build_dist
  new_upstream_commit
  : >"$NPM_LOG"
  set +e
  NPM_FAIL_ON="$step" run_update >"$TMP/out" 2>&1
  rc=$?
  set -e
  [[ "$rc" != 0 ]] || fail "сбой npm $step не вернул ошибку"
  grep -qF "cd $TMP/install/frontend && npm ci && npm run build:all" "$TMP/out" \
    || fail "нет команды для ручной пересборки: $(cat "$TMP/out")"
  ! grep -q "Перезапустите панель" "$TMP/out" || fail "после сбоя предложен перезапуск"
done
echo "  OK"

echo "[test] npm не установлен, а интерфейс собирался: ошибка"
setup_repos
build_dist
new_upstream_commit
set +e
run_update false >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" != 0 ]] || fail "без npm обновление прошло молча"
grep -q "npm" "$TMP/out" || fail "нет объяснения про npm: $(cat "$TMP/out")"
echo "  OK"

echo "All menu update checks passed."
