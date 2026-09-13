#!/usr/bin/env bash
# Provision client portal host for the current AdminPanelAZ publish mode.
# Usage: sudo ./scripts/nginx-setup-portal.sh [--remove]
# Env: PORTAL_DOMAIN (required unless --remove with PORTAL_DOMAIN from .env),
#      DOMAIN, EMAIL, BACKEND_PORT, HTTPS_PUBLIC_PORT, HTTP_ACME_PORT, SSL_CERT, SSL_KEY, PUBLISH_MODE
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/nginx-setup-portal.sh [--remove] [--help]

Настраивает хост клиентского портала под текущий PUBLISH_MODE из backend/.env
(второй nginx vhost, SAN/LE cert для uvicorn, или только CORS для http_direct).

Переменные:
  PORTAL_DOMAIN       Хост портала (обязателен)
  DOMAIN              Домен панели (из .env)
  EMAIL               Email для Let's Encrypt
  BACKEND_PORT        Порт uvicorn
  HTTPS_PUBLIC_PORT   Публичный HTTPS (nginx)
  HTTP_ACME_PORT      HTTP / ACME
  SSL_CERT / SSL_KEY  Для custom-режимов
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--remove" ]]; then
  portal="$(nginx_normalize_host "${PORTAL_DOMAIN:-$(nginx_env_get PORTAL_DOMAIN)}")"
  if [[ -n "$portal" ]]; then
    nginx_remove_site "$portal"
    nginx_log "Vhost портала удалён: ${portal}"
  fi
  nginx_env_unset PORTAL_DOMAIN
  exit 0
fi

portal="$(nginx_normalize_host "${PORTAL_DOMAIN:-}")"
[[ -n "$portal" ]] || {
  echo "PORTAL_DOMAIN обязателен" >&2
  exit 1
}

nginx_provision_portal_domain "$portal"
