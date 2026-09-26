#!/usr/bin/env bash
# Запуск shell-тестов (по умолчанию все scripts/test-*.sh) с охраной хоста: изменяющие вызовы systemctl, nginx,
# iptables, ipset, ufw и certbot, которые тест не подменил сам, блокируются (scripts/host-guard-cmd.sh),
# и такой тест считается упавшим, даже если сам он прошёл.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD_DIR="$(mktemp -d)"
trap 'rm -rf "$GUARD_DIR"' EXIT

mkdir "$GUARD_DIR/bin"
for cmd in systemctl nginx iptables ip6tables iptables-save ip6tables-save iptables-restore ip6tables-restore \
  ipset ufw certbot; do
  ln -s "$ROOT_DIR/scripts/host-guard-cmd.sh" "$GUARD_DIR/bin/$cmd"
done
export HOST_GUARD_LOG="$GUARD_DIR/violations.log"
: >"$HOST_GUARD_LOG"
export PATH="$GUARD_DIR/bin:$PATH"

if [[ "$#" -gt 0 ]]; then
  tests=("$@")
else
  tests=("$ROOT_DIR"/scripts/test-*.sh)
fi

failed=()
for test in "${tests[@]}"; do
  echo "=== $(basename "$test")"
  before="$(wc -l <"$HOST_GUARD_LOG")"
  status=0
  bash "$test" || status=$?
  after="$(wc -l <"$HOST_GUARD_LOG")"
  if [[ "$after" -gt "$before" ]]; then
    echo "HOST GUARD: $(basename "$test") вызывал на хосте:" >&2
    sed -n "$((before + 1)),${after}p" "$HOST_GUARD_LOG" | sed 's/^/  /' >&2
    status=1
  fi
  [[ "$status" -eq 0 ]] || failed+=("$(basename "$test")")
done

echo
if [[ "${#failed[@]}" -gt 0 ]]; then
  echo "Упали: ${failed[*]}" >&2
  exit 1
fi
echo "Все shell-тесты прошли (${#tests[@]}), вызовов на хосте нет."
