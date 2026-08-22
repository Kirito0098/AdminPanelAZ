#!/usr/bin/env bash
# Проверка «нужен reboot после apt upgrade» для install.sh.
# Не запускать напрямую — source из установщика.
#
# Ubuntu/Debian: /var/run/reboot-required (+ .pkgs) после ядра/libc.
# Запасной сигнал: в /boot есть vmlinuz новее, чем uname -r (не в контейнере).
#
# Тесты: REBOOT_CHECK_RUN_DIR, REBOOT_CHECK_BOOT_DIR, REBOOT_CHECK_UNAME,
#        REBOOT_CHECK_IN_CONTAINER, INSTALL_SKIP_REBOOT_CHECK.

reboot_check_run_dir() {
  printf '%s' "${REBOOT_CHECK_RUN_DIR:-/var/run}"
}

reboot_check_boot_dir() {
  printf '%s' "${REBOOT_CHECK_BOOT_DIR:-/boot}"
}

reboot_check_uname() {
  if [[ -n "${REBOOT_CHECK_UNAME:-}" ]]; then
    printf '%s' "$REBOOT_CHECK_UNAME"
    return
  fi
  uname -r
}

reboot_check_in_container() {
  case "${REBOOT_CHECK_IN_CONTAINER:-}" in
    1|true|yes) return 0 ;;
    0|false|no) return 1 ;;
  esac
  [[ -f /.dockerenv || -f /run/.containerenv ]] && return 0
  if command -v systemd-detect-virt >/dev/null 2>&1; then
    systemd-detect-virt --quiet --container && return 0
  fi
  return 1
}

# Маркер apt/needrestart. При overlay — только этот каталог; иначе /var/run и /run.
reboot_check_marker_paths() {
  if [[ -n "${REBOOT_CHECK_RUN_DIR:-}" ]]; then
    printf '%s\n' "${REBOOT_CHECK_RUN_DIR}/reboot-required"
    return
  fi
  printf '%s\n' /var/run/reboot-required /run/reboot-required
}

reboot_check_pkgs_paths() {
  if [[ -n "${REBOOT_CHECK_RUN_DIR:-}" ]]; then
    printf '%s\n' "${REBOOT_CHECK_RUN_DIR}/reboot-required.pkgs"
    return
  fi
  printf '%s\n' /var/run/reboot-required.pkgs /run/reboot-required.pkgs
}

reboot_check_marker_present() {
  local f
  while IFS= read -r f; do
    [[ -f "$f" ]] && return 0
  done < <(reboot_check_marker_paths)
  return 1
}

# Уникальные имена пакетов из reboot-required.pkgs (до 8).
reboot_check_pkgs_list() {
  local f line
  local -a pkgs=()
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%%#*}"
      line="${line#"${line%%[![:space:]]*}"}"
      line="${line%"${line##*[![:space:]]}"}"
      [[ -n "$line" ]] || continue
      line="${line%% *}"
      local seen=false p
      for p in "${pkgs[@]+"${pkgs[@]}"}"; do
        if [[ "$p" == "$line" ]]; then
          seen=true
          break
        fi
      done
      if [[ "$seen" == false ]]; then
        pkgs+=("$line")
      fi
      if [[ ${#pkgs[@]} -ge 8 ]]; then
        break 2
      fi
    done < "$f"
  done < <(reboot_check_pkgs_paths)
  if [[ ${#pkgs[@]} -eq 0 ]]; then
    return 1
  fi
  local out="" p
  for p in "${pkgs[@]}"; do
    if [[ -z "$out" ]]; then
      out="$p"
    else
      out="${out}, ${p}"
    fi
  done
  printf '%s' "$out"
}

reboot_check_newest_installed_kernel() {
  local boot_dir f ver newest=""
  local -a files=()
  boot_dir="$(reboot_check_boot_dir)"
  [[ -d "$boot_dir" ]] || return 0

  shopt -s nullglob
  files=("$boot_dir"/vmlinuz-*)
  shopt -u nullglob

  for f in "${files[@]}"; do
    [[ -e "$f" ]] || continue
    [[ "$f" == *.efi.signed ]] && continue
    ver="${f##*/}"
    ver="${ver#vmlinuz-}"
    [[ -n "$ver" ]] || continue
    if [[ -z "$newest" ]]; then
      newest="$ver"
      continue
    fi
    if [[ "$(printf '%s\n' "$newest" "$ver" | sort -V | tail -n1)" == "$ver" ]]; then
      newest="$ver"
    fi
  done
  printf '%s' "$newest"
}

# 0 — в /boot есть ядро новее запущенного. В контейнере не проверяем (ядро хоста).
reboot_check_kernel_pending() {
  reboot_check_in_container && return 1
  local running newest
  running="$(reboot_check_uname)"
  newest="$(reboot_check_newest_installed_kernel)"
  [[ -n "$running" && -n "$newest" ]] || return 1
  [[ "$newest" != "$running" ]]
}

reboot_check_is_pending() {
  reboot_check_marker_present && return 0
  reboot_check_kernel_pending && return 0
  return 1
}

# Человекочитаемые причины, по одной на строку.
reboot_check_reasons() {
  local pkgs newest running
  if reboot_check_marker_present; then
    printf '%s\n' "Система пометила reboot после обновлений (reboot-required)."
    pkgs="$(reboot_check_pkgs_list || true)"
    if [[ -n "$pkgs" ]]; then
      printf '%s\n' "Пакеты: ${pkgs}"
    fi
  fi
  if reboot_check_kernel_pending; then
    running="$(reboot_check_uname)"
    newest="$(reboot_check_newest_installed_kernel)"
    printf '%s\n' "Установлено новое ядро ${newest} (сейчас запущено ${running})."
  fi
}

reboot_check_should_prompt() {
  [[ "${NON_INTERACTIVE:-false}" != true ]] || return 1
  [[ "${ACCEPT_DEFAULTS:-false}" != true ]] || return 1
  [[ -t 0 ]] || return 1
  return 0
}

install_reboot_now() {
  if [[ "${REBOOT_CHECK_DRY_RUN:-}" == "1" ]]; then
    echo "[install] DRY-RUN: reboot"
    return 0
  fi
  if declare -F log >/dev/null 2>&1; then
    log "Перезагрузка сервера. После загрузки снова: sudo ./install.sh"
  else
    echo "[install] Перезагрузка сервера. После загрузки снова: sudo ./install.sh"
  fi
  INSTALL_FATAL_HANDLED=true
  trap - ERR INT TERM
  sync || true
  if command -v systemctl >/dev/null 2>&1; then
    exec systemctl reboot
  fi
  exec reboot
  if declare -F die >/dev/null 2>&1; then
    die "Не удалось выполнить reboot. Сделайте вручную: sudo reboot"
  fi
  echo "[install] ОШИБКА: не удалось выполнить reboot. Сделайте вручную: sudo reboot" >&2
  exit 1
}

# Preflight для install.sh. 0 — можно продолжать.
check_reboot_required() {
  if [[ "${INSTALL_SKIP_REBOOT_CHECK:-}" == "1" ]]; then
    return 0
  fi
  if ! reboot_check_is_pending; then
    return 0
  fi

  local -a reasons=()
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] && reasons+=("$line")
  done < <(reboot_check_reasons)

  if declare -F ui_warn_box >/dev/null 2>&1 && [[ "${NON_INTERACTIVE:-false}" != true ]]; then
    ui_warn_box "Нужна перезагрузка сервера" \
      "После обновлений ядра или системных библиотек установка часто" \
      "ломается, пока не выполнен reboot." \
      "" \
      "${reasons[@]}" \
      "" \
      "После перезагрузки снова: sudo ./install.sh"
  else
    echo "[install] ВНИМАНИЕ: нужна перезагрузка сервера перед установкой." >&2
    for line in "${reasons[@]}"; do
      echo "[install]   $line" >&2
    done
    echo "[install]   После reboot: sudo ./install.sh" >&2
  fi

  if reboot_check_should_prompt && declare -F ui_confirm >/dev/null 2>&1; then
    echo
    if ui_confirm "Перезагрузить сервер сейчас?" "n" "true"; then
      install_reboot_now
      return 0
    fi
    if ui_confirm "Продолжить установку без перезагрузки?" "n"; then
      if declare -F warn >/dev/null 2>&1; then
        warn "Продолжаем без reboot — возможны сбои (ядро, systemd, сеть)."
      else
        echo "[install] ВНИМАНИЕ: продолжаем без reboot." >&2
      fi
      return 0
    fi
    if declare -F die >/dev/null 2>&1; then
      die "Установка отложена до перезагрузки. Затем: sudo ./install.sh"
    fi
    echo "[install] ОШИБКА: установка отложена до перезагрузки." >&2
    exit 1
  fi

  if declare -F warn >/dev/null 2>&1; then
    warn "Режим без вопросов (-y / --non-interactive): продолжаем, но reboot всё ещё рекомендуется."
  fi
  return 0
}
