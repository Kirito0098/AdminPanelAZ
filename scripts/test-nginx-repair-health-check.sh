#!/usr/bin/env bash
# verify_panel_health в nginx-repair.sh: default-deny (ssl_reject_handshake) отклоняет TLS без SNI,
# поэтому проверка через nginx должна идти по имени домена (--resolve), а uvicorn при ENFORCE_HTTPS
# отвечает 308 на голый HTTP, если не передан X-Forwarded-Proto: https.
# Проверки передаются в check строкой и раскрываются через eval.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"
SERVICE_NAME="adminpanelaz"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

eval "$(sed -n '/^verify_panel_health() {/,/^}/p' "$ROOT_DIR/scripts/nginx-repair.sh")"
declare -f verify_panel_health >/dev/null || { echo "verify_panel_health не найдена" >&2; exit 1; }

CURL_LOG="$TMP/curl.log"
NGINX_CODE=200
UVICORN_CODE=200
# Подмена curl: nginx с default-deny отвечает только при SNI = домен (--resolve + https://DOMAIN),
# uvicorn при ENFORCE_HTTPS без X-Forwarded-Proto: https отвечает 308.
curl() {
  local a resolve="" url="" xfp=false
  printf '%s\n' "$*" >>"$CURL_LOG"
  while [[ $# -gt 0 ]]; do
    a="$1"
    case "$a" in
      --resolve) resolve="$2"; shift ;;
      -H) [[ "$2" == "X-Forwarded-Proto: https" ]] && xfp=true; shift ;;
      -o | -w | --max-time | --connect-timeout) shift ;;
      http://* | https://*) url="$a" ;;
    esac
    shift
  done
  case "$url" in
    "https://${DOMAIN}"/* | "https://${DOMAIN}":*)
      if [[ -n "$resolve" && "$resolve" == "${DOMAIN}:"*":127.0.0.1" ]]; then
        printf '%s' "$NGINX_CODE"
        [[ "$NGINX_CODE" != 000 ]] || return 7
        return 0
      fi
      printf '000'
      return 6
      ;;
    https://127.0.0.1*)
      printf '000'
      return 35
      ;;
    "http://127.0.0.1:${BACKEND_PORT}"/*)
      if [[ "$UVICORN_CODE" == 000 ]]; then
        printf '000'
        return 7
      fi
      if [[ "$xfp" == true ]]; then printf '%s' "$UVICORN_CODE"; else printf '308'; fi
      return 0
      ;;
  esac
  printf '000'
  return 6
}

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }
check() { if eval "$1"; then ok "$2"; else bad "$2"; fi; }

# run_health <https_port> <access_path> <nginx_code> <uvicorn_code>
run_health() {
  DOMAIN="panel.example.com"
  BACKEND_PORT=8000
  HTTPS_PUBLIC_PORT="$1"
  ACCESS_PATH="$2"
  NGINX_CODE="$3"
  UVICORN_CODE="$4"
  : >"$CURL_LOG"
  OUT="$(verify_panel_health 2>&1)"
  FIRST_CALL="$(sed -n 1p "$CURL_LOG")"
  LAST_CALL="$(tail -n 1 "$CURL_LOG")"
}

echo "[test] порт 443: проверка через nginx по имени домена (SNI + Host), без предупреждения"
run_health 443 "" 200 200
check '[[ "$FIRST_CALL" == *"--resolve panel.example.com:443:127.0.0.1"* ]]' "--resolve DOMAIN:443:127.0.0.1"
check '[[ "$FIRST_CALL" == *" https://panel.example.com/api/health"* ]]' "URL https://DOMAIN/api/health"
check '[[ "$FIRST_CALL" != *"https://127.0.0.1"* ]]' "без обращения к https://127.0.0.1 (нет SNI)"
check '[[ "$FIRST_CALL" == *"-o /dev/null -w %{http_code}"* ]]' "-o /dev/null -w %{http_code}"
check '[[ "$FIRST_CALL" == *"--max-time "* ]]' "есть --max-time"
check '[[ "$OUT" == *"Проверка через nginx: OK (HTTP 200 на https://panel.example.com/api/health)"* ]]' "лог: nginx OK"
check '[[ "$OUT" != *"ВНИМАНИЕ"* ]]' "нет предупреждения"
check '[[ "$(wc -l <"$CURL_LOG")" == 1 ]]' "fallback на uvicorn не нужен"

echo "[test] свой HTTPS-порт и ACCESS_PATH"
run_health 8443 "/panel" 200 200
check '[[ "$FIRST_CALL" == *"--resolve panel.example.com:8443:127.0.0.1"* ]]' "--resolve DOMAIN:8443:127.0.0.1"
check '[[ "$FIRST_CALL" == *" https://panel.example.com:8443/panel/api/health"* ]]' "URL https://DOMAIN:8443/panel/api/health"
check '[[ "$OUT" == *"Проверка через nginx: OK (HTTP 200 на https://panel.example.com:8443/panel/api/health)"* ]]' "лог: nginx OK с подпутём"
check '[[ "$OUT" != *"ВНИМАНИЕ"* ]]' "нет предупреждения"

echo "[test] nginx не ответил: uvicorn с ENFORCE_HTTPS проверяется с X-Forwarded-Proto: https"
run_health 443 "" 000 200
check '[[ "$LAST_CALL" == *"http://127.0.0.1:8000/api/health"* ]]' "fallback на 127.0.0.1:BACKEND_PORT"
check '[[ "$LAST_CALL" == *"-H X-Forwarded-Proto: https"* ]]' "передан X-Forwarded-Proto: https"
check '[[ "$LAST_CALL" == *"--max-time "* ]]' "есть --max-time"
check '[[ "$OUT" == *"Проверка uvicorn: OK (HTTP 200 на 127.0.0.1:8000/api/health)"* ]]' "лог: uvicorn OK"
check '[[ "$OUT" != *"ВНИМАНИЕ"* ]]' "нет предупреждения (не HTTP 308)"

echo "[test] ни nginx, ни uvicorn не ответили — предупреждение с кодом"
run_health 443 "" 000 000
check '[[ "$OUT" == *"ВНИМАНИЕ: Health-check не прошёл (nginx/uvicorn: HTTP 000)"* ]]' "предупреждение HTTP 000"
check '[[ "$OUT" != *"000000"* ]]' "код не задваивается при ошибке curl"

echo "[test] nginx 502: предупреждение, если и uvicorn не ответил"
run_health 443 "" 502 000
check '[[ "$OUT" == *"ВНИМАНИЕ: Health-check не прошёл"* ]]' "предупреждение"
check '[[ "$OUT" != *"OK"* ]]' "нет OK"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
