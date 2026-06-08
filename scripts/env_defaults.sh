#!/bin/bash
# Значения по умолчанию для backend/.env (AdminPanelAZ, синхронизировано с AdminAntizapret 1.9.0)

_ensure_env_default() {
    local key="$1"
    local value="$2"
    local env_file="${ENV_FILE:?ENV_FILE не задан}"

    mkdir -p "$(dirname "$env_file")"
    [ -f "$env_file" ] || touch "$env_file"
    grep -q "^${key}=" "$env_file" 2>/dev/null && return 0
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
}

ensure_env_defaults() {
    _ensure_env_default "TRAFFIC_SYNC_ENABLED" "true"
    _ensure_env_default "TRAFFIC_LIMIT_RECONCILE_AFTER_SYNC" "true"
    _ensure_env_default "MONITOR_ENABLED" "true"
    _ensure_env_default "MONITOR_CPU_THRESHOLD" "90"
    _ensure_env_default "MONITOR_RAM_THRESHOLD" "90"
    _ensure_env_default "MONITOR_CHECK_INTERVAL_SECONDS" "60"
    _ensure_env_default "MONITOR_COOLDOWN_MINUTES" "30"
    _ensure_env_default "CIDR_DB_SOURCE_FETCH_TIMEOUT" "90"
    _ensure_env_default "CIDR_DB_SOURCE_FETCH_RETRIES" "3"
    _ensure_env_default "FEATURE_OPENVPN_ENABLED" "true"
    _ensure_env_default "FEATURE_WIREGUARD_ENABLED" "true"
    _ensure_env_default "FEATURE_LOGS_DASHBOARD_ENABLED" "true"
    _ensure_env_default "FEATURE_SERVER_MONITOR_ENABLED" "true"
    _ensure_env_default "FEATURE_ROUTING_ENABLED" "true"
    _ensure_env_default "FEATURE_EDIT_FILES_ENABLED" "true"
    _ensure_env_default "FEATURE_TELEGRAM_ENABLED" "true"
    _ensure_env_default "FEATURE_BACKUPS_ENABLED" "true"
    _ensure_env_default "FEATURE_SECURITY_ENABLED" "true"
    _ensure_env_default "FEATURE_DIAGNOSTICS_TESTS_ENABLED" "true"
    # Публикация (nginx-setup.sh задаёт DOMAIN, BEHIND_NGINX, TRUSTED_PROXY_IPS)
    _ensure_env_default "BEHIND_NGINX" "false"
    _ensure_env_default "APP_ENV" "development"
    _ensure_env_default "AUTH_RATE_LIMIT_ENABLED" "true"
    _ensure_env_default "SECURITY_HEADERS_ENABLED" "true"
    _ensure_env_default "AUDIT_LOG_ENABLED" "true"
}
