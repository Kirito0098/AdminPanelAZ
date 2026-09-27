#!/usr/bin/env bash
# Повторная установка агента не должна менять ключ и mTLS, которые уже знает панель:
# иначе панель теряет связь с узлом до ручной перепривязки.
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

INSTALL_FNS="$(extract "$ROOT_DIR/install.sh" env_escape_for_sed node_env_set proxy_env_set is_placeholder_secret \
  agent_env_value agent_mtls_bundle_valid agent_env_preserve setup_node_env setup_proxy_env)"

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

PKI="$TMP_DIR/pki"
mkdir -p "$PKI"
make_ca() {
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=$1" \
    -keyout "$PKI/$1.key" -out "$PKI/$1.crt" >/dev/null 2>&1
}
make_ca ca
make_ca other-ca
openssl req -newkey rsa:2048 -nodes -subj "/CN=agent" -keyout "$PKI/agent.key" -out "$PKI/agent.csr" >/dev/null 2>&1
openssl x509 -req -in "$PKI/agent.csr" -CA "$PKI/ca.crt" -CAkey "$PKI/ca.key" -CAcreateserial \
  -days 2 -out "$PKI/agent.crt" >/dev/null 2>&1
openssl x509 -req -in "$PKI/agent.csr" -CA "$PKI/other-ca.crt" -CAkey "$PKI/other-ca.key" -CAcreateserial \
  -days 2 -out "$PKI/foreign.crt" >/dev/null 2>&1
openssl genrsa -out "$PKI/wrong.key" 2048 >/dev/null 2>&1
openssl x509 -req -in "$PKI/agent.csr" -CA "$PKI/ca.crt" -CAkey "$PKI/ca.key" -CAcreateserial \
  -days 0 -out "$PKI/expired.crt" >/dev/null 2>&1
sleep 1

NODE_ENV_FILE="$TMP_DIR/node_agent.env"
PROXY_ENV_FILE="$TMP_DIR/proxy_agent.env"
printf 'NODE_AGENT_API_KEY=change-me-node-agent-key\nNODE_AGENT_PORT=9100\n' >"$TMP_DIR/node.example"
printf 'PROXY_AGENT_API_KEY=change-me-proxy-agent-key\nPROXY_AGENT_PORT=9101\n' >"$TMP_DIR/proxy.example"

run_setup() {
  NODE_ENV_FILE="$NODE_ENV_FILE" PROXY_ENV_FILE="$PROXY_ENV_FILE" \
    NODE_ENV_EXAMPLE="$TMP_DIR/node.example" PROXY_ENV_EXAMPLE="$TMP_DIR/proxy.example" \
    ROOT_DIR="$TMP_DIR" bash -c '
    set -euo pipefail
    log() { :; }
    warn() { echo "WARN $*" >>"'"$TMP_DIR"'/warn.log"; }
    install_node_selected() { return 0; }
    install_proxy_selected() { return 0; }
    random_hex() { echo "generated-0123456789abcdef0123456789abcdef"; }
    eval "$1"
    shift
    "$@"
  ' bash "$INSTALL_FNS" "$@"
}

key_of() { sed -n "s/^$2=//p" "$1" | tail -1; }

mtls_env() {
  local cert="$1" key="$2"
  printf 'NODE_AGENT_API_KEY=live-node-key-0123456789abcdef\nNODE_AGENT_MTLS_ENABLED=true\n'
  printf 'NODE_AGENT_MTLS_CA_CERT=%s\nNODE_AGENT_MTLS_SERVER_CERT=%s\nNODE_AGENT_MTLS_SERVER_KEY=%s\n' \
    "$PKI/ca.crt" "$cert" "$key"
}

echo "[test] повторная установка узла сохраняет ключ и mTLS"
mtls_env "$PKI/agent.crt" "$PKI/agent.key" >"$NODE_ENV_FILE"
run_setup setup_node_env
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_API_KEY)" == live-node-key-0123456789abcdef ]] || fail "ключ узла сменился"
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_MTLS_ENABLED)" == true ]] || fail "mTLS выключен"
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_MTLS_SERVER_CERT)" == "$PKI/agent.crt" ]] || fail "путь к сертификату потерян"
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_MTLS_SERVER_KEY)" == "$PKI/agent.key" ]] || fail "путь к ключу потерян"
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_MTLS_CA_CERT)" == "$PKI/ca.crt" ]] || fail "путь к CA потерян"
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_PORT)" == 9100 ]] || fail "остальные значения не из примера"
[[ "$(stat -c %a "$NODE_ENV_FILE")" == 600 ]] || fail "node_agent.env должен быть 600"
echo "  OK"

echo "[test] явно переданный ключ важнее сохранённого"
mtls_env "$PKI/agent.crt" "$PKI/agent.key" >"$NODE_ENV_FILE"
NODE_AGENT_API_KEY=explicit-key-0123456789abcdef01 run_setup setup_node_env
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_API_KEY)" == explicit-key-0123456789abcdef01 ]] || fail "явный ключ не применён"
echo "  OK"

for broken in "foreign.crt agent.key сертификат от чужого CA" "agent.crt wrong.key ключ не от сертификата" "missing.crt agent.key сертификата нет" \
  "expired.crt agent.key сертификат истёк"; do
  read -r cert key why <<<"$broken"
  echo "[test] mTLS не переносится: $why"
  : >"$TMP_DIR/warn.log"
  mtls_env "$PKI/$cert" "$PKI/$key" >"$NODE_ENV_FILE"
  run_setup setup_node_env
  [[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_API_KEY)" == live-node-key-0123456789abcdef ]] || fail "ключ узла сменился"
  [[ -z "$(key_of "$NODE_ENV_FILE" NODE_AGENT_MTLS_ENABLED)" ]] || fail "mTLS включён с негодным PKI"
  grep -q "mTLS" "$TMP_DIR/warn.log" || fail "нет предупреждения о mTLS"
  echo "  OK"
done

echo "[test] без прежнего файла или с плейсхолдером ключ генерируется"
rm -f "$NODE_ENV_FILE"
run_setup setup_node_env
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_API_KEY)" == generated-0123456789abcdef0123456789abcdef ]] || fail "ключ не сгенерирован"
printf 'NODE_AGENT_API_KEY=CHANGE-ME\n' >"$NODE_ENV_FILE"
run_setup setup_node_env
[[ "$(key_of "$NODE_ENV_FILE" NODE_AGENT_API_KEY)" == generated-0123456789abcdef0123456789abcdef ]] || fail "плейсхолдер сохранён"
echo "  OK"

echo "[test] повторная установка прокси сохраняет ключ"
printf 'PROXY_AGENT_API_KEY=live-proxy-key-0123456789abcd\n' >"$PROXY_ENV_FILE"
run_setup setup_proxy_env
[[ "$(key_of "$PROXY_ENV_FILE" PROXY_AGENT_API_KEY)" == live-proxy-key-0123456789abcd ]] || fail "ключ прокси сменился"
echo "  OK"

WIZARD_FNS="$(extract "$ROOT_DIR/scripts/install-wizard.sh" wizard_ask_node_agent wizard_ask_proxy_agent)"
run_wizard() {
  local fn="$1" answers="$2"
  NODE_ENV_FILE="$NODE_ENV_FILE" PROXY_ENV_FILE="$PROXY_ENV_FILE" ANSWERS="$answers" bash -c '
    set -euo pipefail
    wiz_step() { :; }
    ui_info_box() { :; }
    print_info() { :; }
    die() { echo "DIE $*" >&2; exit 1; }
    random_hex() { echo "wizard-generated-0123456789abcdef"; }
    read -r -a queue <<<"$ANSWERS"
    wiz_prompt_yesno() { REPLY="${queue[0]}"; queue=("${queue[@]:1}"); }
    wiz_prompt() { REPLY=""; }
    wiz_prompt_secret() { REPLY=""; }
    WIZ_NODE_AGENT_PORT=9100
    WIZ_PROXY_AGENT_PORT=9101
    WIZ_INSTALL_TYPE="$3"
    eval "$1"
    "$2"
    echo "${WIZ_NODE_AGENT_API_KEY:-}${WIZ_PROXY_AGENT_API_KEY:-}"
  ' bash "$(extract "$ROOT_DIR/install.sh" is_placeholder_secret agent_env_value)"$'\n'"$WIZARD_FNS" "$fn" "${3:-node}" | tail -1
}

echo "[test] мастер предлагает оставить ключ, который уже стоит на узле"
printf 'NODE_AGENT_API_KEY=live-node-key-0123456789abcdef\n' >"$NODE_ENV_FILE"
[[ "$(run_wizard wizard_ask_node_agent "y" node)" == live-node-key-0123456789abcdef ]] || fail "мастер не оставил ключ"
[[ "$(run_wizard wizard_ask_node_agent "n y" node)" == wizard-generated-0123456789abcdef ]] || fail "отказ не сгенерировал новый ключ"
printf 'PROXY_AGENT_API_KEY=live-proxy-key-0123456789abcd\n' >"$PROXY_ENV_FILE"
[[ "$(run_wizard wizard_ask_proxy_agent "y" proxy)" == live-proxy-key-0123456789abcd ]] || fail "мастер не оставил ключ прокси"
rm -f "$NODE_ENV_FILE"
[[ "$(run_wizard wizard_ask_node_agent "y" node)" == wizard-generated-0123456789abcdef ]] || fail "без ключа на узле должен генерироваться новый"
echo "  OK"

echo "[test] --reinstall не удаляет mTLS PKI узла"
FAKE_ROOT="$TMP_DIR/root"
mkdir -p "$FAKE_ROOT/scripts"
printf '#!/usr/bin/env bash\necho "$*" >"%s/uninstall.args"\n' "$TMP_DIR" >"$FAKE_ROOT/scripts/uninstall.sh"
chmod +x "$FAKE_ROOT/scripts/uninstall.sh"
ROOT_DIR="$FAKE_ROOT" bash -c '
  set -euo pipefail
  log() { :; }
  resolve_project_dir() { :; }
  ensure_executable_scripts() { :; }
  backup_env_for_reinstall() { :; }
  run_install_flow() { :; }
  offer_restore_env_backup() { :; }
  NON_INTERACTIVE=true
  ACCEPT_DEFAULTS=false
  eval "$1"
  run_reinstall_action
' bash "$(extract "$ROOT_DIR/install.sh" run_reinstall_action)"
grep -q -- "--keep-agent-pki" "$TMP_DIR/uninstall.args" || fail "переустановка не просит сохранить PKI"

CONFIG="$TMP_DIR/etc-adminpanelaz"
mkdir -p "$CONFIG/mtls"
touch "$CONFIG/mtls/agent.key" "$CONFIG/ddns.env" "$CONFIG/node_agent.env"
ADMINPANELAZ_CONFIG_DIR="$CONFIG" bash -c '
  set -euo pipefail
  log() { :; }
  REMOVE_SYSTEM_CONFIG=true
  KEEP_AGENT_PKI=true
  eval "$1"
  remove_system_config
' bash "$(extract "$ROOT_DIR/scripts/uninstall.sh" remove_system_config)"
[[ -f "$CONFIG/mtls/agent.key" ]] || fail "PKI удалён"
[[ ! -e "$CONFIG/ddns.env" ]] || fail "остальная системная конфигурация не удалена"
ADMINPANELAZ_CONFIG_DIR="$CONFIG" bash -c '
  set -euo pipefail
  log() { :; }
  REMOVE_SYSTEM_CONFIG=true
  KEEP_AGENT_PKI=false
  eval "$1"
  remove_system_config
' bash "$(extract "$ROOT_DIR/scripts/uninstall.sh" remove_system_config)"
[[ ! -e "$CONFIG/mtls" ]] || fail "полное удаление должно убирать PKI"
echo "  OK"

echo "All agent reinstall checks passed."
