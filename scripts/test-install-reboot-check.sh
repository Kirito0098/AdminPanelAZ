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
  REBOOT_CHECK_DPKG_STATUS_FILE="$TMP/dpkg-status"
  unset INSTALL_SKIP_REBOOT_CHECK INSTALL_SKIP_DPKG_CHECK
  rm -rf "${TMP:?}/run" "${TMP:?}/boot"
  mkdir -p "$TMP/run" "$TMP/boot"
  printf '%s\n' "ii  git" "rc  linux-image-6.8.0-100-generic" "hi  openvpn" >"$REBOOT_CHECK_DPKG_STATUS_FILE"
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

echo "[test] пакеты dpkg застряли (DKMS не собрался под новое ядро) — стоп, reboot не предлагаем"
setup_overlay
touch "$TMP/run/reboot-required"
touch "$TMP/boot/vmlinuz-6.8.0-71-generic" "$TMP/boot/vmlinuz-7.0.0-38-generic"
cat >"$REBOOT_CHECK_DPKG_STATUS_FILE" <<'EOF'
ii  git
iU  linux-generic-hwe-24.04
iF  linux-headers-7.0.0-38-generic
iF  linux-image-7.0.0-38-generic
ii  openvpn
EOF
NON_INTERACTIVE=true
ACCEPT_DEFAULTS=true
REBOOT_CHECK_DRY_RUN=1
set +e
out="$(check_reboot_required 2>&1)"
rc=$?
set -e
assert_rc "$rc" 1 "broken dpkg stops install"
assert_contains "$out" "linux-generic-hwe-24.04, linux-headers-7.0.0-38-generic, linux-image-7.0.0-38-generic" \
  "lists stuck packages"
assert_contains "$out" "dpkg --configure -a" "points to dpkg error"
if printf '%s' "$out" | grep -qF "DRY-RUN: reboot"; then
  assert_rc 1 0 "no reboot on broken dpkg"
else
  assert_rc 0 0 "no reboot on broken dpkg"
fi
set +e
out="$(INSTALL_SKIP_DPKG_CHECK=1 check_reboot_required 2>&1)"
rc=$?
set -e
assert_rc "$rc" 0 "INSTALL_SKIP_DPKG_CHECK=1 continues"

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

echo "[test] systemctl reboot не сработал — пробуем reboot, затем ошибка"
mkdir -p "$TMP/bin"
cat >"$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$REBOOT_LOG"
exit 1
EOF
cat >"$TMP/bin/reboot" <<'EOF'
#!/usr/bin/env bash
echo "reboot" >>"$REBOOT_LOG"
exit "${FAKE_REBOOT_RC:-0}"
EOF
chmod +x "$TMP/bin/systemctl" "$TMP/bin/reboot"
export REBOOT_LOG="$TMP/reboot.log"
for want_rc in 0 1; do
  : >"$REBOOT_LOG"
  set +e
  out="$(
    PATH="$TMP/bin:$PATH"
    unset REBOOT_CHECK_DRY_RUN
    export FAKE_REBOOT_RC="$want_rc"
    # Предохранитель: настоящие systemctl или reboot перезагрузили бы сервер.
    [[ "$(command -v systemctl)" == "$TMP/bin/systemctl" && "$(command -v reboot)" == "$TMP/bin/reboot" ]] || exit 99
    install_reboot_now 2>&1
  )"
  rc=$?
  set -e
  assert_rc "$rc" "$want_rc" "reboot rc=$want_rc"
  assert_eq "$(tr '\n' ';' <"$REBOOT_LOG")" "systemctl reboot;reboot;" "после systemctl пробуем reboot (rc=$want_rc)"
done
assert_contains "$out" "не удалось выполнить reboot" "ошибка, если reboot не сработал"

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
