#!/usr/bin/env bash
# Apply a generated cloudflare-realip.conf: backup → atomic write → nginx -t → reload.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"
# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

NEW_FILE="${1:?usage: nginx-cloudflare-realip-apply.sh /path/to/new.conf}"
nginx_cloudflare_realip_apply "$NEW_FILE"
