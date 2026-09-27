#!/usr/bin/env bash
# Ops console menu — обёртка над systemd и существующими scripts.
# Не дублирует install.sh wizard; установка: sudo ./install.sh

set -euo pipefail

export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANG="${LANG:-C.UTF-8}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$ROOT_DIR}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/backend/.venv}"
BACKUP_CLI="$ROOT_DIR/scripts/backup-cli.py"
SITE_DIAGNOSTICS="$ROOT_DIR/scripts/site-diagnostics.sh"

GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
RED=$(printf '\033[0;31m')
CYAN=$(printf '\033[0;36m')
NC=$(printf '\033[0m')

ui_ok() { printf "  ${GREEN}✓${NC}  %s\n" "$*"; }
ui_warn() { printf "  ${YELLOW}!${NC}  %s\n" "$*" >&2; }
ui_fail() { printf "  ${RED}✗${NC}  %s\n" "$*" >&2; }
ui_info() { printf "  ${CYAN}i${NC}  %s\n" "$*"; }
ui_section() { printf "\n${CYAN}── %s ──${NC}\n" "$*"; }

_m_border() {
  printf -- '-%.0s' $(seq 1 58)
}

_m_top() { printf "  +%s+\n" "$(_m_border)"; }
_m_bot() { printf "  +%s+\n" "$(_m_border)"; }
_m_sep() { printf "  |%58s|\n" "" | tr ' ' '-'; }
_m_title() {
  local title="$1"
  printf "  | %s" "$title"
  printf "%*s|\n" $((57 - ${#title})) ""
}
_m_item() {
  local text="$1"
  printf "  | %s" "$text"
  printf "%*s|\n" $((57 - ${#text})) ""
}

press_any_key() {
  if [[ -t 0 ]]; then
    printf "\n"
    read -r -p "  Нажмите Enter…" _ || true
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

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    ui_fail "Нужны права root (sudo)."
    exit 1
  fi
}

panel_uses_systemd() {
  [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]
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

panel_status() {
  printf "\n"
  if panel_uses_systemd; then
    systemctl status "$SERVICE_NAME" --no-pager -l || true
  else
    ui_fail "Панель не установлена через systemd ($SERVICE_NAME)"
    return 1
  fi
}

panel_logs() {
  printf "\n"
  if panel_uses_systemd; then
    journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
  elif [[ -d "${ADMINPANELAZ_STATE_DIR:-$ROOT_DIR/.runtime}/logs" ]]; then
    local log_dir="${ADMINPANELAZ_STATE_DIR:-$ROOT_DIR/.runtime}/logs"
    ui_info "Последние строки из $log_dir:"
    tail -n 50 "$log_dir"/*.log 2>/dev/null || ui_warn "Логи не найдены"
  else
    ui_warn "journalctl недоступен; каталог логов не найден"
  fi
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
    mapfile -t seen < <(awk '{ print $1; print $2 }' "$log" | grep -Ex '[0-9a-f]{40}|[0-9a-f]{64}' | grep -vx '0*' | sort -u || true)
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
    if frontend_build_stale; then
      ui_warn "Интерфейс собран до последнего обновления кода"
      if ! panel_build_frontend; then
        panel_frontend_manual_hint
        return 1
      fi
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

  # bash выполняет версию меню, прочитанную до git pull: остальные шаги — уже обновлённым скриптом.
  local menu="$INSTALL_DIR/scripts/adminpanel-menu.sh"
  INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
    "${BASH:-bash}" "$menu" --after-pull
}

# Шаги после git pull; вызывается из panel_update уже обновлённым скриптом.
panel_after_pull() {
  if [[ -x "$VENV_PATH/bin/pip" && -f "$ROOT_DIR/backend/requirements.txt" ]]; then
    ui_info "Обновление Python-зависимостей…"
    if "$VENV_PATH/bin/pip" install -q -r "$ROOT_DIR/backend/requirements.txt"; then
      ui_ok "Зависимости обновлены"
    else
      ui_warn "pip install завершился с ошибкой — проверьте вручную"
    fi
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

  if [[ "$frontend_ok" != true ]]; then
    ui_fail "Код уже обновлён, интерфейс — нет. Повторный $0 --update попробует собрать его снова."
    panel_frontend_manual_hint
    return 1
  fi
  ui_info "Перезапустите панель: $0 --restart"
  return 0
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
    "$py" "$BACKUP_CLI" create 2>&1)"
  code=$?
  set -e
  if [[ "$code" -eq 0 && -n "$archive" ]]; then
    ui_ok "Архив: $archive"
  else
    ui_fail "Бэкап не создан"
    [[ -n "$archive" ]] && printf '%s\n' "$archive" >&2
    return "$code"
  fi
}

panel_diagnose() {
  if [[ ! -f "$SITE_DIAGNOSTICS" ]]; then
    ui_fail "Не найден $SITE_DIAGNOSTICS"
    return 1
  fi
  INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
    bash "$SITE_DIAGNOSTICS"
}

menu_service_panel() {
  while true; do
    clear || true
    _m_top
    _m_title "Сервис панели"
    _m_sep
    _m_item "1. Перезапустить"
    _m_item "2. Статус"
    _m_item "3. Журнал"
    _m_sep
    _m_item "0. Назад"
    _m_bot
    printf "\n"

    read -r -p "  Выберите действие [0-3]: " choice
    case "$choice" in
      1) menu_action panel_restart ;;
      2) menu_action panel_status ;;
      3) menu_action panel_logs ;;
      0) break ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

menu_backups_updates() {
  while true; do
    clear || true
    _m_top
    _m_title "Резервные копии и обновления"
    _m_sep
    _m_item "1. Проверить обновления (git)"
    _m_item "2. Создать резервную копию"
    _m_sep
    _m_item "0. Назад"
    _m_bot
    printf "\n"

    read -r -p "  Выберите действие [0-2]: " choice
    case "$choice" in
      1) menu_action panel_update ;;
      2) menu_action panel_backup ;;
      0) break ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
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

menu_diagnostics() {
  while true; do
    clear || true
    _m_top
    _m_title "Диагностика"
    _m_sep
    _m_item "1. Диагностика запуска сайта"
    _m_item "2. Восстановить nginx для панели"
    _m_item "3. Отключить IP-whitelist (аварийно)"
    _m_sep
    _m_item "0. Назад"
    _m_bot
    printf "\n"

    read -r -p "  Выберите действие [0-3]: " choice
    case "$choice" in
      1) menu_action panel_diagnose ;;
      2) menu_action panel_nginx_repair ;;
      3) menu_action panel_disable_ip_whitelist ;;
      0) break ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

main_menu() {
  while true; do
    clear || true
    _m_top
    _m_title "AdminPanelAZ — Ops console"
    _m_sep
    _m_item "1. Сервис панели"
    _m_item "2. Резервные копии и обновления"
    _m_item "3. Диагностика"
    _m_sep
    _m_item "7. Диагностика запуска сайта"
    _m_sep
    _m_item "0. Выход"
    _m_bot
    printf "\n"
    ui_info "Установка: sudo ./install.sh (не этот скрипт)"

    read -r -p "  Выберите действие [0-7]: " choice
    case "$choice" in
      1) menu_service_panel ;;
      2) menu_backups_updates ;;
      3) menu_diagnostics ;;
      7) menu_action panel_diagnose ;;
      0) exit 0 ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

usage() {
  cat <<EOF
Использование: sudo ./scripts/adminpanel-menu.sh [опция]

Интерактивное ops-меню (без мастера install.sh):
  restart, update, backup, site diagnostics, disable IP whitelist.

Опции (как adminpanel.sh в AA):
  --restart              Перезапустить панель (systemctl restart adminpanelaz)
  --update               git fetch + fast-forward из upstream текущей ветки (main без upstream —
                         origin/main) + pip + сборка интерфейса (если есть обновления
                         или интерфейс собран до последнего обновления кода)
  --backup               Создать резервную копию (scripts/backup-cli.py)
  --diagnose             Диагностика запуска (scripts/site-diagnostics.sh)
  --disable-ip-whitelist Аварийно выключить IP-whitelist панели
  --help                 Эта справка

Без опций — интерактивное меню.
Установка / переустановка: sudo ./install.sh
EOF
}

main() {
  case "${1:-}" in
    --restart)
      panel_restart
      ;;
    --update)
      panel_update
      ;;
    --after-pull)
      panel_after_pull
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
    --help|-h)
      usage
      ;;
    "")
      if [[ ! -t 0 ]]; then
        usage >&2
        exit 1
      fi
      main_menu
      ;;
    *)
      ui_fail "Неизвестный аргумент: $1"
      usage >&2
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
