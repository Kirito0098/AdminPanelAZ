#!/usr/bin/env bash
# Общий запуск uvicorn для systemd-агентов (node / proxy): проверка venv, mTLS, PYTHONPATH и exec.
# Подключается systemd-exec-node.sh и systemd-exec-proxy.sh; ROOT_DIR задаёт скрипт-обёртка.

# systemd_exec_agent <компонент> <ASGI-приложение> <префикс env> <host> <порт> <strict|lenient> [VAR=значение…]
# strict — mTLS=1|true|yes, без cert/key/ca агент не стартует (node); lenient — только true, без файлов
# агент стартует без mTLS (proxy). Режимы разные намеренно: node без mTLS наружу не пускаем.
systemd_exec_agent() {
  local component="$1" app="$2" prefix="$3" host="$4" port="$5" mode="$6"
  shift 6
  local log="[systemd-exec-${component}]"
  local backend_dir="$ROOT_DIR/backend"
  local uvicorn="$backend_dir/.venv/bin/uvicorn"

  if [[ ! -x "$uvicorn" ]]; then
    echo "$log не найден $uvicorn — пересоздайте venv (install / ap_ensure_venv)" >&2
    exit 1
  fi

  local mtls_var="${prefix}_MTLS_ENABLED"
  local mtls_flag="${!mtls_var:-false}"
  local mtls_on=false
  if [[ "$mode" == strict ]]; then
    case "${mtls_flag,,}" in
      1|true|yes) mtls_on=true ;;
    esac
  elif [[ "$mtls_flag" == "true" ]]; then
    mtls_on=true
  fi

  local -a mtls_args=()
  if [[ "$mtls_on" == "true" ]]; then
    local cert_var="${prefix}_MTLS_SERVER_CERT" key_var="${prefix}_MTLS_SERVER_KEY"
    local ca_var="${prefix}_MTLS_CA_CERT"
    local cert="${!cert_var:-/etc/adminpanelaz/mtls/agent.crt}"
    local key="${!key_var:-/etc/adminpanelaz/mtls/agent.key}"
    local ca="${!ca_var:-/etc/adminpanelaz/mtls/ca.crt}"
    local -a missing=()
    local file
    for file in "$cert" "$key" "$ca"; do
      [[ -f "$file" ]] || missing+=("$file")
    done
    if (( ${#missing[@]} == 0 )); then
      mtls_args=(
        --ssl-certfile "$cert"
        --ssl-keyfile "$key"
        --ssl-ca-certs "$ca"
        --ssl-cert-reqs 2
      )
    elif [[ "$mode" == strict ]]; then
      echo "$log mTLS включён (${mtls_var}=${mtls_flag}), сертификатов нет: ${missing[*]}. Агент не запущен: верните файлы в /etc/adminpanelaz/mtls или выключите mTLS в backend/${component}_agent.env" >&2
      exit 1
    else
      echo "$log ${mtls_var}=true, но cert/key/ca не найдены — без mTLS" >&2
    fi
  fi

  local api_key_var="${prefix}_API_KEY"
  export PYTHONPATH="${backend_dir}${PYTHONPATH:+:$PYTHONPATH}"
  export "${api_key_var}=${!api_key_var:-change-me-${component}-agent-key}"
  export "${prefix}_PORT=${port}"
  local extra
  for extra in "$@"; do
    export "${extra:?}"
  done

  cd "$backend_dir" || return 1
  exec "$uvicorn" "$app" \
    --host "$host" \
    --port "$port" \
    "${mtls_args[@]}"
}
