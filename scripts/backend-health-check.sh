#!/usr/bin/env bash
# Общие проверки /api/health для install.sh, start.sh и smoke-тестов.
# Поддерживает HTTP и HTTPS (uvicorn TLS, в т.ч. самоподписанный cert).

bhc_env_get() {
  local key="$1" line val
  local env_file="${BHC_ENV_FILE:-}"
  [[ -n "$env_file" && -f "$env_file" ]] || return 1
  line="$(grep -E "^${key}=" "$env_file" 2>/dev/null | head -1 || true)"
  [[ -n "$line" ]] || return 1
  val="${line#*=}"
  val="${val%$'\r'}"
  if [[ "$val" == \"*\" && "$val" == *\" ]]; then
    val="${val:1:-1}"
  elif [[ "$val" == \'*\' && "$val" == *\' ]]; then
    val="${val:1:-1}"
  fi
  printf '%s' "$val"
}

bhc_scheme_from_env() {
  local use_https ssl_cert
  use_https="$(bhc_env_get USE_HTTPS 2>/dev/null || true)"
  case "${use_https,,}" in
    true|1|yes|on)
      ssl_cert="$(bhc_env_get SSL_CERT 2>/dev/null || true)"
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
    http_direct | none)
      echo "http"
      return 0
      ;;
    le | selfsigned | nginx_custom)
      echo "http"
      return 0
      ;;
  esac
  return 1
}

bhc_scheme_from_backend_log() {
  local log_file="${BHC_BACKEND_LOG:-}"
  [[ -n "$log_file" && -f "$log_file" ]] || return 1
  if tail -n 50 "$log_file" 2>/dev/null | grep -qE 'Uvicorn running on https://'; then
    echo "https"
    return 0
  fi
  if tail -n 50 "$log_file" 2>/dev/null | grep -qE 'Uvicorn running on http://'; then
    echo "http"
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

bhc_port_from_backend_log() {
  local log_file="${BHC_BACKEND_LOG:-}" line port
  [[ -n "$log_file" && -f "$log_file" ]] || return 1
  line="$(tail -n 50 "$log_file" 2>/dev/null | grep -E 'Uvicorn running on ' | tail -1 || true)"
  [[ -n "$line" ]] || return 1
  port="$(printf '%s' "$line" | grep -oE ':[0-9]+[[:space:]]*\(' | head -1 | tr -cd '0-9' || true)"
  if [[ -z "$port" ]]; then
    port="$(printf '%s' "$line" | grep -oE ':[0-9]+' | tail -1 | tr -cd '0-9' || true)"
  fi
  [[ -n "$port" ]] || return 1
  printf '%s' "$port"
}

bhc_port_candidates() {
  local -A seen=()
  local p

  for p in \
    "$(bhc_env_get BACKEND_PORT 2>/dev/null || true)" \
    "${BHC_BACKEND_PORT:-}" \
    "${BHC_WIZ_BACKEND_PORT:-}" \
    "$(bhc_port_from_backend_log 2>/dev/null || true)"; do
    [[ -z "$p" ]] && continue
    [[ -n "${seen[$p]:-}" ]] && continue
    seen[$p]=1
    printf '%s\n' "$p"
  done
}

bhc_resolve_port() {
  local port
  port="$(bhc_port_candidates | head -1 || true)"
  printf '%s' "${port:-8000}"
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
    curl -kfsS --connect-timeout 3 --max-time 10 "$url"
  else
    curl -fsS --connect-timeout 3 --max-time 10 "$url"
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
  bhc_health_url "$other" "$port" "$path"
}

bhc_port_is_listening() {
  local port="$1"
  command -v ss >/dev/null 2>&1 || return 0
  ss -H -tln "sport = :${port}" 2>/dev/null | grep -q .
}

bhc_wait_port_listen() {
  local port="$1"
  local attempts="${2:-45}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    bhc_port_is_listening "$port" && return 0
    sleep 1
  done
  return 1
}

bhc_wait_systemd_active() {
  local service="${1:-adminpanelaz}"
  local attempts="${2:-60}"
  local i state
  command -v systemctl >/dev/null 2>&1 || return 0
  for ((i = 1; i <= attempts; i++)); do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
      return 0
    fi
    state="$(systemctl is-failed "$service" 2>/dev/null || true)"
    if [[ "$state" == "failed" ]]; then
      return 1
    fi
    sleep 1
  done
  return 1
}

bhc_try_health_once() {
  local port="$1"
  local path="$2"
  local url
  while read -r url; do
    [[ -z "$url" ]] && continue
    if bhc_curl_url "$url" >/dev/null 2>&1; then
      BHC_LAST_HEALTH_URL="$url"
      return 0
    fi
  done < <(bhc_probe_urls "$port" "$path")
  return 1
}

bhc_wait_health() {
  local port_hint="${1:-}"
  local path="${2:-/api/health}"
  local attempts="${3:-90}"
  local port i waited_listen=false

  if [[ -n "$port_hint" ]]; then
    bhc_wait_port_listen "$port_hint" 30 || true
    waited_listen=true
  fi

  for ((i = 1; i <= attempts; i++)); do
    while read -r port; do
      [[ -z "$port" ]] && continue
      if [[ "$waited_listen" != true && "$port" == "$port_hint" ]]; then
        bhc_wait_port_listen "$port" 5 || true
      fi
      if bhc_try_health_once "$port" "$path"; then
        return 0
      fi
    done < <( {
      [[ -n "$port_hint" ]] && printf '%s\n' "$port_hint"
      bhc_port_candidates
    } | awk '!seen[$0]++')
    sleep 1
  done
  return 1
}

bhc_wait_health_deep() {
  local port_hint="${1:-$(bhc_resolve_port)}"
  local attempts="${2:-30}"
  local port url i

  for ((i = 1; i <= attempts; i++)); do
    while read -r port; do
      [[ -z "$port" ]] && continue
      while read -r url; do
        [[ -z "$url" ]] && continue
        if bhc_curl_url "$url" 2>/dev/null | grep -qE '"status"[[:space:]]*:[[:space:]]*"(ok|degraded)"'; then
          BHC_LAST_HEALTH_URL="$url"
          return 0
        fi
      done < <(bhc_probe_urls "$port" "/api/health/deep")
    done < <( {
      [[ -n "$port_hint" ]] && printf '%s\n' "$port_hint"
      bhc_port_candidates
    } | awk '!seen[$0]++')
    sleep 1
  done
  return 1
}
