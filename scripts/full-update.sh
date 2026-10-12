#!/usr/bin/env bash
# Полное обновление (sudo ./install.sh --update): код из upstream, затем заново пакеты apt, Python, интерфейс,
# unit'ы systemd, vhost nginx, firewall, DDNS и перезапуск — по текущим настройкам, без мастера.
# База, backend/.env, *_agent.env, сертификаты и mTLS не меняются. Запускает install.sh; подключённый через
# source (тесты) скрипт только объявляет функции.
set -euo pipefail

FU_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
# shellcheck source=scripts/adminpanel-menu.sh
source "$FU_DIR/adminpanel-menu.sh"
# shellcheck source=scripts/python-runtime.sh
source "$FU_DIR/python-runtime.sh"
# shellcheck source=scripts/system-packages.sh
source "$FU_DIR/system-packages.sh"
ENV_FILE="$INSTALL_DIR/backend/.env"
# shellcheck source=scripts/nginx-common.sh
source "$FU_DIR/nginx-common.sh"
nginx_common_init
# shellcheck source=scripts/firewall-setup.sh
source "$FU_DIR/firewall-setup.sh"
FU_FW_ARGS=()

FU_STEPS=(backup code apt pip frontend systemd nginx firewall ddns restart)
declare -A FU_LABELS=(
  [backup]=Бэкап [code]=Код [apt]=Пакеты [pip]=Python [frontend]=Интерфейс
  [systemd]=systemd [nginx]=nginx [firewall]=firewall [ddns]=DDNS [restart]=Перезапуск
)
# Ошибка этих шагов останавливает обновление до перезапуска: панель продолжает работать на прежнем коде.
FU_STOP_STEPS=" backup code pip frontend "
FU_STATE=""
FU_STOPPED=false
FU_EXIT=0
FU_ARROW="->"
case "${MENU_USER_LOCALE,,}" in
  *utf-8* | *utf8*) FU_ARROW="→" ;;
esac

# Итог — в файле, а не в переменных: шаги идут в подоболочках, а после обновления кода продолжает новый процесс.
fu_row() {
  local detail="${3:-}"
  detail="${detail//[$'\t\n']/ }"
  printf '%s\t%s\t%s\n' "$1" "$2" "$detail" >>"$FU_STATE"
}

fu_field() {
  awk -F'\t' -v key="$1" -v n="$2" '$1 == key { value = $n } END { print value }' "$FU_STATE"
}

fu_fail_detail() {
  case "$1" in
    backup) echo "бэкап не создан — обновление не начиналось" ;;
    code) echo "код не обновлён — подробности выше" ;;
    pip) echo "pip install не прошёл — панель не перезапускалась" ;;
    frontend) echo "сборка не прошла — панель не перезапускалась; вручную: cd $INSTALL_DIR/frontend && npm ci && npm run build:all" ;;
    systemd) echo "refresh-systemd-units.sh завершился с ошибкой — проверьте unit'ы вручную" ;;
    *) echo "непредвиденная ошибка (код $2), см. вывод выше" ;;
  esac
}

# Шаг — в подоболочке с set -e: отказ команды завершает шаг, а не всё обновление. Вызывать только отдельной
# командой: в `fu_run … || …` и `if fu_run …` bash отключает set -e и внутри подоболочки.
fu_run() {
  local key="$1" rc
  if [[ "$FU_STOPPED" == true ]]; then
    return 0
  fi
  ui_section "${FU_LABELS[$key]}"
  set +e
  (set -e; "$2")
  rc=$?
  set -e
  if [[ -z "$(fu_field "$key" 2)" ]]; then
    if [[ "$rc" -eq 0 ]]; then
      fu_row "$key" ok
    else
      fu_row "$key" ошибка "$(fu_fail_detail "$key" "$rc")"
    fi
  fi
  if [[ "$rc" -ne 0 && "$FU_STOP_STEPS" == *" $key "* ]]; then
    FU_STOPPED=true
  fi
  return 0
}

# printf %-10s в bash считает байты, а буква кириллицы — два байта.
fu_pad() {
  local text="$1" width="$2"
  printf '%s' "$text"
  if ((${#text} < width)); then
    printf '%*s' "$((width - ${#text}))" ''
  fi
}

fu_status_color() {
  case "$1" in
    ok) printf '%s' "$C_OK" ;;
    ошибка) printf '%s' "$C_ERR" ;;
    *) printf '%s' "$C_DIM" ;;
  esac
}

fu_summary() {
  local key status detail width
  width="$(($(menu_cols) - 23))"
  ui_section "Полное обновление"
  for key in "${FU_STEPS[@]}"; do
    status="$(fu_field "$key" 2)"
    detail="$(fu_field "$key" 3)"
    if [[ -z "$status" ]]; then
      status=пропущен
      detail="не выполнялся"
    fi
    printf '  %s %s' "$(fu_pad "${FU_LABELS[$key]}" 10)" "$(fu_status_color "$status")"
    if [[ -n "$detail" ]]; then
      printf '%s%s  %s\n' "$(fu_pad "$status" 8)" "$C_RESET" "$(menu_fit "$detail" "$width")"
    else
      printf '%s%s\n' "$status" "$C_RESET"
    fi
  done
}

fu_finish() {
  local backup
  fu_summary
  FU_EXIT=0
  if awk -F'\t' '$2 == "ошибка" { found = 1 } END { exit !found }' "$FU_STATE"; then
    FU_EXIT=1
  fi
  if [[ "$(fu_field restart 3)" == *"панель не ответила"* ]]; then
    backup="$(fu_field backup 3)"
    printf '\n'
    ui_warn "Панель не ответила после обновления. Бэкап до обновления: ${backup:-нет}"
    ui_info "Восстановить: sudo adminpanelaz $FU_ARROW 6 Бэкап и восстановление"
  fi
  rm -f "$FU_STATE"
}

fu_head() {
  git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || true
}

fu_step_backup() {
  if ! panel_uses_systemd; then
    fu_row backup пропущен "нет панели"
    return 0
  fi
  panel_backup --no-prune --keep-running
  fu_row backup ok "${PANEL_LAST_BACKUP##*/}"
}

# Код — функцией меню: fast-forward из upstream текущей ветки, reset после force-push только при чистом дереве.
fu_step_code() {
  local before after
  before="$(fu_head)"
  PANEL_UPDATE_CODE_ONLY=true
  panel_update
  after="$(fu_head)"
  if [[ "$before" == "$after" ]]; then
    fu_row code ok "актуально, $after"
  else
    fu_row code ok "$before $FU_ARROW $after"
  fi
}

# Остальные шаги — уже обновлённым установщиком: новые шаблоны и новый код шагов. Исходная локаль — для значков.
full_update_reexec() {
  ui_info "Код обновлён — дальше работает обновлённый install.sh"
  exec env LC_ALL="$MENU_USER_LC_ALL" LANG="$MENU_USER_LANG" \
    "${BASH:-bash}" "$INSTALL_DIR/install.sh" --update -y --update-resume="$FU_STATE"
}

fu_apt_packages() {
  local mm
  printf '%s\n' "${ADMINPANELAZ_APT_PACKAGES[@]}"
  mm="$(ap_python_mm "$(ap_venv_report_version "$VENV_PATH" || true)" || true)"
  if [[ -n "$mm" ]]; then
    ap_python_apt_packages_for "$mm" | tr ' ' '\n'
  fi
}

fu_pkg_installed() {
  local status
  status="$(dpkg -s "$1" 2>/dev/null)" || return 1
  grep -qx 'Status: install ok installed' <<<"$status"
}

# Уже установленные пакеты не обновляются (--no-upgrade); ошибка apt не останавливает обновление.
fu_step_apt() {
  local pkg
  local -a missing=()
  while IFS= read -r pkg; do
    if [[ -n "$pkg" ]] && ! fu_pkg_installed "$pkg"; then
      missing+=("$pkg")
    fi
  done < <(fu_apt_packages)
  if [[ "${#missing[@]}" -eq 0 ]]; then
    ui_ok "Все пакеты apt на месте"
    fu_row apt ok "доустановлено: 0"
    return 0
  fi
  ui_info "Доустановка: ${missing[*]}"
  if DEBIAN_FRONTEND=noninteractive apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-upgrade "${missing[@]}"; then
    fu_row apt ok "доустановлено: ${#missing[@]} (${missing[*]})"
    return 0
  fi
  ui_warn "apt-get не доустановил пакеты — обновление продолжается"
  fu_row apt ошибка "не доустановлено: ${missing[*]}"
}

fu_step_pip() {
  local pip="$VENV_PATH/bin/pip"
  if [[ ! -x "$pip" ]]; then
    ui_fail "Нет $pip — виртуальное окружение Python не найдено"
    fu_row pip ошибка "нет $pip"
    return 1
  fi
  ui_info "pip install -r backend/requirements.txt…"
  "$pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"
  ui_ok "Python-зависимости обновлены"
  fu_row pip ok
}

fu_step_frontend() {
  if ! panel_uses_systemd; then
    fu_row frontend пропущен "нет панели"
    return 0
  fi
  panel_build_frontend
  fu_row frontend ok
}

fu_refresh_units() {
  SYSTEMD_UNIT_DIR="$UNIT_DIR" bash "$INSTALL_DIR/scripts/refresh-systemd-units.sh"
}

fu_units_list() {
  local list="" unit
  if panel_uses_systemd; then
    list="$SERVICE_NAME"
  fi
  while IFS= read -r unit; do
    list+="${list:+, }$unit"
  done < <(menu_agent_units)
  printf '%s' "$list"
}

fu_step_systemd() {
  menu_install_command
  fu_refresh_units
  ui_ok "Unit'ы обновлены из шаблонов: $(fu_units_list)"
  fu_row systemd ok "$(fu_units_list)"
}

# Как scripts/nginx-repair.sh: nginx-режимы публикации, у старых установок без PUBLISH_MODE — BEHIND_NGINX.
fu_nginx_published() {
  [[ -n "$(nginx_env_get DOMAIN)" ]] || return 1
  case "$(nginx_env_get PUBLISH_MODE)" in
    nginx_le | nginx_selfsigned | nginx_custom) return 0 ;;
    "") _menu_env_true "$(nginx_env_get BEHIND_NGINX)" ;;
    *) return 1 ;;
  esac
}

fu_vhost_ssl_value() {
  sed -n "s/^[[:space:]]*$1[[:space:]]\{1,\}\([^;[:space:]]\{1,\}\);.*/\1/p" "$2" | sed -n 1p
}

# Сертификаты — из действующего vhost: полное обновление их не выбирает заново и не выпускает.
fu_nginx_render() {
  local kind="$1" host="$2" file="$3" cert key backend https http
  cert="$(fu_vhost_ssl_value ssl_certificate "$file")"
  key="$(fu_vhost_ssl_value ssl_certificate_key "$file")"
  if [[ -z "$cert" || -z "$key" ]]; then
    nginx_warn "В $file нет ssl_certificate / ssl_certificate_key"
    return 1
  fi
  backend="$(nginx_env_get BACKEND_PORT)"
  https="$(nginx_env_get HTTPS_PUBLIC_PORT)"
  http="$(nginx_env_get HTTP_ACME_PORT)"
  if [[ "$kind" == portal ]]; then
    nginx_render_portal_template "$host" "${backend:-8000}" "$cert" "$key" "${https:-443}" "${http:-80}"
  else
    ACCESS_PATH="$(nginx_env_get ACCESS_PATH)" nginx_render_template "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
      "$host" "${backend:-8000}" "$cert" "$key" "${https:-443}" "${http:-80}"
  fi
}

# Пересобираются только свои файлы sites-available/<домен>; панель в подпути чужого сайта — nginx-repair.sh.
# Все vhost собираются до записи, копии .bak-* делаются до первой записи: откат возвращает всё сразу.
fu_step_nginx() {
  local domain portal kind host stamp file err line list i
  local -a kinds=() hosts=() files=() confs=()
  if ! panel_uses_systemd; then
    fu_row nginx пропущен "нет панели"
    return 0
  fi
  if ! fu_nginx_published; then
    fu_row nginx пропущен "публикация без nginx"
    return 0
  fi
  domain="$(nginx_normalize_host "$(nginx_env_get DOMAIN)")"
  portal="$(nginx_normalize_host "$(nginx_env_get PORTAL_DOMAIN)")"
  for kind in panel portal; do
    host="$domain"
    if [[ "$kind" == portal ]]; then
      host="$portal"
    fi
    [[ -n "$host" ]] || continue
    nginx_conf_paths "$host"
    if nginx_is_our_panel_vhost_file "$NGINX_CONF_FILE"; then
      kinds+=("$kind")
      hosts+=("$host")
      files+=("$NGINX_CONF_FILE")
    fi
  done
  if [[ "${#files[@]}" -eq 0 ]]; then
    ui_warn "Свой vhost панели не найден (панель в подпути чужого сайта?) — nginx не менялся; пересборка: sudo ./scripts/nginx-repair.sh"
    fu_row nginx пропущен "нет своего vhost в $(nginx_sites_available_dir) — nginx не менялся"
    return 0
  fi
  for i in "${!files[@]}"; do
    if ! confs[i]="$(fu_nginx_render "${kinds[i]}" "${hosts[i]}" "${files[i]}")"; then
      nginx_install_txn_rollback
      ui_fail "Не удалось собрать vhost ${hosts[i]} — nginx не менялся"
      fu_row nginx ошибка "не удалось собрать vhost ${hosts[i]} — nginx не менялся"
      return 1
    fi
  done
  stamp="$(date +%Y%m%d-%H%M%S)"
  for file in "${files[@]}"; do
    cp -a -- "$file" "$file.bak-$stamp"
    ui_info "Копия: $file.bak-$stamp"
  done
  for i in "${!files[@]}"; do
    printf '%s\n' "${confs[i]}" >"${files[i]}"
  done
  if err="$(nginx -t 2>&1)"; then
    nginx_install_txn_commit
    if ! systemctl reload nginx; then
      ui_fail "systemctl reload nginx не прошёл"
      fu_row nginx ошибка "конфиг обновлён, но systemctl reload nginx не прошёл"
      return 1
    fi
    printf -v list '%s, ' "${hosts[@]}"
    ui_ok "nginx -t прошёл, nginx перезагружен"
    fu_row nginx ok "${list%, }"
    return 0
  fi
  for file in "${files[@]}"; do
    cp -a -- "$file.bak-$stamp" "$file"
  done
  nginx_install_txn_rollback
  if ! nginx -t >/dev/null 2>&1; then
    ui_warn "nginx -t не проходит и со старым конфигом — проверьте: sudo nginx -t"
  fi
  line="$(grep -m1 -E '\[(emerg|error)\]' <<<"$err" || true)"
  if [[ -z "$line" ]]; then
    line="$(head -n1 <<<"$err")"
  fi
  printf '%s\n' "$err" >&2
  ui_fail "nginx -t не прошёл — старый конфиг восстановлен, копии: *.bak-$stamp"
  fu_row nginx ошибка "конфиг не обновлён, старый восстановлен (nginx -t: ${line#nginx: })"
  return 1
}

fu_publish_kind() {
  if fu_nginx_published; then
    echo nginx
    return 0
  fi
  case "$(nginx_env_get PUBLISH_MODE)" in
    uvicorn_* | http_direct)
      echo direct
      return 0
      ;;
  esac
  case "$(nginx_env_get BACKEND_HOST)" in
    "" | 127.0.0.1 | localhost | ::1) echo none ;;
    *) echo direct ;;
  esac
}

# ACCEPT 80/443 не признак: такие правила мог добавить кто угодно.
fu_iptables_has_own_rules() {
  local backend="$1" node="$2" proxy="$3" ip="$4" port
  if [[ "$backend" != 0 ]] && iptables -C INPUT -p tcp --dport "$backend" ! -s 127.0.0.1 -j DROP 2>/dev/null; then
    return 0
  fi
  for port in "$node" "$proxy"; do
    if [[ -z "$port" || "$port" == 0 ]]; then
      continue
    fi
    if iptables -C INPUT -p tcp --dport "$port" -j DROP 2>/dev/null; then
      return 0
    fi
    if [[ -n "$ip" ]] && iptables -C INPUT -p tcp --dport "$port" ! -s "$ip" -j DROP 2>/dev/null; then
      return 0
    fi
  done
  return 1
}

# Свои правила — как их находит uninstall.sh --remove-firewall; правило SSH остаётся и после удаления панели.
fu_firewall_configured() {
  local added backend=0 node="" proxy=""
  case "$(firewall_detect_tool)" in
    ufw)
      added="$(ufw show added 2>/dev/null || true)"
      grep "comment '[^']*AdminPanelAZ" <<<"$added" | grep -vF "comment '${FIREWALL_UFW_SSH_COMMENT}'" >/dev/null
      ;;
    iptables)
      firewall_resolve_uninstall_params "$INSTALL_DIR"
      if panel_uses_systemd; then
        backend="$FIREWALL_UNINSTALL_BACKEND_PORT"
      fi
      if [[ -f "$UNIT_DIR/adminpanelaz-node.service" ]]; then
        node="$FIREWALL_UNINSTALL_NODE_PORT"
      fi
      if [[ -f "$UNIT_DIR/adminpanelaz-proxy.service" ]]; then
        proxy="$FIREWALL_UNINSTALL_PROXY_PORT"
      fi
      fu_iptables_has_own_rules "$backend" "$node" "$proxy" "$FIREWALL_UNINSTALL_PANEL_IP"
      ;;
    *) return 1 ;;
  esac
}

# Агенту без IP панели правило DROP закрыло бы порт и от панели — тогда правила не трогаем.
fu_firewall_args() {
  local backend=0 https http node=false proxy=false nginx=false
  firewall_resolve_uninstall_params "$INSTALL_DIR"
  if [[ -f "$UNIT_DIR/adminpanelaz-node.service" ]]; then
    node=true
  fi
  if [[ -f "$UNIT_DIR/adminpanelaz-proxy.service" ]]; then
    proxy=true
  fi
  if [[ "$node" == true || "$proxy" == true ]] && [[ -z "$FIREWALL_UNINSTALL_PANEL_IP" ]]; then
    return 1
  fi
  https="$FIREWALL_UNINSTALL_HTTPS_PORT"
  http="$FIREWALL_UNINSTALL_HTTP_PORT"
  if panel_uses_systemd; then
    case "$(fu_publish_kind)" in
      nginx)
        nginx=true
        backend="$FIREWALL_UNINSTALL_BACKEND_PORT"
        ;;
      direct)
        nginx=true
        https="$FIREWALL_UNINSTALL_BACKEND_PORT"
        http=0
        ;;
      *) backend="$FIREWALL_UNINSTALL_BACKEND_PORT" ;;
    esac
  fi
  FU_FW_ARGS=("$backend" "$FIREWALL_UNINSTALL_NODE_PORT" "$https" "$http" "$node" "$nginx"
    "$FIREWALL_UNINSTALL_PANEL_IP" "$proxy" "$FIREWALL_UNINSTALL_PROXY_PORT")
}

fu_step_firewall() {
  local tool
  if ! fu_firewall_configured; then
    fu_row firewall пропущен "не настроен"
    return 0
  fi
  tool="$(firewall_detect_tool)"
  if ! fu_firewall_args; then
    ui_warn "IP панели не записан в node_agent.env / proxy_agent.env — правила firewall не менялись"
    fu_row firewall пропущен "IP панели не записан в node_agent.env / proxy_agent.env — правила не менялись"
    return 0
  fi
  if FIREWALL_ENABLE_UFW=false firewall_apply_rules "${FU_FW_ARGS[@]}"; then
    fu_row firewall ok "$tool: правила AdminPanelAZ применены заново"
    return 0
  fi
  ui_warn "Правила firewall не применены — обновление продолжается"
  fu_row firewall ошибка "$tool: правила не применены, см. вывод выше"
}

fu_step_ddns() {
  if [[ ! -f "${DDNS_CONFIG:-/etc/adminpanelaz/ddns.env}" ]]; then
    fu_row ddns пропущен "не настроен"
    return 0
  fi
  if SYSTEMD_UNIT_DIR="$UNIT_DIR" bash "$FU_DIR/ddns-update.sh" install-timer; then
    fu_row ddns ok "adminpanelaz-ddns.timer"
    return 0
  fi
  ui_warn "Таймер DDNS не обновлён — обновление продолжается"
  fu_row ddns ошибка "ddns-update.sh install-timer не прошёл — см. вывод выше"
}

fu_step_restart() {
  local unit detail failed=false
  local -a parts=()
  if panel_uses_systemd; then
    if panel_restart_and_wait; then
      parts+=("панель отвечает")
    else
      parts+=("панель не ответила за 30 с")
      failed=true
    fi
  fi
  while IFS= read -r unit; do
    if agent_restart "$unit"; then
      parts+=("$unit работает")
    else
      parts+=("$unit не запустился")
      failed=true
    fi
  done < <(menu_agent_units)
  printf -v detail '%s, ' "${parts[@]}"
  if [[ "$failed" == true ]]; then
    fu_row restart ошибка "${detail%, }"
    return 1
  fi
  fu_row restart ok "${detail%, }"
}

full_update_apply() {
  fu_run apt fu_step_apt
  fu_run pip fu_step_pip
  fu_run frontend fu_step_frontend
  fu_run systemd fu_step_systemd
  fu_run nginx fu_step_nginx
  fu_run firewall fu_step_firewall
  fu_run ddns fu_step_ddns
  fu_run restart fu_step_restart
}

full_update_run() {
  local before
  before="$(fu_head)"
  fu_run backup fu_step_backup
  fu_run code fu_step_code
  if [[ "$FU_STOPPED" != true && "$(fu_head)" != "$before" ]]; then
    full_update_reexec
  fi
  full_update_apply
}

fu_stdin_is_tty() {
  [[ -t 0 ]]
}

fu_print_plan() {
  ui_section "Полное обновление AdminPanelAZ"
  ui_info "Сервисы: $(fu_units_list)"
  ui_info "Шаги: бэкап, код из upstream, пакеты apt, Python, интерфейс, unit'ы systemd, nginx, firewall, DDNS, перезапуск"
  ui_info "Не меняются: база, backend/.env, *_agent.env, сертификаты, mTLS"
}

fu_state_dir() {
  local dir="${TMPDIR:-/tmp}"
  printf '%s' "${dir%/}"
}

# Файл итога этапа 1 (--resume) создаёт mktemp этого же скрипта от root с правами 600. Другой каталог, symlink,
# чужой владелец или запись для группы и всех — не наш файл. ADMINPANELAZ_TEST_STATE_UID задают только тесты.
fu_state_valid() {
  local path="$1" meta uid mode
  [[ "${path%/*}" == "$(fu_state_dir)" && "${path##*/}" =~ ^adminpanelaz-update\.[A-Za-z0-9]+$ ]] || return 1
  [[ ! -L "$path" && -f "$path" ]] || return 1
  meta="$(stat -c '%u %a' -- "$path" 2>/dev/null)" || return 1
  read -r uid mode <<<"$meta"
  [[ "$uid" == "${ADMINPANELAZ_TEST_STATE_UID:-0}" && "$mode" =~ ^[0-7]{3,4}$ ]] || return 1
  (((8#$mode & 8#022) == 0))
}

# Строки этапа 1 разбираются строго и ничем не исполняются: «Бэкап» (ok или пропущен) не больше одной,
# «Код» — ровно одна ok; подробности без табуляций и управляющих символов; не больше 4 КБ.
fu_state_rows_valid() {
  local line backup=0 code=0
  local re=$'^(backup|code)\t(ok|пропущен)\t([^\t[:cntrl:]]*)$'
  (($(wc -c <"$1") <= 4096)) || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ $re ]] || return 1
    case "${BASH_REMATCH[1]}:${BASH_REMATCH[2]}" in
      backup:*) backup=$((backup + 1)) ;;
      code:ok) code=$((code + 1)) ;;
      *) return 1 ;;
    esac
  done <"$1"
  ((backup <= 1 && code == 1))
}

# Строки берутся в новый файл mktemp: дальше этап 2 пишет только в свой файл. Проверенный файл этапа 1 удаляется.
fu_state_resume() {
  local src="$1" copy
  fu_state_valid "$src" || return 1
  copy="$(mktemp "$(fu_state_dir)/adminpanelaz-update.XXXXXX")"
  head -c 4097 -- "$src" >"$copy" || true
  rm -f -- "$src"
  if ! fu_state_rows_valid "$copy"; then
    rm -f -- "$copy"
    return 1
  fi
  FU_STATE="$copy"
}

FU_ASSUME_YES=false

full_update_main() {
  local resume=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes) FU_ASSUME_YES=true ;;
      --resume)
        if [[ $# -lt 2 ]]; then
          ui_fail "--resume: нужен файл итога"
          return 2
        fi
        resume="$2"
        shift
        ;;
      *)
        ui_fail "Неизвестный аргумент: $1 (запуск: sudo ./install.sh --update)"
        return 2
        ;;
    esac
    shift
  done
  require_root
  if [[ "$(menu_mode)" == none ]]; then
    ui_fail "AdminPanelAZ не установлена: используйте обычную установку (sudo ./install.sh)"
    return 1
  fi
  if [[ -n "$resume" ]]; then
    if ! fu_state_resume "$resume"; then
      ui_fail "Неверный файл итога обновления: ${resume//[[:cntrl:]]/?}"
      return 2
    fi
    full_update_apply
    fu_finish
    return "$FU_EXIT"
  fi
  if [[ "$FU_ASSUME_YES" != true ]]; then
    if ! fu_stdin_is_tty; then
      ui_fail "Нет терминала для подтверждения. Без вопросов: sudo ./install.sh --update -y"
      return 2
    fi
    fu_print_plan
    if ! menu_confirm "Продолжить?" n; then
      ui_info "Полное обновление отменено, ничего не изменено"
      return 0
    fi
  fi
  FU_STATE="$(mktemp "$(fu_state_dir)/adminpanelaz-update.XXXXXX")"
  full_update_run
  fu_finish
  return "$FU_EXIT"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  full_update_main "$@"
fi
