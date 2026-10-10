#!/usr/bin/env bash
# Sourced by install.sh. Node agent 1.12.0+ refuses to start with mTLS on and certificates missing.

# Prints a warning for ENV_FILE when NODE_AGENT_MTLS_ENABLED is on but certificate files are missing.
node_agent_mtls_warning() {
  local env_file="$1" flag cert key ca file
  local -a missing=()
  [[ -f "$env_file" ]] || return 0
  flag="$(sed -n 's/^NODE_AGENT_MTLS_ENABLED=//p' "$env_file" | tail -1)"
  case "${flag,,}" in
    1|true|yes) ;;
    *) return 0 ;;
  esac
  cert="$(sed -n 's/^NODE_AGENT_MTLS_SERVER_CERT=//p' "$env_file" | tail -1)"
  key="$(sed -n 's/^NODE_AGENT_MTLS_SERVER_KEY=//p' "$env_file" | tail -1)"
  ca="$(sed -n 's/^NODE_AGENT_MTLS_CA_CERT=//p' "$env_file" | tail -1)"
  for file in "${cert:-/etc/adminpanelaz/mtls/agent.crt}" "${key:-/etc/adminpanelaz/mtls/agent.key}" "${ca:-/etc/adminpanelaz/mtls/ca.crt}"; do
    [[ -f "$file" ]] || missing+=("$file")
  done
  (( ${#missing[@]} > 0 )) || return 0
  echo "mTLS node agent включён (NODE_AGENT_MTLS_ENABLED=${flag} в ${env_file}), сертификатов нет: ${missing[*]}. Агент не запустится: положите файлы в /etc/adminpanelaz/mtls или поставьте NODE_AGENT_MTLS_ENABLED=false, затем sudo systemctl restart adminpanelaz-node"
}
