#!/usr/bin/env bash
# Apply generated Cloudflare snippets: backup → atomic write → nginx -t → reload.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"
# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

NEW_REALIP_FILE="${1:?usage: nginx-cloudflare-realip-apply.sh /path/to/realip.conf [/path/to/allow.conf]}"
NEW_ALLOW_FILE="${2:-}"
if [[ -n "$NEW_ALLOW_FILE" ]]; then
  nginx_cloudflare_snippets_apply "$NEW_REALIP_FILE" "$NEW_ALLOW_FILE"
else
  nginx_cloudflare_realip_apply "$NEW_REALIP_FILE"
fi
