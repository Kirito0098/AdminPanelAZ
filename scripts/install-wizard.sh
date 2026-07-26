#!/usr/bin/env bash
# Интерактивный мастер установки AdminPanelAZ (вызывается только из install.sh)
# Не запускайте напрямую — используйте: sudo ./install.sh
set -euo pipefail

# shellcheck disable=SC2034
WIZ_INSTALL_TYPE="${WIZ_INSTALL_TYPE:-controller}"
WIZ_REQUIRE_ANTIZAPRET="${WIZ_REQUIRE_ANTIZAPRET:-true}"
WIZ_ANTIZAPRET_PATH="${WIZ_ANTIZAPRET_PATH:-/root/antizapret}"
WIZ_BACKEND_HOST="${WIZ_BACKEND_HOST:-0.0.0.0}"
WIZ_BACKEND_PORT="${WIZ_BACKEND_PORT:-8000}"
WIZ_HTTPS_PUBLIC_PORT="${WIZ_HTTPS_PUBLIC_PORT:-443}"
WIZ_HTTP_ACME_PORT="${WIZ_HTTP_ACME_PORT:-80}"
WIZ_CONFIGURE_FIREWALL="${WIZ_CONFIGURE_FIREWALL:-false}"
WIZ_FIREWALL_ENABLE_UFW="${WIZ_FIREWALL_ENABLE_UFW:-false}"
WIZ_UVICORN_WORKERS="${WIZ_UVICORN_WORKERS:-1}"
WIZ_BEHIND_NGINX="${WIZ_BEHIND_NGINX:-false}"
WIZ_SERVER_ADDRESS="${WIZ_SERVER_ADDRESS:-}"
WIZ_DDNS_PROVIDER="${WIZ_DDNS_PROVIDER:-none}"
WIZ_DDNS_SUBDOMAIN="${WIZ_DDNS_SUBDOMAIN:-}"
WIZ_DDNS_TOKEN="${WIZ_DDNS_TOKEN:-}"
WIZ_DDNS_HOSTNAME="${WIZ_DDNS_HOSTNAME:-}"
WIZ_DDNS_USERNAME="${WIZ_DDNS_USERNAME:-}"
WIZ_DDNS_PASSWORD="${WIZ_DDNS_PASSWORD:-}"
WIZ_DDNS_CONFIGURE_UPDATE="${WIZ_DDNS_CONFIGURE_UPDATE:-false}"
WIZ_CORS_ORIGINS="${WIZ_CORS_ORIGINS:-}"
WIZ_ALLOW_INTERNAL_NODES="${WIZ_ALLOW_INTERNAL_NODES:-false}"
WIZ_APP_ENV="${WIZ_APP_ENV:-production}"
WIZ_ENFORCE_PASSWORD_POLICY="${WIZ_ENFORCE_PASSWORD_POLICY:-true}"
# Дефолт публикации: HTTP напрямую. Env/CI может задать le|uvicorn_*|… до запуска мастера.
WIZ_NGINX_MODE="${WIZ_NGINX_MODE:-http_direct}"
# Запомним preset извне (до apply defaults), чтобы уважать CI-override.
_WIZ_NGINX_MODE_PRESET="${WIZ_NGINX_MODE}"
WIZ_NGINX_DOMAIN="${WIZ_NGINX_DOMAIN:-}"
WIZ_NGINX_EMAIL="${WIZ_NGINX_EMAIL:-}"
WIZ_ACCESS_PATH="${WIZ_ACCESS_PATH:-}"
WIZ_NGINX_SUBPATH_INTEGRATE="${WIZ_NGINX_SUBPATH_INTEGRATE:-false}"
WIZ_ADMIN_USERNAME="${WIZ_ADMIN_USERNAME:-admin}"
WIZ_ADMIN_PASSWORD="${WIZ_ADMIN_PASSWORD:-admin}"
WIZ_ADMIN_MUST_CHANGE_PASSWORD="${WIZ_ADMIN_MUST_CHANGE_PASSWORD:-true}"
WIZ_NODE_AGENT_PORT="${WIZ_NODE_AGENT_PORT:-9100}"
WIZ_NODE_AGENT_API_KEY="${WIZ_NODE_AGENT_API_KEY:-}"
WIZ_NODE_AGENT_ALLOWED_IPS="${WIZ_NODE_AGENT_ALLOWED_IPS:-}"
WIZ_AUTH_RATE_LIMIT_BACKEND="${WIZ_AUTH_RATE_LIMIT_BACKEND:-memory}"
WIZ_API_RATE_LIMIT_BACKEND="${WIZ_API_RATE_LIMIT_BACKEND:-memory}"
WIZ_REDIS_URL="${WIZ_REDIS_URL:-}"
WIZ_RESOURCE_PROFILE="${WIZ_RESOURCE_PROFILE:-full}"
WIZ_NODE_AGENT_MTLS_ENABLED="${WIZ_NODE_AGENT_MTLS_ENABLED:-false}"
WIZ_NODE_API_KEY_ROTATION_DAYS="${WIZ_NODE_API_KEY_ROTATION_DAYS:-0}"
WIZ_RUN_MODE="${WIZ_RUN_MODE:-systemd}"
WIZ_CIDR_DB_REFRESH_ENABLED="${WIZ_CIDR_DB_REFRESH_ENABLED:-true}"
WIZ_CIDR_DB_REFRESH_HOUR="${WIZ_CIDR_DB_REFRESH_HOUR:-2}"
WIZ_CIDR_DB_REFRESH_MINUTE="${WIZ_CIDR_DB_REFRESH_MINUTE:-30}"
WIZ_TRAFFIC_SYNC_ENABLED="${WIZ_TRAFFIC_SYNC_ENABLED:-true}"
WIZ_TELEGRAM_ENABLED="${WIZ_TELEGRAM_ENABLED:-false}"
WIZ_TELEGRAM_BOT_TOKEN="${WIZ_TELEGRAM_BOT_TOKEN:-}"
WIZ_TELEGRAM_CHAT_ID="${WIZ_TELEGRAM_CHAT_ID:-}"
WIZ_AUTO_BACKUP_ENABLED="${WIZ_AUTO_BACKUP_ENABLED:-true}"
WIZ_AUTO_BACKUP_DAYS="${WIZ_AUTO_BACKUP_DAYS:-7}"
WIZ_STATE_DIR="${WIZ_STATE_DIR:-}"
WIZ_NODE_STATE_DIR="${WIZ_NODE_STATE_DIR:-}"
WIZ_BACKUP_ROOT="${WIZ_BACKUP_ROOT:-/var/backups/adminpanelaz}"

WIZ_ACCEPT_DEFAULTS="${WIZ_ACCEPT_DEFAULTS:-false}"
WIZ_APPLY_CONFIRMED="${WIZ_APPLY_CONFIRMED:-false}"
WIZ_CURRENT_STEP=0
WIZ_TOTAL_STEPS="?"

if [[ "${UI_INITIALIZED:-false}" != true ]]; then
  # shellcheck source=scripts/install-ui.sh
  source "$ROOT_DIR/scripts/install-ui.sh"
  ui_init
fi

# shellcheck source=scripts/install-port-check.sh
source "$ROOT_DIR/scripts/install-port-check.sh"

wiz_set_total_steps() {
  case "$WIZ_INSTALL_TYPE" in
    node)
      # тип → порты → node agent
      WIZ_TOTAL_STEPS=3
      ;;
    controller)
      # тип → сеть → admin → paths (DDNS — в панели)
      WIZ_TOTAL_STEPS=4
      ;;
    *)
      # тип → сеть → admin → node agent → paths
      WIZ_TOTAL_STEPS=5
      ;;
  esac
}

wiz_title() {
  echo
  ui_section "$*"
}

wiz_summary_section() {
  echo
  ui_bold "  [ $1 ]"
  echo
}

wiz_step() {
  local title="$1"
  title="${title#*[0-9]*. }"
  title="${title#*[0-9a-z]a. }"
  (( ++WIZ_CURRENT_STEP )) || true
  ui_step_header "$WIZ_CURRENT_STEP" "$WIZ_TOTAL_STEPS" "$title"
}

wiz_prompt() {
  local prompt="$1"
  local default="${2:-}"
  local reply=""

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    if [[ -n "$default" ]]; then
      REPLY="$default"
    else
      REPLY=""
    fi
    echo "$prompt [$default]"
    return 0
  fi

  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " reply
    REPLY="${reply:-$default}"
  else
    read -r -p "$prompt: " reply
    REPLY="$reply"
  fi
}

wiz_prompt_secret() {
  local prompt="$1"
  local default="${2:-}"
  # 3-й аргумент: текст подтверждения. Пустая строка "" — без повторного ввода (token).
  # Не передан — «Подтвердите пароль» (No-IP и т.п.).
  local confirm_label="${3-Подтвердите пароль}"
  local reply=""
  local reply2=""

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="$default"
    echo "$prompt [***]"
    return 0
  fi

  while true; do
    read -r -s -p "$prompt: " reply
    echo
    if [[ -z "$reply" && -n "$default" ]]; then
      REPLY="$default"
      return 0
    fi
    if [[ -z "$confirm_label" ]]; then
      REPLY="$reply"
      return 0
    fi
    read -r -s -p "${confirm_label}: " reply2
    echo
    if [[ "$reply" == "$reply2" ]]; then
      REPLY="$reply"
      return 0
    fi
    echo "Значения не совпадают, повторите."
  done
}

wiz_prompt_yesno() {
  local prompt="$1"
  local default="${2:-n}"
  local reply=""

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="$default"
    echo "$prompt [${default}]"
    return 0
  fi

  local hint="y/N"
  if [[ "$default" == "y" ]]; then
    hint="Y/n"
  fi

  read -r -p "$prompt [$hint]: " reply
  reply="${reply:-$default}"
  case "$reply" in
    y|Y|yes|Yes|да|Да)
      REPLY="y"
      ;;
    *)
      REPLY="n"
      ;;
  esac
}

# Опциональные 3–4 аргументы: role_label, bind_hint (any|127.0.0.1).
# После выбора числа проверяет занятость порта в системе.
wiz_prompt_port() {
  local prompt="$1"
  local default="$2"
  local role="${3:-порт}"
  local bind_hint="${4:-any}"

  while true; do
    wiz_prompt "$prompt" "$default"
    if [[ ! "$REPLY" =~ ^[0-9]+$ ]] || (( REPLY < 1 || REPLY > 65535 )); then
      echo "Введите число от 1 до 65535."
      continue
    fi
    local port="$REPLY"
    # quiet=1: сообщение покажем один раз в ui_warn_box ниже
    if port_check_available "$port" "$role" "$bind_hint" 1; then
      REPLY="$port"
      return 0
    fi
    if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
      die "${role}: порт ${port} занят ($(port_listener_info "$port")). Укажите свободный порт или остановите конфликтующий сервис."
    fi
    if declare -F ui_warn_box >/dev/null 2>&1; then
      ui_warn_box "Порт ${port} занят (${role})" \
        "$(port_listener_info "$port")" \
        "Выберите другой порт или остановите конфликтующий сервис."
    else
      print_warn "${role}: порт ${port} уже занят — $(port_listener_info "$port")"
      echo "Выберите другой порт."
    fi
    default="$port"
  done
}

wiz_prompt_port_no_conflict() {
  local prompt="$1"
  local default="$2"
  shift 2
  local role="порт"
  local bind_hint="any"
  # Опционально: если первый из хвоста не число — это role, второй — bind_hint
  if [[ $# -gt 0 && ! "${1:-}" =~ ^[0-9]+$ ]]; then
    role="$1"
    shift
    if [[ $# -gt 0 && ! "${1:-}" =~ ^[0-9]+$ ]]; then
      bind_hint="$1"
      shift
    fi
  fi
  local -a forbidden=("$@")

  while true; do
    wiz_prompt_port "$prompt" "$default" "$role" "$bind_hint"
    local port="$REPLY"
    local f
    for f in "${forbidden[@]}"; do
      if [[ -n "$f" && "$port" == "$f" ]]; then
        echo "Порт ${port} уже используется другим сервисом установки. Выберите другой."
        continue 2
      fi
    done
    return 0
  done
}

wizard_show_redis_rate_limit_hint() {
  echo
  ui_info_box "Rate limit и несколько воркеров uvicorn" \
    "Uvicorn workers — отдельные процессы, обрабатывающие запросы." \
    "In-memory счётчик лимита входа хранится в каждом процессе отдельно:" \
    "атакующий может обойти лимит, попадая на разные workers." \
    "Redis — общее хранилище счётчиков для всех workers." \
    "При 1 worker достаточно AUTH_RATE_LIMIT_BACKEND=memory (по умолчанию)." \
    "При workers > 1 задайте AUTH_RATE_LIMIT_BACKEND=redis и REDIS_URL."
  echo
}

wiz_prompt_choice() {
  local prompt="$1"
  shift
  local default_choice=1
  if [[ "${1:-}" =~ ^[0-9]+$ ]] && [[ -n "${2:-}" ]]; then
    default_choice="$1"
    shift
  fi
  local options=("$@")
  local i choice

  echo "$prompt"
  for i in "${!options[@]}"; do
    if (( i + 1 == default_choice )); then
      echo "  $((i + 1))) ${options[$i]} (по умолчанию)"
    else
      echo "  $((i + 1))) ${options[$i]}"
    fi
  done

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="$default_choice"
    echo "Выбор [${default_choice}]: ${options[$((default_choice - 1))]}"
    return 0
  fi

  while true; do
    read -r -p "Ваш выбор [1-${#options[@]}] (Enter = ${default_choice}): " choice
    choice="${choice:-$default_choice}"
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      REPLY="$choice"
      return 0
    fi
    echo "  Введите номер от 1 до ${#options[@]} (или Enter для варианта ${default_choice})."
  done
}

# Primary IPv4 сервера (для CORS / summary URL). Переиспользует nginx_server_primary_ip.
wizard_detect_primary_ip() {
  if ! declare -F nginx_server_primary_ip >/dev/null 2>&1; then
    # shellcheck source=scripts/nginx-common.sh
    source "$ROOT_DIR/scripts/nginx-common.sh"
  fi
  nginx_server_primary_ip
}

# Хост для подсказки URL: авто-IP, иначе FQDN из DDNS, иначе placeholder.
wizard_public_access_host() {
  local ip="" fqdn=""
  ip="$(wizard_detect_primary_ip 2>/dev/null || true)"
  if [[ -n "$ip" ]]; then
    printf '%s' "$ip"
    return 0
  fi
  if declare -F wizard_ddns_fqdn >/dev/null 2>&1; then
    fqdn="$(wizard_ddns_fqdn)"
  fi
  if [[ -n "$fqdn" ]]; then
    printf '%s' "$fqdn"
    return 0
  fi
  if [[ -n "${WIZ_SERVER_ADDRESS:-}" ]]; then
    local addr="$WIZ_SERVER_ADDRESS"
    addr="${addr#http://}"
    addr="${addr#https://}"
    addr="${addr%%/*}"
    addr="${addr%%:*}"
    if [[ -n "$addr" ]]; then
      printf '%s' "$addr"
      return 0
    fi
  fi
  printf '%s' '<IP>'
}

wizard_derive_cors_origins() {
  local port="$1"
  local origins="http://127.0.0.1:${port},http://localhost:${port},http://127.0.0.1:5173,http://localhost:5173"
  local addr fqdn ip origin

  ip="$(wizard_detect_primary_ip 2>/dev/null || true)"
  if [[ -n "$ip" ]]; then
    origin="http://${ip}:${port}"
    case ",${origins}," in
      *",${origin},"*) ;;
      *) origins="${origins},${origin}" ;;
    esac
  fi

  # Env-override: WIZ_SERVER_ADDRESS снаружи (интерактивно не спрашиваем)
  if [[ -n "${WIZ_SERVER_ADDRESS:-}" ]]; then
    addr="$WIZ_SERVER_ADDRESS"
    addr="${addr#http://}"
    addr="${addr#https://}"
    addr="${addr%%/*}"
    if [[ -n "$addr" ]]; then
      for origin in "http://${addr}:${port}" "https://${addr}:${port}"; do
        case ",${origins}," in
          *",${origin},"*) ;;
          *) origins="${origins},${origin}" ;;
        esac
      done
    fi
  fi

  if declare -F wizard_ddns_fqdn >/dev/null 2>&1; then
    fqdn="$(wizard_ddns_fqdn)"
    if [[ -n "$fqdn" ]]; then
      origin="http://${fqdn}:${port}"
      case ",${origins}," in
        *",${origin},"*) ;;
        *) origins="${origins},${origin}" ;;
      esac
    fi
  fi

  WIZ_CORS_ORIGINS="$origins"
}

wizard_build_nginx_cors_origins() {
  local domain="$1"
  local https_port="$2"
  local backend_port="$3"
  local public_host="$domain"
  if [[ "$https_port" != "443" ]]; then
    public_host="${domain}:${https_port}"
  fi
  WIZ_CORS_ORIGINS="https://${public_host},http://${public_host},http://127.0.0.1:${backend_port},http://localhost:${backend_port}"
}

# Нормализованный ACCESS_PATH: '' или '/segment' (без хвостового /).
wizard_normalized_access_path() {
  local raw="${1:-${WIZ_ACCESS_PATH:-}}"
  raw="${raw// /}"
  raw="${raw#/}"
  raw="${raw%/}"
  if [[ -z "$raw" ]]; then
    printf ''
    return 0
  fi
  printf '/%s' "$raw"
}

# Суффикс для URL: '/' или '/panel/'.
wizard_access_path_url_suffix() {
  local p
  p="$(wizard_normalized_access_path "${1:-${WIZ_ACCESS_PATH:-}}")"
  if [[ -z "$p" ]]; then
    printf '/'
  else
    printf '%s/' "$p"
  fi
}

wizard_access_path_is_reserved() {
  local normalized="$1"
  local first
  [[ -n "$normalized" ]] || return 1
  first="${normalized#/}"
  first="${first%%/*}"
  first="${first,,}"
  case "$first" in
    status|api|assets|metrics) return 0 ;;
  esac
  case "$normalized" in
    /.well-known|/.well-known/*|/robots.txt|/robots.txt/*) return 0 ;;
  esac
  return 1
}

wizard_prompt_custom_access_path() {
  local reply normalized
  while true; do
    wiz_prompt "Подпуть панели (без слэша, например panel)" "panel"
    reply="${REPLY// /}"
    reply="${reply#/}"
    reply="${reply%/}"
    if [[ -z "$reply" ]]; then
      print_warn "Пустой подпуть — выберите «Корень домена» в меню выше."
      continue
    fi
    if [[ "$reply" == *".."* ]]; then
      print_warn "Подпуть не должен содержать '..'"
      continue
    fi
    if [[ ! "$reply" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*(/[a-zA-Z0-9][a-zA-Z0-9_-]*)*$ ]]; then
      print_warn "Допустимы буквы, цифры, _ и - (сегменты через /)."
      continue
    fi
    normalized="/${reply}"
    if wizard_access_path_is_reserved "$normalized"; then
      print_warn "Путь ${normalized} зарезервирован (нельзя: status, api, assets, …)."
      continue
    fi
    WIZ_ACCESS_PATH="$reply"
    return 0
  done
}

wizard_ask_maybe_subpath_integrate() {
  local domain="${1:-$WIZ_NGINX_DOMAIN}"
  WIZ_NGINX_SUBPATH_INTEGRATE="false"
  [[ -n "$(wizard_normalized_access_path)" ]] || return 0
  [[ -n "$domain" ]] || return 0
  if ! nginx_has_foreign_vhost_for_domain "$domain" 2>/dev/null; then
    return 0
  fi
  echo
  if nginx_has_status_openvpn_vhost_for_domain "$domain" 2>/dev/null; then
    ui_info_box "Чужой nginx vhost" \
      "На домене ${domain} найден StatusOpenVPN или другой сайт." \
      "Можно автоматически добавить include сниппета панели в существующий vhost."
  else
    ui_info_box "Чужой nginx vhost" \
      "На домене ${domain} уже есть nginx-сайт." \
      "Можно автоматически добавить include сниппета панели в существующий vhost."
  fi
  echo
  wiz_prompt_yesno "Автоматически добавить include в существующий vhost?" "y"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_NGINX_SUBPATH_INTEGRATE="true"
  fi
}

# Подпуть ACCESS_PATH и интеграция со StatusOpenVPN / чужим vhost (только nginx-режимы).
wizard_ask_access_path_and_status() {
  local domain="${WIZ_NGINX_DOMAIN:-}"

  if [[ "${WIZ_ACCEPT_DEFAULTS}" == true ]]; then
    WIZ_ACCESS_PATH="${WIZ_ACCESS_PATH:-}"
    WIZ_NGINX_SUBPATH_INTEGRATE="${WIZ_NGINX_SUBPATH_INTEGRATE:-false}"
    return 0
  fi

  WIZ_ACCESS_PATH=""
  WIZ_NGINX_SUBPATH_INTEGRATE="false"

  # shellcheck source=scripts/nginx-common.sh
  source "$ROOT_DIR/scripts/nginx-common.sh"
  nginx_common_init

  echo
  ui_info_box "Общий домен / подпуть" \
    "Оставьте корень, если панель одна на домене." \
    "/panel — если рядом другие сайты или StatusOpenVPN." \
    "Подпуть — дополнительная мера, не замена 2FA."
  echo

  if [[ -n "$domain" ]] && nginx_has_status_openvpn_vhost_for_domain "$domain" 2>/dev/null; then
    print_success "Обнаружен StatusOpenVPN на ${domain} (/status/)."
    echo
    wiz_prompt_yesno "Установить панель рядом со StatusOpenVPN (подпуть /panel)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_ACCESS_PATH="panel"
      WIZ_NGINX_SUBPATH_INTEGRATE="true"
      print_info "Панель: https://${domain}/panel/ · Status: https://${domain}/status/"
      return 0
    fi
  fi

  wiz_prompt_choice "Где открывать панель на домене?" 1 \
    "Корень домена (https://${domain:-example.com}/)" \
    "Подпуть /panel (https://${domain:-example.com}/panel/)" \
    "Свой подпуть"

  case "$REPLY" in
    1)
      WIZ_ACCESS_PATH=""
      ;;
    2)
      WIZ_ACCESS_PATH="panel"
      ;;
    3)
      wizard_prompt_custom_access_path
      ;;
  esac

  wizard_ask_maybe_subpath_integrate "$domain"
}

wizard_check_antizapret() {
  if [[ -d "$WIZ_ANTIZAPRET_PATH" && -f "$WIZ_ANTIZAPRET_PATH/client.sh" ]]; then
    print_success "AntiZapret найден: $WIZ_ANTIZAPRET_PATH"
    return 0
  fi

  ui_warn_box "AntiZapret не найден" \
    "Каталог: $WIZ_ANTIZAPRET_PATH" \
    "Установите отдельно: https://github.com/GubernievS/AntiZapret-VPN"
  if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
    die "Установка прервана: для выбранного типа нужен AntiZapret в /root/antizapret. Установите его (https://github.com/GubernievS/AntiZapret-VPN) и запустите install.sh заново, либо выберите тип «Только панель»."
  fi
}

wizard_configure_antizapret() {
  WIZ_ANTIZAPRET_PATH="/root/antizapret"
  wizard_check_antizapret
}

wizard_ask_install_type() {
  WIZ_CURRENT_STEP=0
  WIZ_TOTAL_STEPS="?"
  wiz_step "Тип установки"
  ui_info_box "Что именно ставим на этот сервер" \
    "1) Только панель — веб-интерфейс управления; VPN-серверы (AntiZapret)" \
    "   работают на других машинах и подключаются как узлы." \
    "2) Панель + локальный AntiZapret — этот сервер сразу и панель, и VPN" \
    "   (AntiZapret уже должен быть установлен в /root/antizapret)." \
    "3) Только Node agent — это VPN-сервер (узел); панель управляет им с" \
    "   другого хоста." \
    "Не уверены? Один сервер с уже установленным AntiZapret — выберите 2."
  echo
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_INSTALL_TYPE="controller"
    WIZ_REQUIRE_ANTIZAPRET=true
    echo "Какой компонент устанавливаем? [2]: Панель + локальный AntiZapret"
  else
    wiz_prompt_choice "Какой компонент устанавливаем?" 2 \
      "Только панель (управление удалёнными узлами, без локального AntiZapret)" \
      "Панель + локальный AntiZapret (AntiZapret уже установлен в /root/antizapret)" \
      "Только Node agent (удалённый VPN-сервер)"

    case "$REPLY" in
      1)
        WIZ_INSTALL_TYPE="controller"
        WIZ_REQUIRE_ANTIZAPRET=false
        ;;
      2)
        WIZ_INSTALL_TYPE="controller"
        WIZ_REQUIRE_ANTIZAPRET=true
        ;;
      3)
        WIZ_INSTALL_TYPE="node"
        WIZ_REQUIRE_ANTIZAPRET=true
        ;;
    esac
  fi
  wiz_set_total_steps
  echo
}

wizard_ask_network() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    wiz_step "Порты node agent"
    wiz_prompt_port "Порт node agent" "$WIZ_NODE_AGENT_PORT" "Node agent" "any"
    WIZ_NODE_AGENT_PORT="$REPLY"
    echo
    return 0
  fi

  wiz_step "Сеть и порты"
  ui_info_box "Как устроен доступ" \
    "Панель слушает на всех интерфейсах (0.0.0.0) по HTTP — сразу доступна по IP:порту." \
    "Домен и HTTPS настраиваются позже в панели: Настройки → Адрес сайта и HTTPS." \
    "CORS и подсказки URL собираются автоматически (localhost + IP сервера)."
  echo
  # WIZ_SERVER_ADDRESS / ALLOW_INTERNAL_NODES интерактивно не спрашиваем.
  # Env-override WIZ_SERVER_ADDRESS учитывается в wizard_derive_cors_origins.
  # ALLOW_INTERNAL_NODES: всегда false при install (override через env до мастера сохраняется).
  WIZ_ALLOW_INTERNAL_NODES="${WIZ_ALLOW_INTERNAL_NODES:-false}"
  if [[ "$WIZ_ALLOW_INTERNAL_NODES" != "true" ]]; then
    WIZ_ALLOW_INTERNAL_NODES="false"
  fi
  wiz_prompt_port "Порт панели (доступ по IP:порт)" "$WIZ_BACKEND_PORT" "Панель" "any"
  WIZ_BACKEND_PORT="$REPLY"
  # HOST задаёт wizard_apply_default_publish_http_direct (не форсируем 127.0.0.1)

  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    wiz_prompt_port_no_conflict "Порт node agent" "$WIZ_NODE_AGENT_PORT" \
      "Node agent" "any" "$WIZ_BACKEND_PORT"
    WIZ_NODE_AGENT_PORT="$REPLY"
  fi
  echo
}

wizard_ddns_fqdn() {
  case "$WIZ_DDNS_PROVIDER" in
    duckdns)
      if [[ -n "$WIZ_DDNS_SUBDOMAIN" ]]; then
        echo "${WIZ_DDNS_SUBDOMAIN}.duckdns.org"
      fi
      ;;
    noip)
      if [[ -n "$WIZ_DDNS_HOSTNAME" ]]; then
        echo "$WIZ_DDNS_HOSTNAME"
      fi
      ;;
  esac
}

# DDNS интерактивно не спрашиваем — настройка в UI: Настройки → Адрес сайта и HTTPS.
# Env-override (CI): WIZ_DDNS_PROVIDER=duckdns|noip + credentials → setup_ddns_if_selected в install.sh.
wizard_ask_ddns() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi
  # Интерактивно оставляем none, если провайдер не задан извне.
  case "${WIZ_DDNS_PROVIDER:-none}" in
    duckdns|noip)
      if [[ -z "$WIZ_SERVER_ADDRESS" ]]; then
        WIZ_SERVER_ADDRESS="$(wizard_ddns_fqdn)"
      fi
      ;;
    *)
      WIZ_DDNS_PROVIDER="none"
      ;;
  esac
}

# APP_ENV всегда production при install (без интерактивного выбора).
wizard_ask_app_env() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi
  WIZ_APP_ENV="production"
  WIZ_ENFORCE_PASSWORD_POLICY="true"
}

# Дефолт публикации: HTTP напрямую (без интерактивного выбора).
# Env/CI: если WIZ_NGINX_MODE задан извне (не none/http_direct) — уважаем, не спрашиваем.
wizard_apply_default_publish_http_direct() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  local preset="${_WIZ_NGINX_MODE_PRESET:-${WIZ_NGINX_MODE:-http_direct}}"
  case "$preset" in
    ""|none|http_direct)
      WIZ_NGINX_MODE="http_direct"
      WIZ_BACKEND_HOST="0.0.0.0"
      WIZ_BEHIND_NGINX="false"
      # Не задаём DOMAIN/HTTPS/SSL/ACCESS_PATH из этого шага
      WIZ_ACCESS_PATH=""
      WIZ_NGINX_SUBPATH_INTEGRATE="false"
      if [[ "${WIZ_ACCEPT_DEFAULTS}" == true ]]; then
        print_info "Публикация: HTTP напрямую (http_direct) на 0.0.0.0:${WIZ_BACKEND_PORT}"
      fi
      ;;
    le|selfsigned|nginx_custom)
      # CI/env override — host/behind как у nginx-режимов
      WIZ_NGINX_MODE="$preset"
      WIZ_BACKEND_HOST="${WIZ_BACKEND_HOST:-127.0.0.1}"
      if [[ "$WIZ_BACKEND_HOST" == "0.0.0.0" ]]; then
        WIZ_BACKEND_HOST="127.0.0.1"
      fi
      WIZ_BEHIND_NGINX="true"
      print_info "WIZ_NGINX_MODE=${WIZ_NGINX_MODE} (задан извне, шаг публикации пропущен)"
      ;;
    uvicorn_*)
      WIZ_NGINX_MODE="$preset"
      WIZ_BACKEND_HOST="0.0.0.0"
      WIZ_BEHIND_NGINX="false"
      WIZ_ACCESS_PATH=""
      WIZ_NGINX_SUBPATH_INTEGRATE="false"
      print_info "WIZ_NGINX_MODE=${WIZ_NGINX_MODE} (задан извне, шаг публикации пропущен)"
      ;;
    *)
      WIZ_NGINX_MODE="$preset"
      print_info "WIZ_NGINX_MODE=${WIZ_NGINX_MODE} (задан извне, шаг публикации пропущен)"
      ;;
  esac

  wizard_derive_cors_origins "$WIZ_BACKEND_PORT"
}

# Совместимость: интерактивный выбор публикации удалён; HTTPS — только в UI / nginx-setup.
# Env-override WIZ_NGINX_MODE уважается внутри wizard_apply_default_publish_http_direct.
wizard_ask_https() {
  wizard_apply_default_publish_http_direct
}

wizard_ask_admin() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "Администратор"
  wiz_prompt "Имя администратора по умолчанию" "$WIZ_ADMIN_USERNAME"
  WIZ_ADMIN_USERNAME="$REPLY"

  echo "Пароль администратора (Enter — сгенерировать случайный):"
  echo "  Политика (production): минимум 8 символов, буквы и цифры; не используйте admin/admin."
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_ADMIN_PASSWORD="${WIZ_ADMIN_PASSWORD:-admin}"
    echo "  [используется значение по умолчанию]"
  else
    while true; do
      read -r -s -p "Пароль (пусто = сгенерировать случайный): " _admin_pw
      echo
      if [[ -z "$_admin_pw" ]]; then
        WIZ_ADMIN_PASSWORD="$(random_hex | cut -c1-16)"
        echo "  Сгенерирован случайный пароль: $WIZ_ADMIN_PASSWORD"
        echo "  Запишите его — он также будет показан в конце установки."
        break
      fi
      read -r -s -p "Повторите пароль для подтверждения: " _admin_pw2
      echo
      if [[ "$_admin_pw" == "$_admin_pw2" ]]; then
        WIZ_ADMIN_PASSWORD="$_admin_pw"
        break
      fi
      print_warn "Пароли не совпадают — попробуйте ещё раз."
    done
  fi

  wiz_prompt_yesno "Требовать смену пароля при первом входе?" "y"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_ADMIN_MUST_CHANGE_PASSWORD="true"
  else
    WIZ_ADMIN_MUST_CHANGE_PASSWORD="false"
  fi
  echo
}

wizard_ask_node_agent() {
  if [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    return 0
  fi

  wiz_step "Node agent"
  ui_info_box "Что это" \
    "Node agent — служба на VPN-сервере, которой управляет панель." \
    "API-ключ (NODE_AGENT_API_KEY) — общий секрет: панель предъявляет его" \
    "узлу при подключении. Тот же ключ нужно указать в панели для этого узла." \
    "Проще всего сгенерировать ключ автоматически — мы покажем его в конце."
  echo
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    print_info "Порт node agent: ${WIZ_NODE_AGENT_PORT} (задан на шаге сети)"
  fi

  wiz_prompt_yesno "Сгенерировать NODE_AGENT_API_KEY автоматически (рекомендуется)?" "y"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_NODE_AGENT_API_KEY="$(random_hex)"
    echo "  Будет сгенерирован ключ (покажем в конце установки)."
  else
    wiz_prompt_secret "Введите NODE_AGENT_API_KEY (мин. 24 символа в production)" ""
    if [[ -z "$REPLY" ]]; then
      die "Node agent не может работать без API-ключа. Запустите мастер заново и выберите автогенерацию ключа (ответ 'y')."
    fi
    WIZ_NODE_AGENT_API_KEY="$REPLY"
  fi

  print_info "Ограничьте доступ к порту ${WIZ_NODE_AGENT_PORT} firewall: только IP панели управления."
  wiz_prompt "Разрешённые IP панели (NODE_AGENT_ALLOWED_IPS, CIDR через запятую, пусто = без ограничения)" ""
  WIZ_NODE_AGENT_ALLOWED_IPS="$REPLY"
  echo
}

# mTLS / ротация / Redis — не спрашиваем; дефолты off (workers=1 → Redis не нужен).
wizard_ask_security_hardening() {
  WIZ_NODE_AGENT_MTLS_ENABLED="false"
  WIZ_NODE_API_KEY_ROTATION_DAYS="0"
}

# Firewall из мастера не настраиваем (устаревшие правила под nginx+127.0.0.1).
wizard_ask_firewall() {
  WIZ_CONFIGURE_FIREWALL="false"
}

# Запуск всегда systemd, workers=1 (без выбора manual/daemon и без prompt workers).
wizard_ask_services() {
  WIZ_RUN_MODE="systemd"
  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    WIZ_UVICORN_WORKERS="1"
  fi
}

# Профиль ресурсов всегда full (apply-resource-profile вызывается из install.sh).
wizard_ask_resource_profile() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi
  WIZ_RESOURCE_PROFILE="full"
  WIZ_CIDR_DB_REFRESH_ENABLED="true"
  WIZ_TRAFFIC_SYNC_ENABLED="true"
}

# Опциональные функции (Telegram/CIDR/backup) — не спрашиваем в install.
# Telegram token не сеем; CIDR/traffic задаёт full profile; автобэкап — дефолт выше.
wizard_ask_optional() {
  return 0
}

wizard_ask_paths() {
  local default_state="$ROOT_DIR/.runtime"
  local default_node_state="$ROOT_DIR/.runtime/node"

  if [[ "$WIZ_RUN_MODE" == "systemd" ]]; then
    default_state="/var/lib/adminpanelaz"
    default_node_state="/var/lib/adminpanelaz-node"
  fi

  WIZ_STATE_DIR="${WIZ_STATE_DIR:-$default_state}"
  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    WIZ_NODE_STATE_DIR="${WIZ_NODE_STATE_DIR:-$default_node_state}"
  fi

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    wiz_step "Пути"
    wiz_prompt "Каталог бэкапов (BACKUP_ROOT)" "$WIZ_BACKUP_ROOT"
    WIZ_BACKUP_ROOT="$REPLY"
    echo
  fi
}

wizard_apply_run_mode_flags() {
  local cli_with_systemd="${WITH_SYSTEMD:-false}"
  local cli_with_daemon="${WITH_DAEMON:-false}"

  WITH_DAEMON=false
  WITH_SYSTEMD=false
  WITH_NODE_AGENT=false

  case "$WIZ_RUN_MODE" in
    daemon) WITH_DAEMON=true ;;
    systemd) WITH_SYSTEMD=true ;;
  esac

  if [[ "$cli_with_systemd" == true ]]; then
    WITH_SYSTEMD=true
    WITH_DAEMON=false
  elif [[ "$cli_with_daemon" == true ]]; then
    WITH_DAEMON=true
    WITH_SYSTEMD=false
  fi

  case "$WIZ_INSTALL_TYPE" in
    node) WITH_NODE_AGENT=true ;;
  esac

  export ADMINPANELAZ_STATE_DIR="$WIZ_STATE_DIR"
  export NODE_AGENT_STATE_DIR="$WIZ_NODE_STATE_DIR"
  export BACKEND_HOST="$WIZ_BACKEND_HOST"
  export BACKEND_PORT="$WIZ_BACKEND_PORT"
  export UVICORN_WORKERS="$WIZ_UVICORN_WORKERS"
  export ANTIZAPRET_PATH="$WIZ_ANTIZAPRET_PATH"
  export NODE_AGENT_PORT="$WIZ_NODE_AGENT_PORT"
  export NODE_AGENT_API_KEY="$WIZ_NODE_AGENT_API_KEY"
}

wizard_show_summary() {
  wizard_apply_run_mode_flags

  ui_summary_title

  local install_label="$WIZ_INSTALL_TYPE"
  case "$WIZ_INSTALL_TYPE" in
    controller)
      if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
        install_label="панель + локальный AntiZapret"
      else
        install_label="только панель"
      fi
      ;;
    node) install_label="только node agent" ;;
  esac

  wiz_summary_section "Что устанавливаем"
  ui_summary_row "Тип установки" "$install_label"
  ui_summary_row "AntiZapret" "$WIZ_ANTIZAPRET_PATH"

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    wiz_summary_section "Сеть и доступ"
    local access_summary backend_summary access_host
    access_host="$(wizard_public_access_host)"
    case "${WIZ_NGINX_MODE}" in
      uvicorn_*)
        access_summary="https://${WIZ_NGINX_DOMAIN:-<домен>}:${WIZ_BACKEND_PORT}"
        backend_summary="0.0.0.0:${WIZ_BACKEND_PORT} (HTTPS на uvicorn, без Nginx)"
        ;;
      http_direct)
        access_summary="http://${access_host}:${WIZ_BACKEND_PORT}/"
        backend_summary="0.0.0.0:${WIZ_BACKEND_PORT} (HTTP напрямую)"
        ;;
      none)
        access_summary="http://127.0.0.1:${WIZ_BACKEND_PORT}"
        backend_summary="127.0.0.1:${WIZ_BACKEND_PORT} (только localhost)"
        ;;
      le | selfsigned | nginx_custom)
        local path_sfx pub_https
        path_sfx="$(wizard_access_path_url_suffix)"
        pub_https="${WIZ_HTTPS_PUBLIC_PORT:-443}"
        if [[ "$pub_https" == "443" ]]; then
          access_summary="https://${WIZ_NGINX_DOMAIN:-<домен>}${path_sfx}"
        else
          access_summary="https://${WIZ_NGINX_DOMAIN:-<домен>}:${pub_https}${path_sfx}"
        fi
        backend_summary="127.0.0.1:${WIZ_BACKEND_PORT} (за Nginx)"
        ;;
      *)
        access_summary="http://${access_host}:${WIZ_BACKEND_PORT}/"
        backend_summary="${WIZ_BACKEND_HOST}:${WIZ_BACKEND_PORT}"
        ;;
    esac
    ui_summary_row "Доступ" "$access_summary"
    if [[ "$WIZ_DDNS_PROVIDER" != "none" ]]; then
      ui_summary_row "DDNS" "$WIZ_DDNS_PROVIDER ($(wizard_ddns_fqdn))"
      ui_summary_row "DDNS auto-update" "$WIZ_DDNS_CONFIGURE_UPDATE"
    fi
    ui_summary_row "Backend" "$backend_summary"
    if [[ "$WIZ_NGINX_MODE" == "http_direct" ]]; then
      ui_summary_row "Публикация" "HTTP напрямую → HTTPS в панели"
    else
      ui_summary_row "Публикация" "$WIZ_NGINX_MODE"
    fi
    if [[ "$WIZ_NGINX_MODE" != "none" && "$WIZ_NGINX_MODE" != "http_direct" && -n "$WIZ_NGINX_DOMAIN" ]]; then
      ui_summary_row "Домен" "$WIZ_NGINX_DOMAIN"
      if [[ "$WIZ_NGINX_MODE" == "le" || "$WIZ_NGINX_MODE" == "selfsigned" || "$WIZ_NGINX_MODE" == "nginx_custom" ]]; then
        local ap_disp
        ap_disp="$(wizard_normalized_access_path)"
        if [[ -n "$ap_disp" ]]; then
          ui_summary_row "Подпуть" "$ap_disp"
        else
          ui_summary_row "Подпуть" "корень домена"
        fi
        if [[ "${WIZ_NGINX_SUBPATH_INTEGRATE:-false}" == "true" ]]; then
          ui_summary_row "Интеграция vhost" "да (include)"
        fi
        ui_summary_row "Публичные порты" "HTTPS ${WIZ_HTTPS_PUBLIC_PORT}, HTTP ${WIZ_HTTP_ACME_PORT}"
      fi
    fi
    ui_summary_row "CORS" "$WIZ_CORS_ORIGINS"
    ui_summary_row "Внутренние IP узлов" "$WIZ_ALLOW_INTERNAL_NODES"

    wiz_summary_section "Доступ администратора"
    ui_summary_row "Логин" "$WIZ_ADMIN_USERNAME"
    ui_summary_row "Смена пароля при входе" "$WIZ_ADMIN_MUST_CHANGE_PASSWORD"
    ui_summary_row "Политика паролей" "$WIZ_ENFORCE_PASSWORD_POLICY"
    ui_summary_row "Режим (APP_ENV)" "$WIZ_APP_ENV"

    wiz_summary_section "Производительность и задачи"
    ui_summary_row "Uvicorn workers" "$WIZ_UVICORN_WORKERS"
    ui_summary_row "Профиль ресурсов" "$WIZ_RESOURCE_PROFILE"
    ui_summary_row "Обновление CIDR" "$WIZ_CIDR_DB_REFRESH_ENABLED"
    ui_summary_row "Сбор трафика" "$WIZ_TRAFFIC_SYNC_ENABLED"
    ui_summary_row "Авто-бэкап" "$WIZ_AUTO_BACKUP_ENABLED"
    ui_summary_row "Каталог бэкапов" "$WIZ_BACKUP_ROOT"
  fi

  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    wiz_summary_section "Node agent"
    ui_summary_row "Порт" "$WIZ_NODE_AGENT_PORT"
    ui_summary_row "API-ключ" "${WIZ_NODE_AGENT_API_KEY:0:8}... (полностью — в конце установки)"
    ui_summary_row "Разрешённые IP" "${WIZ_NODE_AGENT_ALLOWED_IPS:-(без ограничения)}"
    ui_summary_row "Каталог данных" "$WIZ_NODE_STATE_DIR"
  fi

  wiz_summary_section "Запуск и система"
  ui_summary_row "Каталог данных" "$WIZ_STATE_DIR"
  ui_summary_row "Режим запуска" "$WIZ_RUN_MODE"
  if [[ "$WIZ_INSTALL_TYPE" != "node" && "$WIZ_NGINX_MODE" == "http_direct" ]]; then
    echo
    print_info "HTTPS и домен — в панели: Настройки → Адрес сайта и HTTPS."
  fi
  echo
}

wizard_confirm_apply() {
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_APPLY_CONFIRMED=true
    return 0
  fi

  echo
  ui_separator
  print_info "Дальше: установим зависимости, соберём интерфейс и настроим сервис."
  print_info "Это займёт несколько минут — прогресс будет показан по шагам."
  echo
  if ui_confirm "Применить конфигурацию и начать установку?" "y"; then
    WIZ_APPLY_CONFIRMED=true
    print_success "Конфигурация принята, начинаем установку..."
  else
    WIZ_APPLY_CONFIRMED=false
    print_info "Установка отменена."
    exit 0
  fi
}

run_install_wizard() {
  ui_show_banner
  ui_section "Мастер установки"
  ui_info_box "Как это работает" \
    "Мастер задаст несколько вопросов, а в конце покажет сводку." \
    "Ничего не устанавливается и не меняется, пока вы не подтвердите." \
    "Enter — принять значение по умолчанию (показано в [скобках])." \
    "Если сомневаетесь — оставляйте значения по умолчанию, они безопасны." \
    "Почти всё можно изменить позже в панели (Настройки) и в backend/.env."
  echo
  print_info "Подсказка: ответы 'y' (да) / 'n' (нет); выбор из списка — номер варианта."
  echo

  wizard_ask_install_type
  wizard_configure_antizapret
  wizard_ask_network
  wizard_ask_ddns  # только env-override; интерактивно — none (DDNS в UI)
  wizard_ask_app_env
  wizard_apply_default_publish_http_direct
  wizard_ask_admin
  wizard_ask_node_agent
  wizard_ask_services
  wizard_ask_security_hardening
  wizard_ask_resource_profile
  # optional (Telegram/CIDR/backup prompts) и firewall — не спрашиваем
  WIZ_CONFIGURE_FIREWALL="false"
  wizard_ask_paths
  wizard_show_summary
  echo
  install_preflight_ports
  wizard_confirm_apply
  wizard_apply_run_mode_flags
}

wizard_install_controller() {
  case "$WIZ_INSTALL_TYPE" in
    controller) return 0 ;;
    *) return 1 ;;
  esac
}

wizard_install_node() {
  case "$WIZ_INSTALL_TYPE" in
    node) return 0 ;;
    *) return 1 ;;
  esac
}
