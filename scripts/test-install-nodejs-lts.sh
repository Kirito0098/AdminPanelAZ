#!/usr/bin/env bash
# Установщик должен ставить поддерживаемую LTS-версию Node.js: Node 20 больше не получает
# обновлений безопасности, и на нём установка не должна считаться завершённой.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export LOG="$TMP/calls.log" NODE_VERSION_FILE="$TMP/node-version"

FNS="$(grep -E '^NODE_(MIN|INSTALL)_MAJOR=' "$ROOT_DIR/install.sh")"$'\n'"$(
  for fn in node_major_version node_apt_candidate_major install_nodejs; do
    sed -n "/^${fn}() {/,/^}/p" "$ROOT_DIR/install.sh"
  done
)"

# run_install <node до установки|none> <кандидат apt|none> <node после установки>
run_install() {
  local before="$1" candidate="$2" after="$3"
  : >"$LOG"
  if [[ "$before" == none ]]; then rm -f "$NODE_VERSION_FILE"; else echo "$before" >"$NODE_VERSION_FILE"; fi
  CANDIDATE="$candidate" AFTER="$after" bash -c '
    set -euo pipefail
    log() { echo "LOG $*" >>"$LOG"; }
    warn() { echo "WARN $*" >>"$LOG"; }
    die() { echo "DIE $*" >>"$LOG"; exit 1; }
    command() {
      if [[ "$1" == -v && "$2" == node ]]; then [[ -f "$NODE_VERSION_FILE" ]]; return; fi
      builtin command "$@"
    }
    node() { cat "$NODE_VERSION_FILE"; }
    apt-cache() {
      echo "apt-cache $*" >>"$LOG"
      echo "nodejs:"
      echo "  Installed: (none)"
      [[ "$CANDIDATE" == none ]] && echo "  Candidate: (none)" || echo "  Candidate: $CANDIDATE"
    }
    apt-get() { echo "apt-get $*" >>"$LOG"; echo "$AFTER" >"$NODE_VERSION_FILE"; }
    curl() { echo "curl $*" >>"$LOG"; echo "true"; }
    eval "$1"
    install_nodejs
  ' bash "$FNS"
}

fail() {
  echo "  FAIL $*" >&2
  sed 's/^/    /' "$LOG" >&2
  exit 1
}

echo "[test] поддерживаемая LTS уже стоит — ничего не ставим"
for v in v22.12.0 v24.4.1; do
  run_install "$v" none "$v" || fail "$v отклонена"
  ! grep -q "^apt-get\|^curl" "$LOG" || fail "$v: лишняя установка"
done
echo "  OK"

echo "[test] Node 20 обновляется через NodeSource до 24.x"
run_install v20.20.2 18.19.1+dfsg-6ubuntu5 v24.4.1 || fail "обновление не прошло"
grep -q "^curl .*https://deb.nodesource.com/setup_24.x" "$LOG" || fail "не NodeSource 24.x"
grep -q "^apt-get install -y nodejs$" "$LOG" || fail "nodejs не установлен"
grep -q "^WARN .*v20.20.2" "$LOG" || fail "нет предупреждения про устаревшую версию"
echo "  OK"

echo "[test] нет node — ставится 24.x"
run_install none none v24.4.1 || fail "установка не прошла"
grep -q "setup_24.x" "$LOG" || fail "не NodeSource 24.x"
echo "  OK"

echo "[test] apt предлагает поддерживаемую версию — ставим из apt"
for candidate in 22.12.0+dfsg-1 1:24.1.0-1nodesource1; do
  run_install v20.20.2 "$candidate" v22.12.0 || fail "установка из apt ($candidate) не прошла"
  grep -q "^apt-get install -y nodejs npm$" "$LOG" || fail "$candidate: не из apt"
  ! grep -q "^curl" "$LOG" || fail "$candidate: лишний NodeSource"
done
echo "  OK"

echo "[test] apt предлагает Node 20 — не годится, NodeSource"
run_install none 20.19.2+dfsg-1 v24.4.1 || fail "установка не прошла"
grep -q "setup_24.x" "$LOG" || fail "Node 20 из apt принят"
echo "  OK"

echo "[test] после установки всё ещё старая версия — ошибка"
if run_install v20.20.2 none v20.20.2; then fail "установка со старой версией прошла"; fi
grep -q "^DIE .*22" "$LOG" || fail "нет понятной ошибки"
echo "  OK"

echo "All Node.js LTS checks passed."
