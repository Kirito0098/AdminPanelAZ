#!/usr/bin/env bash
# Ops console menu — обёртка над systemd и существующими scripts.
# Не дублирует install.sh wizard; установка: sudo ./install.sh

set -euo pipefail

# Локаль пользователя запоминается до переключения на C.UTF-8: её получает sudo, по ней выбираются значки.
MENU_USER_LC_ALL="${LC_ALL-}"
MENU_USER_LANG="${LANG-}"
MENU_USER_LOCALE="${LC_ALL:-${LC_CTYPE:-${LANG:-}}}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANG="${LANG:-C.UTF-8}"

ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$ROOT_DIR}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/backend/.venv}"
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
BACKUP_CLI="$ROOT_DIR/scripts/backup-cli.py"
SITE_DIAGNOSTICS="$ROOT_DIR/scripts/site-diagnostics.sh"
PANEL_UPDATE_CHANGED=false
# true — только git (полное обновление, scripts/full-update.sh): pip, интерфейс и unit'ы оно делает своими шагами.
PANEL_UPDATE_CODE_ONLY=false
PANEL_LAST_BACKUP=""
MENU_CHOICE=""
MENU_AGENT=""
MENU_CODE=""
MENU_PANEL_STATE=""
MENU_HEALTH=""
MENU_URL=""
MENU_AGENT_UNITS=()
MENU_AGENT_STATES=()

# Цвет (no-color.org): только если stdout — терминал, NO_COLOR пуст и TERM не dumb.
C_OK="" C_WARN="" C_ERR="" C_INFO="" C_DIM="" C_BOLD="" C_RESET=""
if [[ -z "${NO_COLOR:-}" && "${TERM:-}" != dumb && -t 1 ]]; then
  C_OK=$'\033[32m'
  C_WARN=$'\033[33m'
  C_ERR=$'\033[31m'
  C_INFO=$'\033[36m'
  C_DIM=$'\033[2m'
  C_BOLD=$'\033[1m'
  C_RESET=$'\033[0m'
fi

case "${MENU_USER_LOCALE,,}" in
  *utf-8* | *utf8*)
    G_OK="✓" G_WARN="!" G_ERR="✗" G_INFO="i" MENU_DOT="·" MENU_ELLIPSIS="…"
    ;;
  *)
    G_OK="[ok]" G_WARN="[!]" G_ERR="[x]" G_INFO="[i]" MENU_DOT="-" MENU_ELLIPSIS="..."
    ;;
esac

ui_ok() { printf '  %s%s%s  %s\n' "$C_OK" "$G_OK" "$C_RESET" "$*"; }
ui_warn() { printf '  %s%s%s  %s\n' "$C_WARN" "$G_WARN" "$C_RESET" "$*" >&2; }
ui_fail() { printf '  %s%s%s  %s\n' "$C_ERR" "$G_ERR" "$C_RESET" "$*" >&2; }
ui_info() { printf '  %s%s%s  %s\n' "$C_INFO" "$G_INFO" "$C_RESET" "$*"; }
ui_section() { printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

# Ширина терминала: COLUMNS, иначе tput cols, иначе 80. Уже 40 колонок не считаем — строки просто переносятся.
menu_cols() {
  local cols="${COLUMNS:-}"
  [[ "$cols" =~ ^[1-9][0-9]*$ ]] || cols="$(tput cols 2>/dev/null)" || cols=""
  [[ "$cols" =~ ^[1-9][0-9]*$ ]] || cols=80
  ((cols >= 40)) || cols=40
  printf '%s' "$cols"
}

# menu_fit <текст> <ширина>: длинный текст обрезается, последним ставится многоточие.
menu_fit() {
  local text="$1" width="$2"
  if ((${#text} <= width)); then
    printf '%s' "$text"
  else
    printf '%s%s' "${text:0:$((width - ${#MENU_ELLIPSIS}))}" "$MENU_ELLIPSIS"
  fi
}

# clear -x сохраняет историю прокрутки; в старых ncurses ключа -x нет. Вне терминала экран не чистим.
menu_clear() {
  [[ -t 1 && "${TERM:-dumb}" != dumb ]] || return 0
  clear -x 2>/dev/null || printf '\033[H\033[2J'
}

menu_item() { printf '  %s  %s\n' "$1" "$2"; }

# menu_screen <заголовок> <пункт 0> <пункты…>: экран подменю.
menu_screen() {
  local title="$1" zero="$2" i
  shift 2
  menu_clear
  printf '%s%s%s\n\n' "$C_BOLD" "$title" "$C_RESET"
  for ((i = 1; i <= $#; i++)); do
    menu_item "$i" "${!i}"
  done
  printf '\n'
  menu_item 0 "$zero"
}

# menu_read <последний номер> <что делает q>: ответ в MENU_CHOICE; q и конец ввода — 0.
menu_read() {
  printf 'Выберите [0-%s, q — %s]: ' "$1" "$2"
  if ! read -r MENU_CHOICE; then
    MENU_CHOICE=0
    printf '\n'
  fi
  if [[ "$MENU_CHOICE" == [qQ] ]]; then
    MENU_CHOICE=0
  fi
}

menu_valid_choice() {
  [[ "$MENU_CHOICE" =~ ^[1-9][0-9]*$ ]] && ((MENU_CHOICE <= $1))
}

menu_invalid() {
  ui_warn "Неверный выбор"
  sleep 1
}

# menu_confirm <вопрос> <y|n>: Enter — ответ по умолчанию (второй аргумент), конец ввода — «нет».
menu_confirm() {
  local answer hint="[y/N]"
  if [[ "$2" == y ]]; then
    hint="[Y/n]"
  fi
  printf '  %s %s: ' "$1" "$hint"
  if ! read -r answer; then
    printf '\n'
    return 1
  fi
  case "${answer,,}" in
    "") [[ "$2" == y ]] ;;
    y | yes | д | да) return 0 ;;
    *) return 1 ;;
  esac
}

menu_state_word() {
  local color="$C_DIM"
  case "$1" in
    работает | отвечает) color="$C_OK" ;;
    остановлен | запускается) color="$C_WARN" ;;
    ошибка | "не отвечает") color="$C_ERR" ;;
  esac
  printf '%s%s%s' "$color" "$1" "$C_RESET"
}

press_any_key() {
  if [[ -t 0 ]]; then
    printf "\n"
    read -r -p "  Нажмите Enter, чтобы вернуться" _ || true
  fi
}

# Пункт интерактивного меню: отказ или ошибка действия не закрывает меню, а внутри действия set -e работает
# (в `действие || true` bash его отключает).
menu_action() {
  set +e
  (set -e; "$@")
  set -e
  press_any_key
}

menu_interrupted() {
  printf '\n'
  exit 130
}

require_root() {
  if [[ "$(id -u)" != 0 ]]; then
    ui_fail "Нужны права root (sudo)."
    exit 1
  fi
}

# sudo сбрасывает окружение: NO_COLOR передаётся явно, локаль сохраняет env_keep по умолчанию.
menu_ensure_root() {
  if [[ "$(id -u)" == 0 ]]; then
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    ui_fail "Нужны права root (sudo не найден)"
    exit 1
  fi
  local sudo_env=()
  if [[ -n "${NO_COLOR:-}" ]]; then
    sudo_env=("NO_COLOR=$NO_COLOR")
  fi
  LC_ALL="$MENU_USER_LC_ALL" LANG="$MENU_USER_LANG" \
    exec sudo ${sudo_env[@]+"${sudo_env[@]}"} -- "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
}

panel_uses_systemd() {
  [[ -f "$UNIT_DIR/${SERVICE_NAME}.service" ]]
}

_menu_python() {
  if [[ -x "$VENV_PATH/bin/python" ]]; then
    printf '%s\n' "$VENV_PATH/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  return 1
}

# Значение из backend/.env: последнее присваивание (как читает панель), без кавычек; пусто — нет файла или ключа.
_menu_env_get() {
  local file="$INSTALL_DIR/backend/.env" line val
  [[ -r "$file" ]] || return 0
  line="$(grep -E "^$1=" "$file" 2>/dev/null | tail -1)" || true
  val="${line#*=}"
  val="${val%$'\r'}"
  if [[ "${#val}" -ge 2 && ( "$val" == \"*\" || "$val" == \'*\' ) ]]; then
    val="${val:1:-1}"
  fi
  printf '%s' "$val"
}

_menu_env_true() {
  case "${1,,}" in
    1 | true | yes | on) return 0 ;;
  esac
  return 1
}

# ACCESS_PATH как normalize_access_path (backend/app/services/panel_paths.py): "" или "/a/b".
_menu_access_path() {
  local seg out=""
  local -a segs=()
  IFS=/ read -ra segs <<<"$(_menu_env_get ACCESS_PATH)"
  for seg in "${segs[@]}"; do
    seg="${seg//[[:space:]]/}"
    if [[ -n "$seg" ]]; then
      out+="/$seg"
    fi
  done
  printf '%s' "$out"
}

_menu_backend_port() {
  local port
  port="$(_menu_env_get BACKEND_PORT)"
  [[ -n "$port" ]] || port="$(_menu_env_get APP_PORT)"
  printf '%s' "${port:-8000}"
}

_menu_uvicorn_https() {
  local cert
  cert="$(_menu_env_get SSL_CERT)"
  _menu_env_true "$(_menu_env_get USE_HTTPS)" && [[ -n "${cert//[[:space:]]/}" ]]
}

# Как _health_probe_url в backend/app/services/site_diagnostics.py.
panel_health_url() {
  local scheme=http
  if _menu_uvicorn_https; then
    scheme=https
  fi
  printf '%s://127.0.0.1:%s%s/api/health\n' "$scheme" "$(_menu_backend_port)" "$(_menu_access_path)"
}

panel_health_ok() {
  local url
  local -a opts=(-fsS -m 2 -o /dev/null)
  url="$(panel_health_url)"
  if [[ "$url" == https://* ]]; then
    opts+=(-k)
  fi
  curl "${opts[@]}" "$url" >/dev/null 2>&1
}

panel_health_state() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "неизвестно"
  elif panel_health_ok; then
    echo "отвечает"
  else
    echo "не отвечает"
  fi
}

# Адрес для браузера: домен за nginx — https и HTTPS_PUBLIC_PORT; иначе порт backend; без домена — IP сервера.
panel_public_url() {
  local host scheme=http port note=""
  host="$(_menu_env_get DOMAIN)"
  host="${host//[[:space:]]/}"
  host="${host%%:*}"
  port="$(_menu_backend_port)"
  if [[ -n "$host" ]] && _menu_env_true "$(_menu_env_get BEHIND_NGINX)"; then
    scheme=https
    port="$(_menu_env_get HTTPS_PUBLIC_PORT)"
    port="${port:-443}"
  else
    if _menu_uvicorn_https; then
      scheme=https
    fi
    if [[ -z "$host" ]]; then
      case "$(_menu_env_get BACKEND_HOST)" in
        127.0.0.1 | localhost | ::1)
          host=127.0.0.1
          note=" (только с этого сервера)"
          ;;
        *)
          host="$(hostname -I 2>/dev/null | awk '{ print $1 }')" || true
          host="${host:-<IP сервера>}"
          ;;
      esac
    fi
  fi
  if [[ "$scheme:$port" == https:443 || "$scheme:$port" == http:80 ]]; then
    port=""
  else
    port=":$port"
  fi
  printf '%s://%s%s%s/%s\n' "$scheme" "$host" "$port" "$(_menu_access_path)" "$note"
}

# systemctl может ждать D-Bus десятки секунд — шапка меню ждать не должна.
_menu_unit_state() {
  local state
  state="$(timeout 3 systemctl is-active "$1" 2>/dev/null)" || true
  case "$state" in
    active) echo "работает" ;;
    inactive) echo "остановлен" ;;
    failed) echo "ошибка" ;;
    activating | reloading) echo "запускается" ;;
    *) echo "неизвестно" ;;
  esac
}

menu_code_line() {
  local version commit branch
  version="$(sed -n 's/^[[:space:]]*"version":[[:space:]]*"\([^"]*\)".*/\1/p' "$INSTALL_DIR/frontend/package.json" 2>/dev/null \
    | head -1)" || true
  commit="$(timeout 3 git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null)" || true
  branch="$(timeout 3 git -C "$INSTALL_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null)" || true
  printf 'AdminPanelAZ %s %s %s @ %s' "${version:-неизвестно}" "$MENU_DOT" "${branch:-неизвестно}" "${commit:-неизвестно}"
}

# menu_probe <panel|agent|both>: пробы для шапки, результат — в переменных MENU_*.
menu_probe() {
  local unit
  MENU_CODE="$(menu_code_line)"
  MENU_PANEL_STATE=""
  MENU_HEALTH=""
  MENU_URL=""
  MENU_AGENT_UNITS=()
  MENU_AGENT_STATES=()
  if [[ "$1" == panel || "$1" == both ]]; then
    MENU_PANEL_STATE="$(_menu_unit_state "$SERVICE_NAME")"
    MENU_HEALTH="$(panel_health_state)"
    MENU_URL="$(panel_public_url)"
  fi
  if [[ "$1" == agent || "$1" == both ]]; then
    mapfile -t MENU_AGENT_UNITS < <(menu_agent_units)
    for unit in "${MENU_AGENT_UNITS[@]}"; do
      MENU_AGENT_STATES+=("$(_menu_unit_state "$unit")")
    done
  fi
}

# menu_header <panel|agent|both>: шапка по результатам menu_probe; адрес и ветка@коммит — по ширине терминала.
menu_header() {
  local width i agents=""
  width="$(menu_cols)"
  printf '%s%s%s\n' "$C_BOLD" "$(menu_fit "$MENU_CODE" "$width")" "$C_RESET"
  if [[ "$1" == panel || "$1" == both ]]; then
    printf '  Панель   %s %s health %s\n' "$(menu_state_word "$MENU_PANEL_STATE")" "$MENU_DOT" \
      "$(menu_state_word "$MENU_HEALTH")"
    printf '  Адрес    %s\n' "$(menu_fit "$MENU_URL" $((width - 11)))"
  fi
  if [[ "$1" == agent || "$1" == both ]]; then
    for i in "${!MENU_AGENT_UNITS[@]}"; do
      agents+="${agents:+ $MENU_DOT }$(menu_state_word "${MENU_AGENT_STATES[i]}") (${MENU_AGENT_UNITS[i]#adminpanelaz-})"
    done
    printf '  Агент    %s\n' "$agents"
  fi
}

# Всё установленное работает: панель — сервис и health, агенты — active.
menu_probe_ok() {
  local state
  if [[ -n "$MENU_PANEL_STATE" ]]; then
    [[ "$MENU_PANEL_STATE" == работает && "$MENU_HEALTH" == отвечает ]] || return 1
  fi
  for state in "${MENU_AGENT_STATES[@]}"; do
    [[ "$state" == работает ]] || return 1
  done
}

menu_status() {
  local mode
  mode="$(menu_mode)"
  if [[ "$mode" == none ]]; then
    printf '%s\n' "$(menu_fit "$(menu_code_line)" "$(menu_cols)")"
    printf '  Панель   не установлена через systemd\n'
    return 1
  fi
  menu_probe "$mode"
  menu_header "$mode"
  menu_probe_ok
}

# Строку «Проверка состояния…» стирает перерисовка экрана после проб.
menu_probe_screen() {
  menu_clear
  printf 'Проверка состояния%s\n' "$MENU_ELLIPSIS"
  menu_probe "$1"
  menu_clear
}

panel_wait_health() {
  local i start="$SECONDS"
  ui_info "Ожидание ответа панели (до 30 с)…"
  for ((i = 0; i <= 15; i++)); do
    if panel_health_ok; then
      ui_ok "Панель запущена и отвечает"
      return 0
    fi
    if ((i == 15 || SECONDS - start >= 30)); then
      break
    fi
    sleep 2
  done
  ui_fail "Панель не ответила за 30 с"
  ui_info "Причина — в меню: 2 Журнал → 3 Только ошибки; 3 Диагностика сайта"
  return 1
}

# Интерфейс проверяется только там, где его уже собирали. Сборка устарела, если отслеживаемый файл frontend
# новее собранного index.html: git pull ставит изменённым файлам текущее время.
frontend_build_stale() {
  local index="$INSTALL_DIR/frontend/dist/index.html" path
  [[ -d "$INSTALL_DIR/frontend/dist" ]] || return 1
  [[ -f "$index" ]] || return 0
  while IFS= read -r -d '' path; do
    [[ "$INSTALL_DIR/$path" -nt "$index" ]] && return 0
  done < <(git -C "$INSTALL_DIR" ls-files -z -- frontend 2>/dev/null)
  return 1
}

panel_build_frontend() {
  local frontend_dir="$INSTALL_DIR/frontend"
  if ! command -v npm >/dev/null 2>&1; then
    ui_fail "npm не найден — интерфейс не пересобран"
    return 1
  fi
  ui_info "Сборка интерфейса (npm ci, npm run build:all)…"
  if (cd "$frontend_dir" && npm ci && npm run build:all); then
    ui_ok "Интерфейс пересобран"
    return 0
  fi
  ui_fail "Сборка интерфейса не удалась — панель показывает старый интерфейс"
  return 1
}

panel_frontend_manual_hint() {
  ui_fail "Соберите интерфейс вручную: cd $INSTALL_DIR/frontend && npm ci && npm run build:all, затем $0 --restart"
}

panel_restart() {
  require_root
  if frontend_build_stale; then
    ui_warn "Интерфейс собран до последнего обновления кода — пересоберите его: $0 --update"
  fi
  ui_info "Перезапуск панели…"
  if panel_uses_systemd; then
    systemctl restart "$SERVICE_NAME"
    ui_ok "systemctl restart $SERVICE_NAME"
  else
    ui_fail "Не найден systemd unit $SERVICE_NAME"
    return 1
  fi
}

unit_status() {
  printf "\n"
  systemctl status "$1" --no-pager -l || true
}

unit_restart() {
  require_root
  local unit="$1"
  if [[ "$unit" == nginx ]] && ! nginx -t; then
    ui_fail "nginx -t не прошёл — перезапуск отменён, исправьте конфигурацию"
    return 1
  fi
  systemctl restart "$unit"
  ui_ok "systemctl restart $unit"
}

unit_logs_tail() {
  printf "\n"
  journalctl -u "$1" -n 50 --no-pager || true
}

unit_logs_follow() {
  ui_info "Журнал $1 в реальном времени. Ctrl+C — вернуться в меню"
  journalctl -u "$1" -f -n 20 --no-pager || true
}

unit_logs_errors() {
  local unit="$1" since lines
  local -a range=(-b)
  since="$(systemctl show -p ActiveEnterTimestamp --value --timestamp=unix "$unit" 2>/dev/null)" || true
  if [[ "$since" == @* && "$since" != @0 ]]; then
    range=(--since "$since")
  fi
  lines="$(journalctl -u "$unit" "${range[@]}" --no-pager -o short-iso 2>/dev/null \
    | grep -Ei 'error|exception|traceback|critical' | tail -n 100)" || true
  ui_info "Ошибки $unit с последнего запуска (не больше 100 строк):"
  if [[ -z "$lines" ]]; then
    ui_ok "Ошибок нет"
  else
    printf '%s\n' "$lines"
  fi
}

menu_logs() {
  local unit="$1" saved
  while true; do
    menu_screen "Журнал $MENU_DOT $unit" "Назад" \
      "Последние 50 строк" "В реальном времени (Ctrl+C — назад)" "Только ошибки с последнего запуска"
    menu_read 3 назад
    case "$MENU_CHOICE" in
      1) menu_action unit_logs_tail "$unit" ;;
      2)
        # Ctrl+C должен остановить только journalctl, а не выйти из меню.
        saved="$(trap -p INT)"
        trap ':' INT
        menu_action unit_logs_follow "$unit"
        eval "${saved:-trap - INT}"
        ;;
      3) menu_action unit_logs_errors "$unit" ;;
      0) return 0 ;;
      *) menu_invalid ;;
    esac
  done
}

panel_reset_password() {
  require_root
  local py
  py="$(_menu_python)" || {
    ui_fail "Python не найден ($VENV_PATH/bin/python или python3)"
    return 1
  }
  "$py" "$ROOT_DIR/scripts/reset-password.py"
}

# nginx ставится пакетом в /lib/systemd/system, поэтому кроме $UNIT_DIR спрашиваем systemd.
neighbor_units() {
  local unit file
  for unit in nginx adminpanelaz-node adminpanelaz-proxy adminpanelaz-ddns.timer; do
    file="$unit"
    [[ "$file" == *.* ]] || file="$unit.service"
    if [[ -f "$UNIT_DIR/$file" || -n "$(systemctl list-unit-files --no-legend "$file" 2>/dev/null)" ]]; then
      printf '%s\n' "$unit"
    fi
  done
  return 0
}

menu_unit_actions() {
  local unit="$1"
  while true; do
    menu_screen "$unit $MENU_DOT $(_menu_unit_state "$unit")" "Назад" "Статус" "Перезапустить"
    menu_read 2 назад
    case "$MENU_CHOICE" in
      1) menu_action unit_status "$unit" ;;
      2)
        if menu_confirm "Перезапустить $unit?" n; then
          menu_action unit_restart "$unit"
        fi
        ;;
      0) return 0 ;;
      *) menu_invalid ;;
    esac
  done
}

menu_services() {
  local i
  local -a units=() labels=()
  while true; do
    mapfile -t units < <(neighbor_units)
    if [[ "${#units[@]}" -eq 0 ]]; then
      ui_info "nginx, агенты и DDNS на этом сервере не установлены"
      press_any_key
      return 0
    fi
    labels=()
    for i in "${!units[@]}"; do
      labels+=("$(printf '%-24s %s' "${units[i]}" "$(menu_state_word "$(_menu_unit_state "${units[i]}")")")")
    done
    menu_screen "Сервисы" "Назад" "${labels[@]}"
    menu_read "${#units[@]}" назад
    if [[ "$MENU_CHOICE" == 0 ]]; then
      return 0
    fi
    if ! menu_valid_choice "${#units[@]}"; then
      menu_invalid
      continue
    fi
    menu_unit_actions "${units[MENU_CHOICE - 1]}"
  done
}

# Ветка, с которой обновляется рабочая копия, — те же правила, что у обновления из панели
# (resolve_update_ref в backend/app/services/node_update.py): upstream текущей ветки, для main без upstream —
# origin/main. Ветку релиза нельзя двигать на историю другой ветки.
panel_update_ref() {
  local branch upstream
  branch="$(git -C "$INSTALL_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [[ -z "$branch" ]]; then
    ui_fail "Рабочая копия не на ветке (detached HEAD): обновите вручную"
    return 1
  fi
  upstream="$(git -C "$INSTALL_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  if [[ -n "$upstream" ]]; then
    printf '%s\n' "$upstream"
    return 0
  fi
  if [[ "$branch" == main ]]; then
    printf '%s\n' origin/main
    return 0
  fi
  ui_fail "У ветки $branch нет upstream: обновите вручную или привяжите её (git branch -u origin/$branch)"
  return 1
}

# Коммиты HEAD, которых нет ни в одной ветке origin и не было в upstream ($1), — как _unpushed_commit_count
# в node_update.py; «?», если git не ответил. Вершины upstream до force-push берутся из обеих колонок его
# reflog: у свежего клона reflog нет, и первый fetch после force-push пишет прежнюю вершину только как old.
panel_unpushed_count() {
  local log seen=()
  log="$(git -C "$INSTALL_DIR" rev-parse --git-path "logs/refs/remotes/$1" 2>/dev/null)" || log=""
  [[ -z "$log" || "$log" == /* ]] || log="$INSTALL_DIR/$log"
  if [[ -f "$log" ]]; then
    mapfile -t seen < <(awk '{ print $1; print $2 }' "$log" | grep -Ex '[0-9a-f]{40}|[0-9a-f]{64}' | grep -vxE '0+' | sort -u || true)
  fi
  git -C "$INSTALL_DIR" rev-list --count HEAD --not --remotes ${seen[@]+"${seen[@]}"} 2>/dev/null || echo '?'
}

panel_update() {
  require_root
  if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    ui_fail "Каталог $INSTALL_DIR не является git-репозиторием"
    return 1
  fi
  if ! command -v git >/dev/null 2>&1; then
    ui_fail "git не найден"
    return 1
  fi

  ui_section "Обновление AdminPanelAZ"
  ui_info "git fetch origin…"
  if ! git -C "$INSTALL_DIR" fetch origin --quiet; then
    ui_fail "git fetch не удался"
    return 1
  fi

  local ref local_rev remote_rev behind ahead
  ref="$(panel_update_ref)" || return 1
  local_rev="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
  if ! remote_rev="$(git -C "$INSTALL_DIR" rev-parse --verify --quiet "$ref^{commit}")"; then
    ui_fail "Не найдена ветка $ref"
    return 1
  fi
  behind="$(git -C "$INSTALL_DIR" rev-list --count "$local_rev..$remote_rev")"
  ahead="$(git -C "$INSTALL_DIR" rev-list --count "$remote_rev..$local_rev")"

  if [[ "$behind" -eq 0 ]]; then
    ui_ok "Репозиторий актуален ($(git -C "$INSTALL_DIR" rev-parse --short HEAD), $ref)"
    if [[ "$ahead" -gt 0 ]]; then
      ui_info "Локальных коммитов, которых нет в $ref: $ahead"
    fi
    # Так досборка доходит до обновившихся меню 2.25.1: оно делало git pull без сборки интерфейса.
    if [[ "$PANEL_UPDATE_CODE_ONLY" != true ]] && frontend_build_stale; then
      ui_warn "Интерфейс собран до последнего обновления кода"
      if ! panel_build_frontend; then
        panel_frontend_manual_hint
        return 1
      fi
      PANEL_UPDATE_CHANGED=true
      ui_info "Перезапустите панель: $0 --restart"
    fi
    return 0
  fi

  ui_info "Найдены обновления в $ref (отставание: $behind). git merge --ff-only $ref…"
  local merge_out status_out unpushed
  if ! merge_out="$(git -C "$INSTALL_DIR" merge --ff-only "$ref" 2>&1)"; then
    # После force-push на origin история расходится при чистом дереве: сброс только на upstream той же ветки.
    if ! status_out="$(git -C "$INSTALL_DIR" status --porcelain 2>/dev/null)" || [[ -n "$status_out" ]]; then
      [[ -n "$merge_out" ]] && printf '%s\n' "$merge_out" >&2
      ui_fail "Обновление не удалось: история расходится с $ref или есть локальные изменения — обновите вручную"
      return 1
    fi
    unpushed="$(panel_unpushed_count "$ref")"
    if [[ "$unpushed" != 0 ]]; then
      [[ -n "$merge_out" ]] && printf '%s\n' "$merge_out" >&2
      ui_fail "В локальной ветке есть коммиты, которых нет на сервере git: $unpushed (история расходится с $ref) — синхронизируйте вручную"
      return 1
    fi
    if ! git -C "$INSTALL_DIR" reset --hard --quiet "$ref"; then
      ui_fail "Обновление не удалось: git reset --hard $ref — обновите вручную"
      return 1
    fi
    ui_warn "История переписана: reset --hard $ref"
  else
    [[ -n "$merge_out" ]] && printf '%s\n' "$merge_out"
  fi
  ui_ok "Код обновлён"
  PANEL_UPDATE_CHANGED=true
  if [[ "$PANEL_UPDATE_CODE_ONLY" == true ]]; then
    return 0
  fi

  # bash выполняет версию меню, прочитанную до git pull: остальные шаги — уже обновлённым скриптом.
  local menu="$INSTALL_DIR/scripts/adminpanel-menu.sh"
  INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
    "${BASH:-bash}" "$menu" --after-pull
}

# Команду получают и серверы, установленные до неё: её ставит шаг после обновления.
menu_install_command() {
  local lib="$ROOT_DIR/scripts/console-command.sh" link rc=0
  [[ -f "$lib" && -f "$INSTALL_DIR/scripts/adminpanel-menu.sh" ]] || return 0
  # shellcheck source=scripts/console-command.sh
  source "$lib"
  link="$(console_command_path)"
  console_command_link "$INSTALL_DIR" || rc=$?
  case "$rc" in
    0) ui_ok "Консольное меню: sudo adminpanelaz" ;;
    2) ui_warn "$link уже есть и это не ссылка AdminPanelAZ — команда adminpanelaz не установлена" ;;
    *) ui_warn "Не удалось создать $link" ;;
  esac
  return 0
}

# Шаги после git pull; вызывается из panel_update уже обновлённым скриптом.
panel_after_pull() {
  if [[ -x "$VENV_PATH/bin/pip" && -f "$ROOT_DIR/backend/requirements.txt" ]]; then
    ui_info "Обновление Python-зависимостей…"
    if ! "$VENV_PATH/bin/pip" install -q -r "$ROOT_DIR/backend/requirements.txt"; then
      ui_fail "pip install завершился с ошибкой — обновление остановлено: интерфейс не собран, systemd units не обновлены, панель не перезапускайте"
      ui_fail "Исправьте ошибку, затем: $VENV_PATH/bin/pip install -r $ROOT_DIR/backend/requirements.txt && $0 --after-pull"
      return 1
    fi
    ui_ok "Зависимости обновлены"
  fi

  # Интерфейс собирается только там, где его уже собирали: на сервере с одним агентом нет npm.
  local frontend_dir="$INSTALL_DIR/frontend" frontend_ok=true
  if [[ -f "$frontend_dir/package.json" && -d "$frontend_dir/dist" ]]; then
    panel_build_frontend || frontend_ok=false
  fi

  # 2.19+: старые unit’ы с start.sh ломаются после удаления скриптов — переписать из репо
  if [[ -x "$INSTALL_DIR/scripts/refresh-systemd-units.sh" ]]; then
    ui_info "Обновление systemd units…"
    if bash "$INSTALL_DIR/scripts/refresh-systemd-units.sh"; then
      ui_ok "systemd units обновлены"
    else
      ui_warn "refresh-systemd-units завершился с ошибкой — проверьте unit вручную"
    fi
  fi

  menu_install_command

  if [[ "$frontend_ok" != true ]]; then
    ui_fail "Код уже обновлён, интерфейс — нет. Повторный $0 --update попробует собрать его снова."
    panel_frontend_manual_hint
    return 1
  fi
  ui_info "Перезапустите панель: $0 --restart"
  return 0
}

panel_restart_and_wait() {
  panel_restart
  panel_wait_health
}

panel_offer_restart() {
  if ! menu_confirm "Перезапустить панель сейчас?" y; then
    ui_info "Панель не перезапущена: $0 --restart"
    return 0
  fi
  panel_restart_and_wait
}

panel_update_interactive() {
  PANEL_UPDATE_CHANGED=false
  panel_update
  [[ "$PANEL_UPDATE_CHANGED" == true ]] || return 0
  panel_offer_restart
}

# Полное обновление — режим install.sh: кроме кода заново пакеты, unit'ы, nginx, firewall и DDNS, свой итог по шагам.
menu_full_update() {
  ui_section "Полное обновление (код + конфигурация сервера)"
  ui_info "Бэкап, код из git, пакеты apt, Python, интерфейс, unit'ы systemd, nginx, firewall, DDNS и перезапуск — по текущим настройкам"
  ui_info "База, backend/.env, сертификаты и mTLS не меняются"
  if ! menu_confirm "Запустить полное обновление?" n; then
    ui_info "Полное обновление отменено"
    return 0
  fi
  LC_ALL="$MENU_USER_LC_ALL" LANG="$MENU_USER_LANG" "${BASH:-bash}" "$INSTALL_DIR/install.sh" --update -y
}

panel_backup() {
  require_root
  local py
  py="$(_menu_python)" || {
    ui_fail "Python не найден ($VENV_PATH/bin/python или python3)"
    return 1
  }
  if [[ ! -f "$BACKUP_CLI" ]]; then
    ui_fail "Не найден $BACKUP_CLI"
    return 1
  fi

  ui_section "Резервная копия панели"
  local archive code
  set +e
  archive="$(INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" \
    "$py" "$BACKUP_CLI" create "$@" 2>&1)"
  code=$?
  set -e
  if [[ "$code" -eq 0 && -n "$archive" ]]; then
    PANEL_LAST_BACKUP="${archive##*$'\n'}"
    ui_ok "Архив: $archive"
  else
    ui_fail "Бэкап не создан"
    [[ -n "$archive" ]] && printf '%s\n' "$archive" >&2
    return "$code"
  fi
}

_menu_size_mb() {
  awk -v bytes="$1" 'BEGIN { printf "%.1f МБ", bytes / 1048576 }'
}

_menu_backup_components() {
  local item out=""
  local -a items=()
  IFS=, read -ra items <<<"$1"
  for item in "${items[@]}"; do
    case "$item" in
      db) item="база" ;;
      cidr_db) item="база CIDR" ;;
      env) item=".env" ;;
      configs) item="списки AntiZapret" ;;
      awg2) item="AZ-AWG2" ;;
    esac
    out+="${out:+, }$item"
  done
  printf '%s' "${out:-состав неизвестен}"
}

panel_restore() {
  require_root
  local py listing name created size components answer safety i
  local -a lines=() names=()
  py="$(_menu_python)" || {
    ui_fail "Python не найден ($VENV_PATH/bin/python или python3)"
    return 1
  }
  if ! listing="$(INSTALL_DIR="$INSTALL_DIR" "$py" "$BACKUP_CLI" list)"; then
    ui_fail "Не удалось получить список резервных копий"
    return 1
  fi
  if [[ -n "$listing" ]]; then
    mapfile -t lines <<<"$listing"
  fi
  if [[ "${#lines[@]}" -eq 0 ]]; then
    ui_warn "Резервных копий нет"
    return 0
  fi

  ui_section "Восстановление из резервной копии"
  for i in "${!lines[@]}"; do
    IFS=$'\t' read -r name created size components <<<"${lines[i]}"
    names+=("$name")
    created="${created%Z}"
    menu_item "$((i + 1))" "${created/T/ } UTC $MENU_DOT $(_menu_size_mb "$size") $MENU_DOT $(_menu_backup_components "$components")"
  done
  printf '\n'
  menu_item 0 "Отмена"
  menu_read "${#names[@]}" отмена
  if [[ "$MENU_CHOICE" == 0 ]]; then
    ui_info "Восстановление отменено"
    return 0
  fi
  if ! menu_valid_choice "${#names[@]}"; then
    ui_warn "Неверный выбор"
    return 1
  fi
  name="${names[MENU_CHOICE - 1]}"

  ui_warn "Панель будет остановлена, база и backend/.env — перезаписаны из $name"
  ui_info "Перед восстановлением будет сделана копия текущего состояния"
  printf '  Восстановить из %s? Введите «да»: ' "$name"
  if ! read -r answer; then
    answer=""
    printf '\n'
  fi
  if [[ "$answer" != "да" ]]; then
    ui_info "Восстановление отменено, ничего не изменено"
    return 0
  fi

  if ! panel_backup --no-prune; then
    ui_fail "Копия текущего состояния не создана — восстановление отменено, панель не останавливалась"
    return 1
  fi
  safety="$PANEL_LAST_BACKUP"
  if ! INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" "$py" "$BACKUP_CLI" restore "$name"; then
    ui_fail "Восстановление не удалось. Копия состояния до восстановления: $safety"
    return 1
  fi
  ui_ok "Восстановлено из $name"
  ui_info "Копия состояния до восстановления: $safety"
  panel_wait_health
}

menu_backups() {
  while true; do
    menu_screen "Бэкап и восстановление" "Назад" "Создать резервную копию" "Восстановить из резервной копии"
    menu_read 2 назад
    case "$MENU_CHOICE" in
      1) menu_action panel_backup ;;
      2) menu_action panel_restore ;;
      0) return 0 ;;
      *) menu_invalid ;;
    esac
  done
}

panel_diagnose() {
  if [[ ! -f "$SITE_DIAGNOSTICS" ]]; then
    ui_fail "Не найден $SITE_DIAGNOSTICS"
    return 1
  fi
  INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
    bash "$SITE_DIAGNOSTICS"
}

panel_disable_ip_whitelist() {
  require_root
  local script="$ROOT_DIR/scripts/disable-ip-whitelist.sh"
  if [[ ! -f "$script" ]]; then
    ui_fail "Не найден $script"
    return 1
  fi
  bash "$script" disable
}

panel_nginx_repair() {
  require_root
  bash "$ROOT_DIR/scripts/nginx-repair.sh"
}

menu_emergency() {
  while true; do
    menu_screen "Аварийно" "Назад" "Восстановить nginx для панели" "Отключить белый список IP"
    menu_read 2 назад
    case "$MENU_CHOICE" in
      1) menu_action panel_nginx_repair ;;
      2) menu_action panel_disable_ip_whitelist ;;
      0) return 0 ;;
      *) menu_invalid ;;
    esac
  done
}

menu_render_main() {
  menu_header "$1"
  printf '\n'
  menu_item 1 "Обновить и перезапустить"
  menu_item 2 "Журнал"
  menu_item 3 "Диагностика сайта"
  menu_item 4 "Перезапустить панель"
  menu_item 5 "Сервисы: nginx, агент, DDNS"
  menu_item 6 "Бэкап и восстановление"
  menu_item 7 "Сброс пароля / 2FA"
  menu_item 8 "Аварийно: nginx, белый список IP"
  if [[ "$1" == both ]]; then
    menu_item 9 "Агент узла"
    menu_item 10 "Полное обновление (код + конфигурация сервера)"
  else
    menu_item 9 "Полное обновление (код + конфигурация сервера)"
  fi
  printf '\n'
  menu_item 0 "Выход"
}

main_menu() {
  local mode="${1:-panel}" full=9
  if [[ "$mode" == both ]]; then
    full=10
  fi
  while true; do
    menu_probe_screen "$mode"
    menu_render_main "$mode"
    menu_read "$full" выход
    case "$MENU_CHOICE" in
      1) menu_action panel_update_interactive ;;
      2) menu_logs "$SERVICE_NAME" ;;
      3) menu_action panel_diagnose ;;
      4) menu_action panel_restart_and_wait ;;
      5) menu_services ;;
      6) menu_backups ;;
      7) menu_action panel_reset_password ;;
      8) menu_emergency ;;
      "$full") menu_action menu_full_update ;;
      9) menu_agent ;;
      0) exit 0 ;;
      *) menu_invalid ;;
    esac
  done
}

# Установленные агенты узла — имена unit'ов без .service.
menu_agent_units() {
  local unit
  for unit in adminpanelaz-node adminpanelaz-proxy; do
    if [[ -f "$UNIT_DIR/$unit.service" ]]; then
      printf '%s\n' "$unit"
    fi
  done
  return 0
}

menu_mode() {
  local agents
  agents="$(menu_agent_units)"
  if panel_uses_systemd; then
    if [[ -n "$agents" ]]; then
      echo both
    else
      echo panel
    fi
  elif [[ -n "$agents" ]]; then
    echo agent
  else
    echo none
  fi
}

# Агент с неверными настройками (например, mTLS без сертификатов) падает сразу после старта — смотрим через 5 с.
agent_restart() {
  require_root
  local unit="$1"
  systemctl restart "$unit"
  ui_info "Перезапуск $unit, проверка через 5 с…"
  sleep 5
  if [[ "$(_menu_unit_state "$unit")" == "работает" ]]; then
    ui_ok "$unit работает"
    return 0
  fi
  ui_fail "$unit не запустился — посмотрите журнал агента"
  return 1
}

agent_update() {
  local unit="$1"
  PANEL_UPDATE_CHANGED=false
  panel_update
  [[ "$PANEL_UPDATE_CHANGED" == true ]] || return 0
  if ! menu_confirm "Перезапустить $unit сейчас?" y; then
    ui_info "Агент не перезапущен: systemctl restart $unit"
    return 0
  fi
  agent_restart "$unit"
}

agent_mtls_check() {
  local env_file="$INSTALL_DIR/backend/node_agent.env" warning flag
  if [[ ! -f "$UNIT_DIR/adminpanelaz-node.service" ]]; then
    ui_info "mTLS проверяется для node agent — на этом сервере его нет"
    return 0
  fi
  # shellcheck source=scripts/node-agent-mtls-check.sh
  source "$ROOT_DIR/scripts/node-agent-mtls-check.sh"
  warning="$(node_agent_mtls_warning "$env_file")"
  if [[ -n "$warning" ]]; then
    ui_fail "$warning"
    return 1
  fi
  flag="$(sed -n 's/^NODE_AGENT_MTLS_ENABLED=//p' "$env_file" 2>/dev/null | tail -1)" || true
  case "${flag,,}" in
    1 | true | yes) ui_ok "mTLS включён, сертификаты на месте" ;;
    *) ui_info "mTLS выключен (NODE_AGENT_MTLS_ENABLED в $env_file)" ;;
  esac
}

# Агент для действия — в MENU_AGENT. Если стоят node и proxy, спросить; 0 или неверный ввод — код 1.
menu_pick_agent() {
  local i
  local -a units=()
  mapfile -t units < <(menu_agent_units)
  if [[ "${#units[@]}" -eq 1 ]]; then
    MENU_AGENT="${units[0]}"
    return 0
  fi
  printf '\nКакой агент?\n'
  for i in "${!units[@]}"; do
    menu_item "$((i + 1))" "${units[i]#adminpanelaz-}"
  done
  menu_item 0 "Назад"
  menu_read "${#units[@]}" назад
  if menu_valid_choice "${#units[@]}"; then
    MENU_AGENT="${units[MENU_CHOICE - 1]}"
    return 0
  fi
  if [[ "$MENU_CHOICE" != 0 ]]; then
    menu_invalid
  fi
  return 1
}

menu_render_agent() {
  menu_header agent
  printf '\n'
  menu_item 1 "Обновить и перезапустить агент"
  menu_item 2 "Журнал"
  menu_item 3 "Проверка mTLS"
  menu_item 4 "Перезапустить агент"
  menu_item 5 "Статус"
  menu_item 6 "Полное обновление (код + конфигурация сервера)"
  printf '\n'
  menu_item 0 "$1"
}

# menu_agent [top]: top — сервер без панели, меню агента главное («0 Выход»).
menu_agent() {
  local zero=Назад quit=назад
  if [[ "${1:-}" == top ]]; then
    zero=Выход
    quit=выход
  fi
  while true; do
    menu_probe_screen agent
    menu_render_agent "$zero"
    menu_read 6 "$quit"
    case "$MENU_CHOICE" in
      1) if menu_pick_agent; then menu_action agent_update "$MENU_AGENT"; fi ;;
      2) if menu_pick_agent; then menu_logs "$MENU_AGENT"; fi ;;
      3) menu_action agent_mtls_check ;;
      4) if menu_pick_agent; then menu_action agent_restart "$MENU_AGENT"; fi ;;
      5) if menu_pick_agent; then menu_action unit_status "$MENU_AGENT"; fi ;;
      6) menu_action menu_full_update ;;
      0)
        if [[ "$zero" == Выход ]]; then
          exit 0
        fi
        return 0
        ;;
      *) menu_invalid ;;
    esac
  done
}

menu_start() {
  local mode
  mode="$(menu_mode)"
  if [[ "$mode" == none ]]; then
    ui_fail "AdminPanelAZ не установлена через systemd"
    usage >&2
    return 1
  fi
  trap 'menu_interrupted' INT
  if [[ "$mode" == agent ]]; then
    menu_agent top
  else
    main_menu "$mode"
  fi
}

usage() {
  cat <<EOF
Использование: sudo adminpanelaz [опция]   (или sudo ./scripts/adminpanel-menu.sh [опция])

Ops-меню сервера без веб-интерфейса (не мастер install.sh): состояние, журнал, обновление
с перезапуском, бэкап и восстановление, сброс пароля, сервисы. На сервере только с агентом
(--node-only / --proxy-only) — меню агента. Без root меню перезапускается через sudo.

Опции:
  --status               Состояние: версия, сервис, health, адрес (без root, если хватает прав)
  --restart              Перезапустить панель (systemctl restart adminpanelaz)
  --update               git fetch + fast-forward из upstream текущей ветки (main без upstream —
                         origin/main) + pip + сборка интерфейса (если есть обновления
                         или интерфейс собран до последнего обновления кода); без перезапуска
  --backup               Создать резервную копию (scripts/backup-cli.py)
  --diagnose             Диагностика запуска (scripts/site-diagnostics.sh)
  --disable-ip-whitelist Аварийно выключить IP-whitelist панели
  --help                 Эта справка (без root)

Без опций — интерактивное меню (нужен терминал).

Коды выхода:
  0    успех
  1    ошибка действия; для --status — панель или агент не работает
  2    неверный аргумент или меню без терминала
  130  прервано Ctrl+C

Установка / переустановка: sudo ./install.sh
EOF
}

# Без прав на чтение backend/.env --status не узнает порт health и адрес — тогда через sudo.
_menu_can_read() {
  [[ ! -e "$1" || -r "$1" ]]
}

main() {
  case "${1:-}" in
    --help | -h)
      usage
      return 0
      ;;
    --after-pull)
      # Шаг panel_update, уже запущенного от root: повторный sudo сбросил бы INSTALL_DIR, VENV_PATH и PATH.
      panel_after_pull
      return
      ;;
    --status)
      if ! _menu_can_read "$INSTALL_DIR/backend/.env"; then
        menu_ensure_root "$@"
      fi
      menu_status
      return
      ;;
    --restart | --update | --backup | --diagnose | --disable-ip-whitelist) ;;
    "")
      if [[ ! -t 0 || ! -t 1 ]]; then
        usage >&2
        exit 2
      fi
      ;;
    *)
      ui_fail "Неизвестный аргумент: $1"
      usage >&2
      exit 2
      ;;
  esac
  menu_ensure_root "$@"

  case "${1:-}" in
    --restart)
      panel_restart
      ;;
    --update)
      panel_update
      ;;
    --backup)
      panel_backup
      ;;
    --diagnose)
      panel_diagnose
      exit $?
      ;;
    --disable-ip-whitelist)
      panel_disable_ip_whitelist
      exit $?
      ;;
    "")
      menu_start
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
