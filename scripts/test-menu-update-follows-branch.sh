#!/usr/bin/env bash
# Обновление из консольного меню следует тем же правилам ветки, что и обновление из панели (node_update.py):
# ветка обновляется из своего upstream, `main` без upstream — из origin/main, detached HEAD и ветка без upstream
# не обновляются, сброс после переписанной истории — только на upstream той же ветки и только если все
# локальные коммиты уже есть на сервере git.
# shellcheck disable=SC2016
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
AFTER_LOG="$TMP/after-pull.log"
RELEASE="release/9.9.9"
UNPUSHED="В локальной ветке есть коммиты, которых нет на сервере git"

git_q() { git -c init.defaultBranch=main "$@" >/dev/null 2>&1; }
rev() { git -C "$1" rev-parse "$2"; }
git_identity() { git -C "$1" config user.email t@t && git -C "$1" config user.name t; }

# Репозиторий «origin» с main и веткой релиза, рабочая копия разработчика и установка.
# Меню в репозитории — заглушка: отмечает, что шаги после обновления кода запущены.
setup_repos() {
  rm -rf "${TMP:?}/origin.git" "${TMP:?}/install" "${TMP:?}/dev"
  git_q init --bare "$TMP/origin.git"
  git_q clone "$TMP/origin.git" "$TMP/dev"
  git_identity "$TMP/dev"
  mkdir -p "$TMP/dev/scripts"
  printf '#!/usr/bin/env bash\necho "after $*" >>"$AFTER_LOG"\n' >"$TMP/dev/scripts/adminpanel-menu.sh"
  echo base >"$TMP/dev/version"
  git_q -C "$TMP/dev" add -A
  git_q -C "$TMP/dev" commit -m base
  git_q -C "$TMP/dev" push origin HEAD:main
  git_q -C "$TMP/dev" push origin "HEAD:refs/heads/$RELEASE"
  git_q clone "$TMP/origin.git" "$TMP/install"
  git_identity "$TMP/install"
  : >"$AFTER_LOG"
}

# local_commit — коммит в установке, которого нет на origin
local_commit() {
  echo "local $RANDOM" >"$TMP/install/local"
  git_q -C "$TMP/install" add local
  git_q -C "$TMP/install" commit -m local
}

# upstream_commit <ветка> — новый коммит в ветку на origin
upstream_commit() {
  git_q -C "$TMP/dev" fetch origin
  git_q -C "$TMP/dev" checkout -B "$1" "origin/$1"
  echo "$1 $RANDOM" >"$TMP/dev/version"
  git_q -C "$TMP/dev" commit -am "next $1"
  git_q -C "$TMP/dev" push origin "HEAD:refs/heads/$1"
}

checkout_release() {
  git_q -C "$TMP/install" fetch origin
  git_q -C "$TMP/install" checkout -b "$RELEASE" --track "origin/$RELEASE"
}

# run_update [аргумент меню] — panel_update, с аргументом — main "$@" (как `adminpanel-menu.sh --update`).
# GIT_STATUS_FAILS=1 — `git status` завершается ошибкой.
run_update() {
  AFTER_LOG="$AFTER_LOG" INSTALL_DIR="$TMP/install" VENV_PATH="$TMP/no-venv" \
    GIT_STATUS_FAILS="${GIT_STATUS_FAILS:-}" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    shift
    require_root() { :; }
    if [[ -n "$GIT_STATUS_FAILS" ]]; then
      git() { if [[ " $* " == *" status "* ]]; then return 128; fi; command git "$@"; }
    fi
    if [[ $# -gt 0 ]]; then main "$@"; else panel_update; fi
  ' bash "$ROOT_DIR" "$@"
}

# run_update_rc [аргумент меню] — запуск с сохранением кода возврата в $rc и вывода в $TMP/out
run_update_rc() {
  set +e
  run_update "$@" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

fail() {
  echo "  FAIL $*" >&2
  [[ -f "$TMP/out" ]] && sed 's/^/    | /' "$TMP/out" >&2
  exit 1
}

is_ancestor() { git -C "$TMP/install" merge-base --is-ancestor "$1" "$2"; }
# diverged_from_origin <коммит> — HEAD установки не предок коммита (в origin есть обе истории)
diverged_from_origin() {
  local head
  head="$(rev "$TMP/install" HEAD)"
  git -C "$TMP/origin.git" cat-file -e "$head^{commit}" && \
    ! git -C "$TMP/origin.git" merge-base --is-ancestor "$head" "$1"
}

echo "[test] ветка релиза с upstream: fast-forward из своего upstream, коммиты main не приходят"
setup_repos
checkout_release
upstream_commit main
upstream_commit "$RELEASE"
main_tip="$(rev "$TMP/origin.git" main)"
release_tip="$(rev "$TMP/origin.git" "$RELEASE")"
run_update_rc
[[ "$rc" == 0 ]] || fail "обновление завершилось ошибкой ($rc)"
[[ "$(git -C "$TMP/install" branch --show-current)" == "$RELEASE" ]] || fail "ветка сменилась"
[[ "$(rev "$TMP/install" HEAD)" == "$release_tip" ]] || fail "ветка не на вершине своего upstream"
! is_ancestor "$main_tip" HEAD || fail "в ветку релиза попал коммит main"
grep -q "Код обновлён" "$TMP/out" || fail "нет сообщения «Код обновлён»"
[[ "$(cat "$AFTER_LOG")" == "after --after-pull" ]] || fail "шаги после обновления не запущены: $(cat "$AFTER_LOG")"
echo "  OK"

echo "[test] ветка релиза актуальна, в main новый коммит: «актуален», ничего не меняется"
setup_repos
checkout_release
upstream_commit main
before="$(rev "$TMP/install" HEAD)"
run_update_rc
[[ "$rc" == 0 ]] || fail "обновление завершилось ошибкой ($rc)"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "HEAD изменился"
grep -q "Репозиторий актуален" "$TMP/out" || fail "нет сообщения «Репозиторий актуален»"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены без обновления"
echo "  OK"

echo "[test] main без upstream обновляется с origin/main"
setup_repos
git_q -C "$TMP/install" branch --unset-upstream main
upstream_commit main
upstream_commit "$RELEASE"
run_update_rc
[[ "$rc" == 0 ]] || fail "обновление завершилось ошибкой ($rc)"
[[ "$(git -C "$TMP/install" branch --show-current)" == main ]] || fail "ветка сменилась"
[[ "$(rev "$TMP/install" HEAD)" == "$(rev "$TMP/origin.git" main)" ]] || fail "main не на вершине origin/main"
echo "  OK"

echo "[test] --update на main: код возврата 0 после обновления, ненулевой при отказе"
setup_repos
upstream_commit main
run_update_rc --update
[[ "$rc" == 0 ]] || fail "--update завершился ошибкой ($rc)"
[[ "$(rev "$TMP/install" HEAD)" == "$(rev "$TMP/origin.git" main)" ]] || fail "main не на вершине origin/main"
[[ "$(cat "$AFTER_LOG")" == "after --after-pull" ]] || fail "шаги после обновления не запущены"
local_commit
upstream_commit main
run_update_rc --update
[[ "$rc" != 0 ]] || fail "--update с неотправленным коммитом при расхождении завершился без ошибки"
grep -qF "$UNPUSHED" "$TMP/out" || fail "нет объяснения про коммиты, которых нет на сервере"
echo "  OK"

echo "[test] только локальные коммиты (без отставания): «актуален», коммиты на месте"
setup_repos
checkout_release
local_commit
before="$(rev "$TMP/install" HEAD)"
run_update_rc
[[ "$rc" == 0 ]] || fail "обновление завершилось ошибкой ($rc)"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "HEAD изменился"
grep -q "Репозиторий актуален" "$TMP/out" || fail "нет сообщения «Репозиторий актуален»"
grep -qF "Локальных коммитов, которых нет в origin/$RELEASE: 1" "$TMP/out" || fail "нет сообщения о локальных коммитах"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены без обновления"
echo "  OK"

echo "[test] detached HEAD: отказ с объяснением, рабочая копия не меняется"
setup_repos
git_q -C "$TMP/install" checkout --detach
upstream_commit main
upstream_commit "$RELEASE"
before="$(rev "$TMP/install" HEAD)"
run_update_rc
[[ "$rc" != 0 ]] || fail "обновление в detached HEAD прошло без ошибки"
grep -q "detached HEAD" "$TMP/out" || fail "нет объяснения про detached HEAD"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "HEAD изменился"
! git -C "$TMP/install" symbolic-ref -q HEAD >/dev/null || fail "рабочая копия переключена на ветку"
[[ -z "$(git -C "$TMP/install" status --porcelain)" ]] || fail "рабочая копия изменена"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены"
echo "  OK"

echo "[test] ветка без upstream: отказ с подсказкой git branch -u, рабочая копия не меняется"
setup_repos
git_q -C "$TMP/install" checkout -b feature
upstream_commit main
before="$(rev "$TMP/install" HEAD)"
run_update_rc
[[ "$rc" != 0 ]] || fail "обновление ветки без upstream прошло без ошибки"
grep -q "У ветки feature нет upstream" "$TMP/out" || fail "нет объяснения про upstream"
grep -qF "git branch -u origin/feature" "$TMP/out" || fail "нет подсказки git branch -u"
[[ "$(git -C "$TMP/install" branch --show-current)" == feature ]] || fail "ветка сменилась"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "HEAD изменился"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены"
echo "  OK"

# rewrite_release — на origin история ветки релиза переписана (force-push), в main тоже новый коммит
rewrite_release() {
  git_q -C "$TMP/dev" fetch origin
  git_q -C "$TMP/dev" checkout -B "$RELEASE" "origin/$RELEASE"
  git_q -C "$TMP/dev" reset --hard HEAD~1
  echo "rewritten $RANDOM" >"$TMP/dev/version"
  git_q -C "$TMP/dev" commit -am rewritten
  git_q -C "$TMP/dev" push -f origin "HEAD:refs/heads/$RELEASE"
  upstream_commit main
}

echo "[test] переписанная история, чистое дерево: reset --hard на upstream той же ветки, не на main"
setup_repos
upstream_commit "$RELEASE"
checkout_release
rewrite_release
release_tip="$(rev "$TMP/origin.git" "$RELEASE")"
main_tip="$(rev "$TMP/origin.git" main)"
diverged_from_origin "$release_tip" || fail "история не расходится — проверка сброса ничего не проверяет"
run_update_rc
[[ "$rc" == 0 ]] || fail "обновление завершилось ошибкой ($rc)"
[[ "$(git -C "$TMP/install" branch --show-current)" == "$RELEASE" ]] || fail "ветка сменилась"
[[ "$(rev "$TMP/install" HEAD)" == "$release_tip" ]] || fail "ветка не сброшена на свой upstream"
! is_ancestor "$main_tip" HEAD || fail "ветка релиза сброшена на main"
grep -qF "История переписана: reset --hard origin/$RELEASE" "$TMP/out" || fail "нет сообщения о сбросе"
[[ "$(cat "$AFTER_LOG")" == "after --after-pull" ]] || fail "шаги после обновления не запущены"
echo "  OK"

echo "[test] переписанная история, локальные изменения: отказ, ничего не сбрасывается"
setup_repos
upstream_commit "$RELEASE"
checkout_release
rewrite_release
before="$(rev "$TMP/install" HEAD)"
diverged_from_origin "$(rev "$TMP/origin.git" "$RELEASE")" || fail "история не расходится"
echo local-edit >>"$TMP/install/version"
run_update_rc
[[ "$rc" != 0 ]] || fail "обновление с локальными изменениями прошло без ошибки"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "HEAD изменился"
grep -q local-edit "$TMP/install/version" || fail "локальные изменения потеряны"
! grep -q "Код обновлён" "$TMP/out" || fail "сообщено «Код обновлён»"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены"
echo "  OK"

echo "[test] расхождение с неотправленным локальным коммитом, чистое дерево: отказ, коммит сохранён"
setup_repos
checkout_release
local_commit
upstream_commit "$RELEASE"
before="$(rev "$TMP/install" HEAD)"
run_update_rc
[[ "$rc" != 0 ]] || fail "обновление с неотправленным коммитом прошло без ошибки"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "локальный коммит потерян"
grep -qF "$UNPUSHED" "$TMP/out" || fail "нет объяснения про коммиты, которых нет на сервере"
! grep -q "Код обновлён" "$TMP/out" || fail "сообщено «Код обновлён»"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены"
echo "  OK"

echo "[test] переписанная история и неотправленный коммит поверх неё: отказ, коммит сохранён"
setup_repos
upstream_commit "$RELEASE"
checkout_release
local_commit
rewrite_release
before="$(rev "$TMP/install" HEAD)"
run_update_rc
[[ "$rc" != 0 ]] || fail "обновление с неотправленным коммитом прошло без ошибки"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "локальный коммит потерян"
grep -qF "$UNPUSHED" "$TMP/out" || fail "нет объяснения про коммиты, которых нет на сервере"
echo "  OK"

echo "[test] переписанная история, локальные коммиты есть в другой ветке origin: reset --hard"
setup_repos
upstream_commit "$RELEASE"
checkout_release
git_q -C "$TMP/dev" push origin "origin/$RELEASE:refs/heads/backup"
rewrite_release
release_tip="$(rev "$TMP/origin.git" "$RELEASE")"
run_update_rc
[[ "$rc" == 0 ]] || fail "обновление завершилось ошибкой ($rc)"
[[ "$(rev "$TMP/install" HEAD)" == "$release_tip" ]] || fail "ветка не сброшена на свой upstream"
echo "  OK"

echo "[test] git status завершился ошибкой: дерево считается изменённым, сброса нет"
setup_repos
upstream_commit "$RELEASE"
checkout_release
rewrite_release
before="$(rev "$TMP/install" HEAD)"
GIT_STATUS_FAILS=1 run_update_rc
[[ "$rc" != 0 ]] || fail "обновление при сбое git status прошло без ошибки"
[[ "$(rev "$TMP/install" HEAD)" == "$before" ]] || fail "HEAD сброшен при сбое git status"
[[ ! -s "$AFTER_LOG" ]] || fail "шаги после обновления запущены"
echo "  OK"

echo "[test] интерактивное меню: отказ обновления не закрывает меню"
setup_repos
git_q -C "$TMP/install" checkout --detach
set +e
AFTER_LOG="$AFTER_LOG" INSTALL_DIR="$TMP/install" VENV_PATH="$TMP/no-venv" bash -c '
  set -euo pipefail
  source "$1/scripts/adminpanel-menu.sh"
  require_root() { :; }
  menu_action panel_update
  echo "menu alive"
' bash "$ROOT_DIR" </dev/null >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" == 0 ]] || fail "меню завершилось после отказа ($rc)"
grep -q "detached HEAD" "$TMP/out" || fail "нет объяснения отказа"
grep -q "menu alive" "$TMP/out" || fail "меню не продолжило работу"
echo "  OK"

echo "All menu branch update checks passed."
