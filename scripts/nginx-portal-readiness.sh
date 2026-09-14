#!/usr/bin/env bash
# Exit 0 with a readiness trailer is intentional: background_task run_checked_command
# treats non-zero as hard failure; blockers are reported via READY=0 / ISSUES=…
# (not a separate stale_portal_vhost issue code — stale folds into nginx_t_fail).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

usage() {
  cat <<'EOF'
Usage: ./scripts/nginx-portal-readiness.sh --check|--prepare

--check    Emit readiness trailer (always exit 0 if trailer produced)
--prepare  Apply safe fixes then emit readiness trailer (exit 0 unless hard failure)
EOF
}

MODE="${1:-}"
case "$MODE" in
  --check|--prepare) ;;
  --help|-h|"")
    usage
    exit 0
    ;;
  *)
    echo "Нужен --check или --prepare" >&2
    exit 2
    ;;
esac

_join_csv() {
  local -a items=("$@")
  local out=""
  local x
  for x in "${items[@]}"; do
    [[ -n "$x" ]] || continue
    if [[ -z "$out" ]]; then
      out="$x"
    else
      out="${out},${x}"
    fi
  done
  printf '%s' "$out"
}

_is_blocking_issue() {
  # publish_mode_missing is warning only — must not set READY=false alone.
  local issue="$1"
  [[ "$issue" != "publish_mode_missing" ]]
}

_issue_label_ru() {
  local issue="$1"
  case "$issue" in
    missing_portal_domain) echo "не указан хост портала" ;;
    host_equals_panel) echo "хост портала совпадает с доменом панели" ;;
    hash_bucket_low) echo "нужен server_names_hash_bucket_size" ;;
    env_mismatch) echo "PORTAL_DOMAIN не совпадает с .env" ;;
    publish_mode_missing) echo "не задан PUBLISH_MODE (предупреждение)" ;;
    nginx_t_fail) echo "nginx -t не проходит" ;;
    *) echo "$issue" ;;
  esac
}

_build_ru_message() {
  local ready="$1" issues_csv="$2"
  if [[ "$ready" == "true" ]]; then
    printf 'Портал готов к настройке'
    return 0
  fi
  local -a labels=()
  local -a issues=()
  IFS=',' read -r -a issues <<<"${issues_csv:-}"
  local x
  for x in "${issues[@]}"; do
    [[ -n "$x" ]] || continue
    labels+=("$(_issue_label_ru "$x")")
  done
  if [[ ${#labels[@]} -gt 0 ]]; then
    printf 'Нужна подготовка: %s' "$(IFS='; '; echo "${labels[*]}")"
  else
    printf 'Нужна подготовка'
  fi
}

_nginx_site_present() {
  local host="$1"
  [[ -n "$host" ]] || return 1
  local base enabled available
  base="$(nginx_conf_basename "$host")"
  enabled="$(nginx_sites_enabled_dir)/$base"
  available="$(nginx_sites_available_dir)/$base"
  [[ -e "$enabled" || -L "$enabled" || -f "$available" ]]
}

# Temporarily disable site files, probe nginx -t, and keep deletion only if nginx -t passes.
# Returns 0 when site was deleted, 1 otherwise (restored).
_probe_remove_site_if_nginx_t_passes() {
  local host="$1"
  [[ -n "$host" ]] || return 1
  command -v nginx >/dev/null 2>&1 || return 1
  _nginx_site_present "$host" || return 1

  local base enabled_dir available_dir enabled_path available_path
  base="$(nginx_conf_basename "$host")"
  enabled_dir="$(nginx_sites_enabled_dir)"
  available_dir="$(nginx_sites_available_dir)"
  enabled_path="${enabled_dir}/${base}"
  available_path="${available_dir}/${base}"

  local bak_dir
  bak_dir="$(mktemp -d)"
  local bak_enabled="${bak_dir}/enabled"
  local bak_available="${bak_dir}/available"
  local moved_enabled=false moved_available=false

  if [[ -e "$enabled_path" || -L "$enabled_path" ]]; then
    cp -a "$enabled_path" "$bak_enabled"
    rm -f "$enabled_path"
    moved_enabled=true
  fi
  if [[ -f "$available_path" ]]; then
    cp -a "$available_path" "$bak_available"
    rm -f "$available_path"
    moved_available=true
  fi

  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx 2>/dev/null || true
    rm -rf "$bak_dir"
    return 0
  fi

  # Restore if nginx -t still fails (unrelated breakage).
  if [[ "$moved_available" == "true" && -e "$bak_available" ]]; then
    mkdir -p "$available_dir"
    cp -a "$bak_available" "$available_path"
  fi
  if [[ "$moved_enabled" == "true" && -e "$bak_enabled" ]]; then
    mkdir -p "$enabled_dir"
    cp -a "$bak_enabled" "$enabled_path"
  fi
  rm -rf "$bak_dir"
  return 1
}

_emit_trailer() {
  local ready="$1" issues_csv="$2" suggested="$3" migrated_to="$4" actions_csv="$5" portal="$6" message="$7"
  printf 'READY=%s\n' "$ready"
  printf 'ISSUES=%s\n' "$issues_csv"
  printf 'SUGGESTED_PORTAL_DOMAIN=%s\n' "$suggested"
  printf 'MIGRATED_TO=%s\n' "$migrated_to"
  printf 'ACTIONS_TAKEN=%s\n' "$actions_csv"
  printf 'PORTAL_DOMAIN=%s\n' "$portal"
  printf 'MESSAGE=%s\n' "$message"
}

_compute_readiness() {
  local portal_arg portal_env portal panel publish_mode
  local suggested=""
  local -a issues=()

  portal_arg="$(nginx_normalize_host "${PORTAL_DOMAIN:-}")"
  portal_env="$(nginx_normalize_host "$(nginx_env_get PORTAL_DOMAIN)")"
  if [[ -n "$portal_arg" ]]; then
    portal="$portal_arg"
  else
    portal="$portal_env"
  fi

  panel="$(nginx_normalize_host "$(nginx_env_get DOMAIN)")"
  publish_mode="$(nginx_env_get PUBLISH_MODE)"

  if [[ -z "$portal" ]]; then
    issues+=("missing_portal_domain")
    [[ -n "$panel" ]] && suggested="$(nginx_suggest_portal_domain "$panel")"
  fi

  if [[ -n "$portal" && -n "$panel" && "$portal" == "$panel" ]]; then
    issues+=("host_equals_panel")
    suggested="$(nginx_suggest_portal_domain "$panel")"
  fi

  local bucket dest
  dest="$(nginx_server_names_hash_dest)"
  bucket="$(nginx_hash_bucket_size_from_file "$dest")"
  if [[ "${bucket:-0}" =~ ^[0-9]+$ ]] && (( bucket < 128 )); then
    issues+=("hash_bucket_low")
  fi

  if [[ -n "$portal_arg" ]]; then
    # Only flag env mismatch if caller supplied PORTAL_DOMAIN explicitly.
    if [[ -z "$portal_env" || "$portal_env" != "$portal_arg" ]]; then
      issues+=("env_mismatch")
    fi
  fi

  if [[ -z "$publish_mode" ]]; then
    issues+=("publish_mode_missing")
  fi

  if command -v nginx >/dev/null 2>&1; then
    if ! nginx -t >/dev/null 2>&1; then
      issues+=("nginx_t_fail")
    fi
  else
    issues+=("nginx_t_fail")
  fi

  READINESS_PORTAL="$portal"
  READINESS_PANEL="$panel"
  READINESS_SUGGESTED="$suggested"
  READINESS_ISSUES_CSV="$(_join_csv "${issues[@]}")"

  local blocking=0 i
  for i in "${issues[@]}"; do
    if _is_blocking_issue "$i"; then
      blocking=1
      break
    fi
  done
  if [[ "$blocking" -eq 1 ]]; then
    READINESS_READY="false"
  else
    READINESS_READY="true"
  fi
}

MIGRATED_TO=""
MESSAGE=""
declare -a ACTIONS=()

if [[ "$MODE" == "--prepare" ]]; then
  _compute_readiness

  if [[ "$READINESS_ISSUES_CSV" == *"hash_bucket_low"* ]]; then
    nginx_ensure_server_names_hash
    ACTIONS+=("ensured_server_names_hash")
  fi

  if [[ -n "${PORTAL_DOMAIN:-}" ]]; then
    nginx_env_set PORTAL_DOMAIN "$(nginx_normalize_host "$PORTAL_DOMAIN")"
    ACTIONS+=("synced_portal_domain_env")
  fi

  # Remove portal vhost only if it is proven to be the reason nginx -t fails.
  _compute_readiness
  if [[ "$READINESS_ISSUES_CSV" == *"nginx_t_fail"* && -n "$READINESS_PORTAL" ]]; then
    if _nginx_site_present "$READINESS_PORTAL"; then
      nginx_log "Пробуем временно отключить vhost портала (${READINESS_PORTAL}) и проверить nginx -t…"
      if _probe_remove_site_if_nginx_t_passes "$READINESS_PORTAL"; then
        nginx_log "Удалён portal vhost для ${READINESS_PORTAL} (после отключения nginx -t прошёл)"
        ACTIONS+=("removed_stale_portal_vhost")
      else
        nginx_log "vhost портала не является причиной ошибки nginx -t — конфиг восстановлен"
      fi
    fi
  fi

  _compute_readiness
  MESSAGE="$(_build_ru_message "$READINESS_READY" "$READINESS_ISSUES_CSV")"

  _emit_trailer "$READINESS_READY" "$READINESS_ISSUES_CSV" "$READINESS_SUGGESTED" "$MIGRATED_TO" \
    "$(_join_csv "${ACTIONS[@]}")" "$READINESS_PORTAL" "$MESSAGE"
  exit 0
fi

# --check
_compute_readiness
MESSAGE="$(_build_ru_message "$READINESS_READY" "$READINESS_ISSUES_CSV")"
_emit_trailer "$READINESS_READY" "$READINESS_ISSUES_CSV" "$READINESS_SUGGESTED" "$MIGRATED_TO" "" "$READINESS_PORTAL" "$MESSAGE"
exit 0

