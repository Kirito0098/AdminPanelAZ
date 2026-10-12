#!/usr/bin/env bash
# Установщик должен ставить поддерживаемую LTS-версию Node.js: Node 20 больше не получает
# обновлений безопасности, и на нём установка не должна считаться завершённой.
# NodeSource подключается apt-репозиторием с ключом, сверенным по отпечатку, без curl | bash.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export LOG="$TMP/calls.log" NODE_VERSION_FILE="$TMP/node-version" NPM_FILE="$TMP/npm-present"
export NODESOURCE_KEYRING="$TMP/keyrings/nodesource.gpg"
export NODESOURCE_APT_SOURCES="$TMP/apt/sources.list.d/nodesource.sources"
export NODESOURCE_APT_PIN="$TMP/apt/preferences.d/nodejs"
NODESOURCE_FPR="6F71F525282841EEDAF851B42F59B5F99B1BE0B4"

FNS="$(grep -E '^(NODE_(MIN|INSTALL)_MAJOR|NODESOURCE_[A-Z_]+)=' "$ROOT_DIR/install.sh")"$'\n'"$(
  for fn in node_major_version node_apt_candidate_major nodesource_add_repo install_nodejs; do
    sed -n "/^${fn}() {/,/^}/p" "$ROOT_DIR/install.sh"
  done
)"

# run_install <node до установки|none> <кандидат apt|none> <node после установки> [npm в пакете nodejs] [отпечаток ключа]
run_install() {
  local before="$1" candidate="$2" after="$3" npm_bundled="${4:-true}" fpr="${5:-$NODESOURCE_FPR}"
  : >"$LOG"
  rm -f "$NPM_FILE"
  rm -rf "$TMP/apt" "$TMP/keyrings"
  mkdir -p "$TMP/apt/sources.list.d" "$TMP/apt/preferences.d"
  printf 'deb https://deb.nodesource.com/node_20.x nodistro main\n' >"$TMP/apt/sources.list.d/nodesource.list"
  if [[ "$before" == none ]]; then rm -f "$NODE_VERSION_FILE"; else echo "$before" >"$NODE_VERSION_FILE"; fi
  CANDIDATE="$candidate" AFTER="$after" NPM_BUNDLED="$npm_bundled" KEY_FPR="$fpr" TMP="$TMP" bash -c '
    set -euo pipefail
    log() { echo "LOG $*" >>"$LOG"; }
    warn() { echo "WARN $*" >>"$LOG"; }
    die() { echo "DIE $*" >>"$LOG"; exit 1; }
    command() {
      if [[ "$1" == -v && "$2" == node ]]; then [[ -f "$NODE_VERSION_FILE" ]]; return; fi
      if [[ "$1" == -v && "$2" == npm ]]; then [[ -f "$NPM_FILE" ]]; return; fi
      builtin command "$@"
    }
    node() { cat "$NODE_VERSION_FILE"; }
    apt-cache() {
      echo "apt-cache $*" >>"$LOG"
      echo "nodejs:"
      echo "  Installed: (none)"
      [[ "$CANDIDATE" == none ]] && echo "  Candidate: (none)" || echo "  Candidate: $CANDIDATE"
    }
    # Пакет nodejs NodeSource содержит npm, пакет Debian — нет.
    apt-get() {
      echo "apt-get $*" >>"$LOG"
      if [[ " $* " == *" nodejs "* ]]; then
        echo "$AFTER" >"$NODE_VERSION_FILE"
        [[ "$NPM_BUNDLED" != true ]] || : >"$NPM_FILE"
      fi
      [[ " $* " != *" npm "* ]] || : >"$NPM_FILE"
    }
    curl() { echo "curl $*" >>"$LOG"; echo "true"; }
    gpg() {
      echo "gpg $*" >>"$LOG"
      if [[ " $* " == *" --show-keys "* ]]; then
        echo "pub:-:2048:1:2F59B5F99B1BE0B4:1464022864:::-:::scESC::::::23::0:"
        echo "fpr:::::::::${KEY_FPR}:"
        echo "fpr:::::::::0FA5ECC8C0CA58863C0AC5867E9656125E955B26:"
      elif [[ " $* " == *" --dearmor "* ]]; then
        local out=""
        while [[ $# -gt 0 ]]; do
          [[ "$1" == -o ]] && out="$2"
          shift
        done
        echo dearmored >"$out"
      fi
    }
    eval "$1"
    # Предохранитель: файлы apt и keyring пишутся только во временный каталог.
    for path in "$NODESOURCE_KEYRING" "$NODESOURCE_APT_SOURCES" "$NODESOURCE_APT_PIN"; do
      [[ "$path" == "$TMP"/* ]] || { echo "UNSAFE $path" >>"$LOG"; exit 1; }
    done
    install_nodejs
  ' bash "$FNS"
}

fail() {
  echo "  FAIL $*" >&2
  sed 's/^/    /' "$LOG" >&2
  exit 1
}

nodesource_repo_ok() {
  ! grep -q "setup_" "$LOG" || fail "вызван setup-скрипт NodeSource (curl | bash)"
  grep -q "^curl .*https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" "$LOG" || fail "ключ NodeSource не скачан"
  grep -qx "URIs: https://deb.nodesource.com/node_24.x" "$NODESOURCE_APT_SOURCES" || fail "не репозиторий NodeSource 24.x"
  grep -qx "Signed-By: $NODESOURCE_KEYRING" "$NODESOURCE_APT_SOURCES" || fail "репозиторий без Signed-By"
  [[ -s "$NODESOURCE_KEYRING" ]] || fail "нет keyring NodeSource"
  [[ ! -e "$TMP/apt/sources.list.d/nodesource.list" ]] || fail "старый nodesource.list не удалён"
  grep -qx "Pin: origin deb.nodesource.com" "$NODESOURCE_APT_PIN" || fail "нет приоритета NodeSource"
  [[ "$(grep "^apt-get" "$LOG")" == "apt-get update -qq"$'\n'"apt-get install -y nodejs" ]] \
    || fail "apt: сначала update с новым репозиторием, потом nodejs"
}

echo "[test] поддерживаемая LTS уже стоит — ничего не ставим"
for v in v22.12.0 v24.4.1; do
  run_install "$v" none "$v" || fail "$v отклонена"
  ! grep -q "^apt-get\|^curl" "$LOG" || fail "$v: лишняя установка"
done
echo "  OK"

echo "[test] Node 20 обновляется через репозиторий NodeSource до 24.x"
run_install v20.20.2 18.19.1+dfsg-6ubuntu5 v24.4.1 || fail "обновление не прошло"
nodesource_repo_ok
grep -q "^WARN .*v20.20.2" "$LOG" || fail "нет предупреждения про устаревшую версию"
echo "  OK"

echo "[test] нет node — ставится 24.x из репозитория NodeSource"
run_install none none v24.4.1 || fail "установка не прошла"
nodesource_repo_ok
echo "  OK"

echo "[test] apt предлагает поддерживаемую версию — ставим из apt, npm только если его нет"
run_install v20.20.2 22.12.0+dfsg-1 v22.12.0 false || fail "установка из apt Debian не прошла"
[[ "$(grep "^apt-get" "$LOG")" == "apt-get install -y nodejs"$'\n'"apt-get install -y npm" ]] \
  || fail "Debian: nodejs, затем npm отдельно"
! grep -q "^curl" "$LOG" || fail "Debian: лишний NodeSource"
[[ ! -e "$NODESOURCE_APT_SOURCES" ]] || fail "Debian: подключён репозиторий NodeSource"
run_install v20.20.2 1:24.1.0-1nodesource1 v24.1.0 true || fail "установка из apt NodeSource не прошла"
[[ "$(grep "^apt-get" "$LOG")" == "apt-get install -y nodejs" ]] \
  || fail "NodeSource: npm уже в пакете nodejs, пакет npm Debian конфликтует с ним"
! grep -q "^curl" "$LOG" || fail "NodeSource из apt: лишнее подключение репозитория"
echo "  OK"

echo "[test] apt предлагает Node 20 — не годится, репозиторий NodeSource"
run_install none 20.19.2+dfsg-1 v24.4.1 || fail "установка не прошла"
nodesource_repo_ok
echo "  OK"

echo "[test] ключ NodeSource с чужим отпечатком — репозиторий не подключается"
if run_install none none v24.4.1 true 0000000000000000000000000000000000000000; then
  fail "установка с чужим ключом прошла"
fi
grep -q "^DIE .*NodeSource" "$LOG" || fail "нет понятной ошибки"
[[ ! -e "$NODESOURCE_APT_SOURCES" && ! -e "$NODESOURCE_KEYRING" ]] || fail "репозиторий подключён с чужим ключом"
! grep -q "^apt-get install -y nodejs" "$LOG" || fail "nodejs ставился с чужим ключом"
echo "  OK"

echo "[test] после установки всё ещё старая версия — ошибка"
if run_install v20.20.2 none v20.20.2; then fail "установка со старой версией прошла"; fi
grep -q "^DIE .*22" "$LOG" || fail "нет понятной ошибки"
echo "  OK"

echo "All Node.js LTS checks passed."
