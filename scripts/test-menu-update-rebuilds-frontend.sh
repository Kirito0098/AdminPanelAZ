#!/usr/bin/env bash
# Обновление из консольного меню должно пересобирать интерфейс, как обновление из панели:
# иначе после git pull новый backend работает со старым собранным фронтендом.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
NPM_LOG="$TMP/npm.log"
mkdir -p "$TMP/git-only-bin"
ln -s "$(command -v git)" "$TMP/git-only-bin/git"

git_q() { git -c user.email=t@t -c user.name=t -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

# Репозиторий «origin», установка и рабочая копия разработчика для новых коммитов.
setup_repos() {
  rm -rf "${TMP:?}/origin.git" "${TMP:?}/install" "${TMP:?}/dev"
  git_q init --bare "$TMP/origin.git"
  git_q clone "$TMP/origin.git" "$TMP/dev"
  mkdir -p "$TMP/dev/frontend"
  echo '{"name":"x"}' >"$TMP/dev/frontend/package.json"
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

# run_update [npm-доступен] — panel_update в отдельном bash с подменённым npm.
run_update() {
  local npm_available="${1:-true}"
  NPM_LOG="$NPM_LOG" NPM_AVAILABLE="$npm_available" INSTALL_DIR="$TMP/install" VENV_PATH="$TMP/no-venv" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    require_root() { :; }
    if [[ "$NPM_AVAILABLE" == true ]]; then
      npm() { echo "npm $* @ $PWD" >>"$NPM_LOG"; [[ "$*" != "${NPM_FAIL_ON:-none}" ]]; }
    else
      PATH="$2"
    fi
    panel_update
  ' bash "$ROOT_DIR" "$TMP/git-only-bin"
}

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

echo "[test] есть обновление и собранный интерфейс: npm install, затем build:all в frontend/"
setup_repos
mkdir -p "$TMP/install/frontend/dist"
new_upstream_commit
: >"$NPM_LOG"
run_update >"$TMP/out" 2>&1 || fail "обновление завершилось ошибкой: $(cat "$TMP/out")"
[[ "$(cat "$NPM_LOG")" == "npm install @ $TMP/install/frontend"$'\n'"npm run build:all @ $TMP/install/frontend" ]] \
  || fail "вызовы npm: $(cat "$NPM_LOG")"
grep -q "Перезапустите панель" "$TMP/out" || fail "нет подсказки про перезапуск"
echo "  OK"

echo "[test] интерфейс здесь не собирался (сервер только с агентом): npm не вызывается"
setup_repos
new_upstream_commit
: >"$NPM_LOG"
run_update >"$TMP/out" 2>&1 || fail "обновление завершилось ошибкой"
[[ ! -s "$NPM_LOG" ]] || fail "npm вызван без frontend/dist: $(cat "$NPM_LOG")"
echo "  OK"

echo "[test] репозиторий актуален: npm не вызывается"
setup_repos
mkdir -p "$TMP/install/frontend/dist"
: >"$NPM_LOG"
run_update >/dev/null 2>&1 || fail "обновление завершилось ошибкой"
[[ ! -s "$NPM_LOG" ]] || fail "npm вызван без обновлений"
echo "  OK"

echo "[test] сборка не удалась: ошибка с командой для ручной пересборки, без подсказки про перезапуск"
for step in "install" "run build:all"; do
  setup_repos
  mkdir -p "$TMP/install/frontend/dist"
  new_upstream_commit
  : >"$NPM_LOG"
  set +e
  NPM_FAIL_ON="$step" run_update >"$TMP/out" 2>&1
  rc=$?
  set -e
  [[ "$rc" != 0 ]] || fail "сбой npm $step не вернул ошибку"
  grep -qF "cd $TMP/install/frontend && npm install && npm run build:all" "$TMP/out" \
    || fail "нет команды для ручной пересборки: $(cat "$TMP/out")"
  ! grep -q "Перезапустите панель" "$TMP/out" || fail "после сбоя предложен перезапуск"
done
echo "  OK"

echo "[test] npm не установлен, а интерфейс собирался: ошибка"
setup_repos
mkdir -p "$TMP/install/frontend/dist"
new_upstream_commit
set +e
run_update false >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" != 0 ]] || fail "без npm обновление прошло молча"
grep -q "npm" "$TMP/out" || fail "нет объяснения про npm: $(cat "$TMP/out")"
echo "  OK"

echo "All menu update checks passed."
