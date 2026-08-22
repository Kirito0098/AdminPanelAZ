#!/usr/bin/env bash
# Юнит-тесты preflight reboot для install.sh (без reboot хоста).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/install-reboot-check.sh
source "$ROOT_DIR/scripts/install-reboot-check.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

assert_eq() {
  local got="$1" want="$2" label="$3"
  if [[ "$got" == "$want" ]]; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (got='$got' want='$want')" >&2
  fi
}

assert_rc() {
  local rc="$1" want="$2" label="$3"
  if [[ "$rc" -eq "$want" ]]; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (rc=$rc want=$want)" >&2
  fi
}

assert_contains() {
  local hay="$1" needle="$2" label="$3"
  if printf '%s' "$hay" | grep -qF "$needle"; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (missing '$needle' in: $hay)" >&2
  fi
}

setup_overlay() {
  REBOOT_CHECK_RUN_DIR="$TMP/run"
  REBOOT_CHECK_BOOT_DIR="$TMP/boot"
  REBOOT_CHECK_UNAME="6.8.0-71-generic"
  REBOOT_CHECK_IN_CONTAINER="0"
  unset INSTALL_SKIP_REBOOT_CHECK
  rm -rf "$TMP/run" "$TMP/boot"
  mkdir -p "$TMP/run" "$TMP/boot"
}

echo "[test] нет маркера и ядро совпадает — reboot не нужен"
setup_overlay
touch "$TMP/boot/vmlinuz-6.8.0-71-generic"
if reboot_check_is_pending; then
  assert_rc 0 1 "is_pending=false when clean"
else
  assert_rc 0 0 "is_pending=false when clean"
fi

echo "[test] /var/run/reboot-required"
setup_overlay
touch "$TMP/run/reboot-required"
if reboot_check_is_pending; then
  assert_rc 0 0 "is_pending=true on marker"
else
  assert_rc 1 0 "is_pending=true on marker"
fi
assert_contains "$(reboot_check_reasons)" "reboot-required" "reasons mention marker"

echo "[test] reboot-required.pkgs"
setup_overlay
touch "$TMP/run/reboot-required"
printf '%s\n' "linux-image-6.8.0-79-generic" "libc6" "libc6" >"$TMP/run/reboot-required.pkgs"
assert_eq "$(reboot_check_pkgs_list)" "linux-image-6.8.0-79-generic, libc6" "unique pkgs joined"
assert_contains "$(reboot_check_reasons)" "linux-image-6.8.0-79-generic" "reasons include pkgs"

echo "[test] новое ядро в /boot"
setup_overlay
touch "$TMP/boot/vmlinuz-6.8.0-71-generic"
touch "$TMP/boot/vmlinuz-6.8.0-79-generic"
assert_eq "$(reboot_check_newest_installed_kernel)" "6.8.0-79-generic" "newest kernel"
if reboot_check_kernel_pending; then
  assert_rc 0 0 "kernel pending"
else
  assert_rc 1 0 "kernel pending"
fi
assert_contains "$(reboot_check_reasons)" "6.8.0-79-generic" "reasons mention new kernel"

echo "[test] контейнер игнорирует расхождение ядер"
setup_overlay
REBOOT_CHECK_IN_CONTAINER="1"
touch "$TMP/boot/vmlinuz-6.8.0-79-generic"
if reboot_check_kernel_pending; then
  assert_rc 0 1 "kernel pending skipped in container"
else
  assert_rc 0 0 "kernel pending skipped in container"
fi
if reboot_check_is_pending; then
  assert_rc 0 1 "is_pending=false in container without marker"
else
  assert_rc 0 0 "is_pending=false in container without marker"
fi

echo "[test] контейнер всё равно видит reboot-required"
setup_overlay
REBOOT_CHECK_IN_CONTAINER="1"
touch "$TMP/run/reboot-required"
if reboot_check_is_pending; then
  assert_rc 0 0 "marker still counts in container"
else
  assert_rc 1 0 "marker still counts in container"
fi

echo "[test] INSTALL_SKIP_REBOOT_CHECK пропускает preflight"
setup_overlay
touch "$TMP/run/reboot-required"
INSTALL_SKIP_REBOOT_CHECK=1
NON_INTERACTIVE=true
check_reboot_required
assert_rc $? 0 "skip env continues"

echo "[test] non-interactive при pending — предупреждение, не reboot"
setup_overlay
touch "$TMP/run/reboot-required"
unset INSTALL_SKIP_REBOOT_CHECK
NON_INTERACTIVE=true
ACCEPT_DEFAULTS=true
REBOOT_CHECK_DRY_RUN=1
out="$(check_reboot_required 2>&1)"
assert_rc $? 0 "non-interactive continues"
assert_contains "$out" "нужна перезагрузка" "non-interactive warns"

echo "[test] .efi.signed не считается отдельным ядром"
setup_overlay
touch "$TMP/boot/vmlinuz-6.8.0-71-generic"
touch "$TMP/boot/vmlinuz-6.8.0-71-generic.efi.signed"
assert_eq "$(reboot_check_newest_installed_kernel)" "6.8.0-71-generic" "ignore efi.signed"
if reboot_check_kernel_pending; then
  assert_rc 0 1 "same kernel not pending"
else
  assert_rc 0 0 "same kernel not pending"
fi

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
