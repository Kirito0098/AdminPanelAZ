#!/usr/bin/env bash
# Мастер с -y не должен ставить пароль admin: в production он не проходит проверку
# DEFAULT_ADMIN_PASSWORD, и установка падает при первом старте панели.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

extract() {
  local file="$1" fn
  shift
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$file"
  done
}

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

INSTALL_FNS="$(extract "$ROOT_DIR/install.sh" is_placeholder_secret admin_password_is_weak generate_admin_password)"
WIZARD_DEFAULTS="$(grep -E '^WIZ_ADMIN_(USERNAME|PASSWORD|MUST_CHANGE_PASSWORD)=' "$ROOT_DIR/scripts/install-wizard.sh")"
WIZARD_FNS="$(extract "$ROOT_DIR/scripts/install-wizard.sh" wizard_ask_admin)"

strong() {
  local pw="$1"
  [[ ${#pw} -ge 12 && "$pw" =~ [A-Za-z] && "$pw" =~ [0-9] ]]
}

# run_ask_admin <accept_defaults> [stdin]; env WIZ_ADMIN_* пробрасывается как есть.
run_ask_admin() {
  local accept="$1" input="${2:-}"
  ACCEPT="$accept" bash -c '
    set -euo pipefail
    wiz_step() { :; }
    print_info() { :; }
    print_warn() { echo "WARN $*" >&2; }
    wiz_prompt() { REPLY="$2"; }
    wiz_prompt_yesno() { REPLY="$2"; }
    random_hex() { od -An -N16 -tx1 /dev/urandom | tr -d " \n"; echo; }
    WIZ_INSTALL_TYPE=controller
    WIZ_ACCEPT_DEFAULTS="$ACCEPT"
    eval "$1"
    wizard_ask_admin >&2
    printf "%s\n" "$WIZ_ADMIN_PASSWORD"
  ' bash "$INSTALL_FNS"$'\n'"$WIZARD_DEFAULTS"$'\n'"$WIZARD_FNS" <<<"$input" 2>"$TMP_DIR/stderr"
}

echo "[test] слабые пароли распознаются так же, как в панели"
bash -c '
  set -euo pipefail
  eval "$1"
  for pw in "" admin Admin ADMIN password 123456 12345678 qwerty changeme change-me-please1 \
      abcdefghij 1234567890 short1a; do
    admin_password_is_weak "$pw" admin || { echo "не слабый: [$pw]"; exit 1; }
  done
  admin_password_is_weak "operator1" operator1 || { echo "совпадение с логином не слабое"; exit 1; }
  admin_password_is_weak "Operator1" operator1 || { echo "совпадение с логином без учёта регистра"; exit 1; }
  for pw in GoodPass123 a1b2c3d4 Tr0ub4dor-horse; do
    admin_password_is_weak "$pw" admin && { echo "слабый: [$pw]"; exit 1; }
  done
  exit 0
' bash "$INSTALL_FNS" || fail "проверка слабых паролей"
echo "  OK"

echo "[test] сгенерированный пароль всегда содержит буквы и цифры"
printf '0123456789012345aaaa\nabcdefabcdefabcdbbbb\n9f3a1c0e7b2d4a6c8e0f\n' >"$TMP_DIR/hex"
generated="$(HEX="$TMP_DIR/hex" bash -c '
  set -euo pipefail
  eval "$1"
  random_hex() { local line; line="$(head -1 "$HEX")"; sed -i 1d "$HEX"; echo "$line"; }
  generate_admin_password
' bash "$INSTALL_FNS")"
[[ "$generated" == 9f3a1c0e7b2d4a6c ]] || fail "ожидался третий вариант, получено [$generated]"
echo "  OK"

echo "[test] мастер с -y генерирует пароль вместо admin"
pw="$(unset WIZ_ADMIN_PASSWORD; run_ask_admin true)"
[[ "$pw" != admin ]] || fail "пароль admin"
strong "$pw" || fail "пароль слишком простой: [$pw]"
grep -q -- "$pw" "$TMP_DIR/stderr" || fail "сгенерированный пароль не показан"
! grep -q "WARN" "$TMP_DIR/stderr" || fail "лишнее предупреждение: пароль не задавали"
pw2="$(unset WIZ_ADMIN_PASSWORD; run_ask_admin true)"
[[ "$pw" != "$pw2" ]] || fail "пароль не случайный"
echo "  OK"

echo "[test] мастер с -y оставляет заданный надёжный пароль"
pw="$(WIZ_ADMIN_PASSWORD=Strong-pass-42 run_ask_admin true)"
[[ "$pw" == Strong-pass-42 ]] || fail "надёжный пароль заменён: [$pw]"
echo "  OK"

echo "[test] мастер с -y заменяет заданный слабый пароль и предупреждает"
for weak in admin qwerty; do
  pw="$(WIZ_ADMIN_PASSWORD="$weak" run_ask_admin true)"
  strong "$pw" || fail "слабый пароль [$weak] не заменён: [$pw]"
  grep -q "WARN" "$TMP_DIR/stderr" || fail "нет предупреждения о слабом пароле"
done
pw="$(WIZ_ADMIN_USERNAME=operator1 WIZ_ADMIN_PASSWORD=operator1 run_ask_admin true)"
strong "$pw" && [[ "$pw" != operator1 ]] || fail "пароль, совпадающий с логином, не заменён"
echo "  OK"

echo "[test] интерактивный ввод отклоняет слабый пароль"
pw="$(unset WIZ_ADMIN_PASSWORD; run_ask_admin false $'admin\nGoodPass123\nGoodPass123\n')"
[[ "$pw" == GoodPass123 ]] || fail "интерактивный пароль: [$pw]"
grep -q "WARN" "$TMP_DIR/stderr" || fail "нет предупреждения о слабом пароле"
pw="$(unset WIZ_ADMIN_PASSWORD; run_ask_admin false $'\n')"
strong "$pw" || fail "пустой ввод должен генерировать пароль: [$pw]"
echo "  OK"

echo "[test] пустой пароль мастера не затирает DEFAULT_ADMIN_PASSWORD"
out="$(bash -c '
  set -eo pipefail
  command_not_found_handle() { return 0; }
  env_set() { echo "SET $1=$2"; }
  WIZARD_RAN=true
  WIZ_ADMIN_USERNAME=admin
  WIZ_ADMIN_PASSWORD=""
  WIZ_ADMIN_MUST_CHANGE_PASSWORD=true
  eval "$1"
  apply_wiz_env_settings
' bash "$(extract "$ROOT_DIR/install.sh" _wiz_should_apply apply_wiz_env_settings)")"
grep -q "^SET DEFAULT_ADMIN_USERNAME=admin$" <<<"$out" || fail "логин не записан"
! grep -q "^SET DEFAULT_ADMIN_PASSWORD=" <<<"$out" || fail "пустой пароль записан в .env"
echo "  OK"

echo "[test] итог установки не показывает admin, если пароль не менялся"
out="$(bash -c '
  set -o pipefail
  command_not_found_handle() { return 0; }
  install_controller_selected() { return 0; }
  install_node_selected() { return 1; }
  install_proxy_selected() { return 1; }
  ui_summary_row() { echo "ROW $1: $2"; }
  print_info() { echo "INFO $*"; }
  UI_USE_COLOR=false WITH_SYSTEMD=false WIZARD_RAN=false ROOT_DIR=/x ENV_FILE=/x/.env
  WIZ_ADMIN_USERNAME=admin
  unset WIZ_ADMIN_PASSWORD
  eval "$1"
  print_post_install
' bash "$(extract "$ROOT_DIR/install.sh" print_post_install)" 2>/dev/null)"
! grep -q "^ROW Пароль: admin$" <<<"$out" || fail "в итоге показан пароль admin"
grep -q "^ROW Логин: admin$" <<<"$out" || fail "логин не показан"
echo "  OK"

echo "All admin password checks passed."
