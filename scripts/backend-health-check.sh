#!/usr/bin/env bash
# Общие проверки /api/health для install.sh, start.sh и smoke-тестов.
# Поддерживает HTTP и HTTPS (uvicorn TLS, в т.ч. самоподписанный cert).

bhc_env_get() {
  local key="$1"
  local env_file="${BHC_ENV_FILE:-}"
  [[ -n "$env_file" && -f "$env_file" ]] || return 1
  grep -E "^${key}=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- || true
}

bhc_scheme_from_env() {
  local use_https ssl_cert
  use_https="$(bhc_env_get USE_HTTPS 2>/dev/null || true)"
  case "${use_https,,}" in
    true|1|yes|on)
      ssl_cert="$(bhc_env_get SSL_CERT 2>/dev/null || true)"
      if [[ -n "$ssl_cert" && -f "$ssl_cert" ]]; then
        echo "https"
        return 0
      fi
      if [[ -n "$ssl_cert" ]]; then
        echo "https"
        return 0
      fi
      ;;
  esac
  return 1
}

bhc_scheme_from_wizard() {
  case "${BHC_WIZ_NGINX_MODE:-}" in
    uvicorn_le | uvicorn_custom | uvicorn_selfsigned)
      echo "https"
      return 0
      ;;
  esac
  return 1
}

bhc_scheme_from_backend_log() {
  local log_file="${BHC_BACKEND_LOG:-}"
  [[ -n "$log_file" && -f "$log_file" ]] || return 1
  if tail -n 30 "$log_file" 2>/dev/null | grep -qE 'Uvicorn running on https://'; then
    echo "https"
    return 0
  fi
  return 1
}

bhc_primary_scheme() {
  local scheme=""
  scheme="$(bhc_scheme_from_env 2>/dev/null || true)"
  [[ -n "$scheme" ]] && { echo "$scheme"; return 0; }
  scheme="$(bhc_scheme_from_wizard 2>/dev/null || true)"
  [[ -n "$scheme" ]] && { echo "$scheme"; return 0; }
  scheme="$(bhc_scheme_from_backend_log 2>/dev/null || true)"
  [[ -n "$scheme" ]] && { echo "$scheme"; return 0; }
  echo "http"
}

bhc_resolve_port() {
  local port
  port="$(bhc_env_get BACKEND_PORT 2>/dev/null || true)"
  printf '%s' "${port:-${BHC_BACKEND_PORT:-${BHC_WIZ_BACKEND_PORT:-8000}}}"
}

bhc_health_url() {
  local scheme="$1"
  local port="$2"
  local path="${3:-/api/health}"
  echo "${scheme}://127.0.0.1:${port}${path}"
}

bhc_curl_url() {
  local url="$1"
  if [[ "$url" == https://* ]]; then
    curl -kfsS "$url"
  else
    curl -fsS "$url"
  fi
}

bhc_probe_urls() {
  local port="$1"
  local path="${2:-/api/health}"
  local primary other
  primary="$(bhc_primary_scheme)"
  if [[ "$primary" == "https" ]]; then
    other="http"
  else
    other="https"
  fi
  bhc_health_url "$primary" "$port" "$path"
  if [[ "$primary" != "$other" ]]; then
    bhc_health_url "$other" "$port" "$path"
  fi
}

bhc_wait_systemd_active() {
  local service="${1:-adminpanelaz}"
  local attempts="${2:-60}"
  local i
  command -v systemctl >/dev/null 2>&1 || return 0
  for ((i = 1; i <= attempts; i++)); do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

bhc_wait_health() {
  local port="${1:-$(bhc_resolve_port)}"
  local path="${2:-/api/health}"
  local attempts="${3:-90}"
  local url i

  for ((i = 1; i <= attempts; i++)); do
    while read -r url; do
      [[ -z "$url" ]] && continue
      if bhc_curl_url "$url" >/dev/null 2>&1; then
        BHC_LAST_HEALTH_URL="$url"
        return 0
      fi
    done < <(bhc_probe_urls "$port" "$path")
    sleep 1
  done
  return 1
}

bhc_wait_health_deep() {
  local port="${1:-$(bhc_resolve_port)}"
  local attempts="${2:-30}"
  local url i

  for ((i = 1; i <= attempts; i++)); do
    while read -r url; do
      [[ -z "$url" ]] && continue
      if bhc_curl_url "$url" 2>/dev/null | grep -q '"status"' 2>/dev/null; then
        BHC_LAST_HEALTH_URL="$url"
        return 0
      fi
    done < <(bhc_probe_urls "$port" "/api/health/deep")
    sleep 1
  done
  return 1
}
