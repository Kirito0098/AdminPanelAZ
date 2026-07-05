#!/usr/bin/env bash
# Интерактивный мастер установки AdminPanelAZ (вызывается только из install.sh)
# Не запускайте напрямую — используйте: sudo ./install.sh
set -euo pipefail

# shellcheck disable=SC2034
WIZ_INSTALL_TYPE="${WIZ_INSTALL_TYPE:-controller}"
WIZ_REQUIRE_ANTIZAPRET="${WIZ_REQUIRE_ANTIZAPRET:-false}"
WIZ_ANTIZAPRET_PATH="${WIZ_ANTIZAPRET_PATH:-/root/antizapret}"
WIZ_BACKEND_HOST="${WIZ_BACKEND_HOST:-127.0.0.1}"
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
WIZ_APP_ENV="${WIZ_APP_ENV:-development}"
WIZ_ENFORCE_PASSWORD_POLICY="${WIZ_ENFORCE_PASSWORD_POLICY:-false}"
WIZ_NGINX_MODE="${WIZ_NGINX_MODE:-none}"
WIZ_NGINX_DOMAIN="${WIZ_NGINX_DOMAIN:-}"
WIZ_NGINX_EMAIL="${WIZ_NGINX_EMAIL:-}"
WIZ_ADMIN_USERNAME="${WIZ_ADMIN_USERNAME:-admin}"
WIZ_ADMIN_PASSWORD="${WIZ_ADMIN_PASSWORD:-admin}"
WIZ_ADMIN_MUST_CHANGE_PASSWORD="${WIZ_ADMIN_MUST_CHANGE_PASSWORD:-true}"
WIZ_NODE_AGENT_PORT="${WIZ_NODE_AGENT_PORT:-9100}"
WIZ_NODE_AGENT_API_KEY="${WIZ_NODE_AGENT_API_KEY:-}"
WIZ_NODE_AGENT_ALLOWED_IPS="${WIZ_NODE_AGENT_ALLOWED_IPS:-}"
WIZ_AUTH_RATE_LIMIT_BACKEND="${WIZ_AUTH_RATE_LIMIT_BACKEND:-memory}"
WIZ_API_RATE_LIMIT_BACKEND="${WIZ_API_RATE_LIMIT_BACKEND:-memory}"
WIZ_REDIS_URL="${WIZ_REDIS_URL:-}"
WIZ_RESOURCE_PROFILE="${WIZ_RESOURCE_PROFILE:-standard}"
WIZ_NODE_AGENT_MTLS_ENABLED="${WIZ_NODE_AGENT_MTLS_ENABLED:-false}"
WIZ_NODE_API_KEY_ROTATION_DAYS="${WIZ_NODE_API_KEY_ROTATION_DAYS:-0}"
WIZ_RUN_MODE="${WIZ_RUN_MODE:-manual}"
WIZ_CIDR_DB_REFRESH_ENABLED="${WIZ_CIDR_DB_REFRESH_ENABLED:-true}"
WIZ_CIDR_DB_REFRESH_HOUR="${WIZ_CIDR_DB_REFRESH_HOUR:-2}"
WIZ_CIDR_DB_REFRESH_MINUTE="${WIZ_CIDR_DB_REFRESH_MINUTE:-30}"
WIZ_TRAFFIC_SYNC_ENABLED="${WIZ_TRAFFIC_SYNC_ENABLED:-true}"
WIZ_TELEGRAM_ENABLED="${WIZ_TELEGRAM_ENABLED:-false}"
WIZ_TELEGRAM_BOT_TOKEN="${WIZ_TELEGRAM_BOT_TOKEN:-}"
WIZ_TELEGRAM_CHAT_ID="${WIZ_TELEGRAM_CHAT_ID:-}"
WIZ_AUTO_BACKUP_ENABLED="${WIZ_AUTO_BACKUP_ENABLED:-false}"
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

wiz_set_total_steps() {
  case "$WIZ_INSTALL_TYPE" in
    node)
      WIZ_TOTAL_STEPS=6
      ;;
    controller)
      WIZ_TOTAL_STEPS=12
      ;;
    *)
      WIZ_TOTAL_STEPS=12
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
    read -r -s -p "Подтвердите пароль: " reply2
    echo
    if [[ "$reply" == "$reply2" ]]; then
      REPLY="$reply"
      return 0
    fi
    echo "Пароли не совпадают, повторите."
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

wiz_prompt_port() {
  local prompt="$1"
  local default="$2"

  while true; do
    wiz_prompt "$prompt" "$default"
    if [[ "$REPLY" =~ ^[0-9]+$ ]] && (( REPLY >= 1 && REPLY <= 65535 )); then
      return 0
    fi
    echo "Введите число от 1 до 65535."
  done
}

wiz_prompt_port_no_conflict() {
  local prompt="$1"
  local default="$2"
  shift 2
  local -a forbidden=("$@")

  while true; do
    wiz_prompt_port "$prompt" "$default"
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
  local options=("$@")
  local i choice

  echo "$prompt"
  for i in "${!options[@]}"; do
    echo "  $((i + 1))) ${options[$i]}"
  done

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="1"
    echo "Выбор [1]: ${options[0]}"
    return 0
  fi

  while true; do
    read -r -p "Ваш выбор [1-${#options[@]}] (Enter = 1): " choice
    choice="${choice:-1}"
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      REPLY="$choice"
      return 0
    fi
    echo "  Введите номер от 1 до ${#options[@]} (или Enter для варианта 1)."
  done
}

wizard_derive_cors_origins() {
  local port="$1"
  local origins="http://127.0.0.1:${port},http://localhost:${port},http://127.0.0.1:5173,http://localhost:5173"

  if [[ -n "$WIZ_SERVER_ADDRESS" ]]; then
    local addr="$WIZ_SERVER_ADDRESS"
    addr="${addr#http://}"
    addr="${addr#https://}"
    addr="${addr%%/*}"
    origins="${origins},http://${addr}:${port},https://${addr}:${port}"
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
  wiz_prompt_choice "Какой компонент устанавливаем?" \
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
  wiz_set_total_steps
  echo
}

wizard_ask_network() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    wiz_step "Порты node agent"
    wiz_prompt_port "Порт node agent" "$WIZ_NODE_AGENT_PORT"
    WIZ_NODE_AGENT_PORT="$REPLY"
    echo
    return 0
  fi

  wiz_step "Сеть и порты"
  ui_info_box "Как устроен доступ" \
    "Backend слушает только 127.0.0.1 — с других машин напрямую не откроется." \
    "Наружу — через Nginx (настраивается на шаге «Публикация»)." \
    "Enter — доступ только с localhost; IP или домен можно указать позже."
  echo
  wiz_prompt "Внешний IP или домен (для CORS и подсказок; Enter — localhost)" "$WIZ_SERVER_ADDRESS"
  WIZ_SERVER_ADDRESS="$REPLY"
  if [[ -z "$WIZ_SERVER_ADDRESS" ]]; then
    print_info "По умолчанию: только localhost (127.0.0.1). Домен — на шаге публикации через Nginx."
  fi
  wiz_prompt_port "Внутренний порт backend (только localhost)" "$WIZ_BACKEND_PORT"
  WIZ_BACKEND_PORT="$REPLY"
  WIZ_BACKEND_HOST="127.0.0.1"
  wizard_derive_cors_origins "$WIZ_BACKEND_PORT"

  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    wiz_prompt_port_no_conflict "Порт node agent" "$WIZ_NODE_AGENT_PORT" "$WIZ_BACKEND_PORT"
    WIZ_NODE_AGENT_PORT="$REPLY"
  fi

  print_info "Внутренние IP (10.x, 192.168.x, 172.16-31.x) нужны, только если узлы"
  print_info "в одной локальной сети с панелью. Обычно узлы в интернете — отвечайте 'n'."
  wiz_prompt_yesno "Разрешить внутренние (приватные) IP для узлов?" "n"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_ALLOW_INTERNAL_NODES="true"
  else
    WIZ_ALLOW_INTERNAL_NODES="false"
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

wizard_ask_ddns() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "Динамический DNS"
  print_info "Если нет своего домена — бесплатный DDNS (подробнее в README.md, раздел «Бесплатные домены»)."
  echo
  wiz_prompt_choice "Провайдер DDNS" \
    "Не использую DDNS (свой домен или IP)" \
    "DuckDNS (*.duckdns.org) — рекомендуется для homelab" \
    "No-IP (*.ddns.net и др.)"

  case "$REPLY" in
    1) WIZ_DDNS_PROVIDER="none" ;;
    2) WIZ_DDNS_PROVIDER="duckdns" ;;
    3) WIZ_DDNS_PROVIDER="noip" ;;
  esac

  if [[ "$WIZ_DDNS_PROVIDER" == "duckdns" ]]; then
    echo
    echo "  Зарегистрируйтесь на https://www.duckdns.org и создайте поддомен."
    echo "  Токен — на странице домена (token)."
    wiz_prompt "Поддомен DuckDNS (без .duckdns.org)" "$WIZ_DDNS_SUBDOMAIN"
    WIZ_DDNS_SUBDOMAIN="${REPLY,,}"
    WIZ_DDNS_SUBDOMAIN="${WIZ_DDNS_SUBDOMAIN%.duckdns.org}"
    wiz_prompt_secret "DuckDNS token" "$WIZ_DDNS_TOKEN"
    WIZ_DDNS_TOKEN="$REPLY"
    local fqdn="${WIZ_DDNS_SUBDOMAIN}.duckdns.org"
    if [[ -z "$WIZ_SERVER_ADDRESS" ]]; then
      WIZ_SERVER_ADDRESS="$fqdn"
    fi
    echo "  Полное имя: $fqdn"
  elif [[ "$WIZ_DDNS_PROVIDER" == "noip" ]]; then
    echo
    echo "  Зарегистрируйтесь на https://www.noip.com и создайте hostname."
    wiz_prompt "Полное имя хоста No-IP (например, myvpn.ddns.net)" "$WIZ_DDNS_HOSTNAME"
    WIZ_DDNS_HOSTNAME="$REPLY"
    wiz_prompt "Логин No-IP" "$WIZ_DDNS_USERNAME"
    WIZ_DDNS_USERNAME="$REPLY"
    wiz_prompt_secret "Пароль No-IP" "$WIZ_DDNS_PASSWORD"
    WIZ_DDNS_PASSWORD="$REPLY"
    if [[ -z "$WIZ_SERVER_ADDRESS" ]]; then
      WIZ_SERVER_ADDRESS="$WIZ_DDNS_HOSTNAME"
    fi
  fi

  if [[ "$WIZ_DDNS_PROVIDER" != "none" ]]; then
    wiz_prompt_yesno "Настроить автоматическое обновление IP (systemd timer, каждые 5 мин)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_DDNS_CONFIGURE_UPDATE="true"
    else
      WIZ_DDNS_CONFIGURE_UPDATE="false"
      echo "  Обновляйте IP вручную: sudo ./scripts/ddns-update.sh update"
    fi
    echo "  Перед Let's Encrypt IP должен указывать на этот сервер (порты 80/443)."
  fi
  echo
}

wizard_ask_app_env() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "Режим приложения и безопасность"
  ui_info_box "" \
    "APP_ENV=production — проверка секретов, политика паролей, усиленные заголовки." \
    "Для доступа из интернета/LAN рекомендуется production + HTTPS (см. SECURITY.md)."
  echo
  wiz_prompt_choice "Режим APP_ENV" \
    "development (локальная разработка / тесты)" \
    "production (рекомендуется для сетевого доступа)"

  case "$REPLY" in
    1) WIZ_APP_ENV="development" ;;
    2) WIZ_APP_ENV="production" ;;
  esac

  if [[ "$WIZ_APP_ENV" == "production" ]]; then
    WIZ_ENFORCE_PASSWORD_POLICY="true"
    echo "  SECRET_KEY будет сгенерирован автоматически при установке."
  else
    wiz_prompt_yesno "Включить политику паролей (ENFORCE_PASSWORD_POLICY)?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_ENFORCE_PASSWORD_POLICY="true"
    else
      WIZ_ENFORCE_PASSWORD_POLICY="false"
    fi
  fi
  echo
}

wizard_ask_https() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "Публикация и HTTPS"
  ui_info_box "Рекомендуется" \
    "Nginx: панель на 127.0.0.1, снаружи только HTTPS через прокси." \
    "Uvicorn + HTTPS: TLS на самом приложении (как в AdminAntizapret), без nginx." \
    "Позже можно изменить: ./scripts/nginx-setup.sh"
  echo
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_NGINX_MODE="none"
    WIZ_BACKEND_HOST="127.0.0.1"
    WIZ_BEHIND_NGINX="false"
    echo "Способ публикации [7]: Пропустить (только localhost, dev/тесты)"
    print_info "Backend будет доступен только на http://127.0.0.1:${WIZ_BACKEND_PORT}/"
    echo
    return 0
  fi
  wiz_prompt_choice "Способ публикации" \
    "Nginx + Let's Encrypt (домен, рекомендуется для интернета)" \
    "Nginx + самоподписанный сертификат (LAN / внутренняя сеть)" \
    "Nginx + собственные сертификаты" \
    "HTTPS на uvicorn + Let's Encrypt (без nginx, standalone certbot)" \
    "HTTPS на uvicorn + собственные сертификаты (без nginx, cert от 3x-ui и т.п.)" \
    "HTTPS на uvicorn + самоподписанный (без nginx)" \
    "Пропустить (только localhost, dev/тесты)" \
    "HTTP напрямую без TLS (LAN / тесты, не для интернета)"

  case "$REPLY" in
    1) WIZ_NGINX_MODE="le" ;;
    2) WIZ_NGINX_MODE="selfsigned" ;;
    3) WIZ_NGINX_MODE="nginx_custom" ;;
    4) WIZ_NGINX_MODE="uvicorn_le" ;;
    5) WIZ_NGINX_MODE="uvicorn_custom" ;;
    6) WIZ_NGINX_MODE="uvicorn_selfsigned" ;;
    7) WIZ_NGINX_MODE="none" ;;
    8) WIZ_NGINX_MODE="http_direct" ;;
  esac

  local default_domain
  default_domain="$(wizard_ddns_fqdn)"
  if [[ -z "$default_domain" ]]; then
    default_domain="${WIZ_SERVER_ADDRESS:-}"
    default_domain="${default_domain#http://}"
    default_domain="${default_domain#https://}"
    default_domain="${default_domain%%/*}"
    default_domain="${default_domain%%:*}"
  fi

  if [[ "$WIZ_NGINX_MODE" == "le" || "$WIZ_NGINX_MODE" == "selfsigned" || "$WIZ_NGINX_MODE" == "nginx_custom" ]]; then
    WIZ_BACKEND_HOST="127.0.0.1"
    WIZ_BEHIND_NGINX="true"
    wiz_prompt "Домен для сертификата и server_name" "${default_domain:-panel.example.com}"
    WIZ_NGINX_DOMAIN="$REPLY"
    if [[ "$WIZ_NGINX_MODE" == "le" ]]; then
      wiz_prompt "Email для Let's Encrypt (пусто — без email)" "$WIZ_NGINX_EMAIL"
      WIZ_NGINX_EMAIL="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTPS-порт панели (nginx)" "$WIZ_HTTPS_PUBLIC_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT"
      WIZ_HTTPS_PUBLIC_PORT="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTP-порт для ACME" "$WIZ_HTTP_ACME_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT" "$WIZ_HTTPS_PUBLIC_PORT"
      WIZ_HTTP_ACME_PORT="$REPLY"
      if [[ "$WIZ_HTTP_ACME_PORT" != "80" ]]; then
        print_warn "Let's Encrypt проверяет домен на порту 80. Нестандартный порт может потребовать DNS-challenge."
      fi
    elif [[ "$WIZ_NGINX_MODE" == "nginx_custom" ]]; then
      wiz_prompt_port_no_conflict "Публичный HTTPS-порт панели (nginx)" "$WIZ_HTTPS_PUBLIC_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT"
      WIZ_HTTPS_PUBLIC_PORT="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTP-порт (редирект на HTTPS)" "$WIZ_HTTP_ACME_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT" "$WIZ_HTTPS_PUBLIC_PORT"
      WIZ_HTTP_ACME_PORT="$REPLY"
      while true; do
        wiz_prompt "Путь к сертификату (.crt/.pem)" "${WIZ_SSL_CERT:-}"
        WIZ_SSL_CERT="$REPLY"
        [[ -f "$WIZ_SSL_CERT" ]] && break
        print_warn "Файл не найден: $WIZ_SSL_CERT"
      done
      while true; do
        wiz_prompt "Путь к приватному ключу (.key)" "${WIZ_SSL_KEY:-}"
        WIZ_SSL_KEY="$REPLY"
        [[ -f "$WIZ_SSL_KEY" ]] && break
        print_warn "Файл не найден: $WIZ_SSL_KEY"
      done
    else
      wiz_prompt_port_no_conflict "Публичный HTTPS-порт панели (nginx)" "$WIZ_HTTPS_PUBLIC_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT"
      WIZ_HTTPS_PUBLIC_PORT="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTP-порт (редирект на HTTPS)" "$WIZ_HTTP_ACME_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT" "$WIZ_HTTPS_PUBLIC_PORT"
      WIZ_HTTP_ACME_PORT="$REPLY"
    fi
    if [[ "$WIZ_APP_ENV" == "production" ]]; then
      wizard_build_nginx_cors_origins "$WIZ_NGINX_DOMAIN" "$WIZ_HTTPS_PUBLIC_PORT" "$WIZ_BACKEND_PORT"
    fi
  elif [[ "$WIZ_NGINX_MODE" == uvicorn_* ]]; then
    WIZ_BACKEND_HOST="0.0.0.0"
    WIZ_BEHIND_NGINX="false"
    wiz_prompt "Домен для HTTPS" "${default_domain:-panel.example.com}"
    WIZ_NGINX_DOMAIN="$REPLY"
    wiz_prompt_port_no_conflict "Порт HTTPS панели (uvicorn слушает этот порт)" "${WIZ_BACKEND_PORT:-8000}" \
      "$WIZ_NODE_AGENT_PORT"
    WIZ_BACKEND_PORT="$REPLY"
    WIZ_HTTPS_PUBLIC_PORT="$REPLY"
    if [[ "$WIZ_NGINX_MODE" == "uvicorn_le" ]]; then
      wiz_prompt "Email для Let's Encrypt (пусто — без email)" "$WIZ_NGINX_EMAIL"
      WIZ_NGINX_EMAIL="$REPLY"
    elif [[ "$WIZ_NGINX_MODE" == "uvicorn_custom" ]]; then
      while true; do
        wiz_prompt "Путь к сертификату (.crt/.pem)" "${WIZ_SSL_CERT:-}"
        WIZ_SSL_CERT="$REPLY"
        [[ -f "$WIZ_SSL_CERT" ]] && break
        print_warn "Файл не найден: $WIZ_SSL_CERT"
      done
      while true; do
        wiz_prompt "Путь к приватному ключу (.key)" "${WIZ_SSL_KEY:-}"
        WIZ_SSL_KEY="$REPLY"
        [[ -f "$WIZ_SSL_KEY" ]] && break
        print_warn "Файл не найден: $WIZ_SSL_KEY"
      done
    fi
    if [[ "$WIZ_APP_ENV" == "production" ]]; then
      local pub_host="$WIZ_NGINX_DOMAIN"
      if [[ "$WIZ_BACKEND_PORT" != "443" ]]; then
        pub_host="${pub_host}:${WIZ_BACKEND_PORT}"
      fi
      WIZ_CORS_ORIGINS="https://${pub_host},http://127.0.0.1:${WIZ_BACKEND_PORT},http://localhost:${WIZ_BACKEND_PORT}"
      WIZ_CORS_ORIGINS+=",http://127.0.0.1:5173,http://localhost:5173"
    fi
    print_info "Uvicorn будет слушать https://0.0.0.0:${WIZ_BACKEND_PORT}/ (TLS на приложении, без nginx)"
  elif [[ "$WIZ_NGINX_MODE" == "none" ]]; then
    WIZ_BACKEND_HOST="127.0.0.1"
    WIZ_BEHIND_NGINX="false"
    print_info "Backend будет доступен только на http://127.0.0.1:${WIZ_BACKEND_PORT}/"
  else
    WIZ_BACKEND_HOST="0.0.0.0"
    WIZ_BEHIND_NGINX="false"
    print_warn "uvicorn будет слушать 0.0.0.0:${WIZ_BACKEND_PORT} — не используйте в интернете без firewall."
  fi
  echo
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

wizard_ask_security_hardening() {
  wiz_step "Дополнительная безопасность (необязательно)"
  ui_info_box "Можно пропустить" \
    "Это усиленные настройки для продвинутых сценариев — не обязательны." \
    "mTLS — взаимные TLS-сертификаты между панелью и узлом (надёжнее, но" \
    "сложнее: нужно сгенерировать сертификаты отдельным скриптом)." \
    "Ротация API-ключа — автоматическая периодическая смена ключа узлов." \
    "Если не уверены — отвечайте 'n' (значения по умолчанию безопасны)."
  echo
  # Сброс: mTLS только при явном «да» на этом шаге (не наследуем pre-export из окружения).
  WIZ_NODE_AGENT_MTLS_ENABLED="false"

  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    wiz_prompt_yesno "Включить mTLS для node agent (требует scripts/generate-mtls-certs.sh)?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_NODE_AGENT_MTLS_ENABLED="true"
      echo "  После установки: sudo ./scripts/generate-mtls-certs.sh"
    fi
    echo
    return 0
  fi

  if [[ "$WIZ_UVICORN_WORKERS" -gt 1 ]]; then
    wizard_show_redis_rate_limit_hint
    wiz_prompt_yesno "Настроить Redis для rate limit (auth + API)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_AUTH_RATE_LIMIT_BACKEND="redis"
      WIZ_API_RATE_LIMIT_BACKEND="redis"
      wiz_prompt "REDIS_URL" "redis://127.0.0.1:6379/0"
      WIZ_REDIS_URL="$REPLY"
    fi
  fi
  wiz_prompt_yesno "Включить mTLS между панелью и node agent?" "n"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_NODE_AGENT_MTLS_ENABLED="true"
    echo "  После установки: sudo ./scripts/generate-mtls-certs.sh"
  fi
  wiz_prompt "Автоматическая ротация API-ключа узлов (дней, 0 = выкл)" "$WIZ_NODE_API_KEY_ROTATION_DAYS"
  WIZ_NODE_API_KEY_ROTATION_DAYS="$REPLY"
  echo
}

wizard_ask_firewall() {
  wiz_step "Firewall"
  local has_nginx=false
  local has_node=false
  local backend_port="$WIZ_BACKEND_PORT"

  if [[ "$WIZ_NGINX_MODE" == "le" || "$WIZ_NGINX_MODE" == "selfsigned" ]]; then
    has_nginx=true
  fi
  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    has_node=true
  fi
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    has_node=true
    has_nginx=false
    backend_port="0"
  fi

  print_info "Рекомендуется закрыть внутренние порты с интернета и открыть только Nginx."
  echo

  # shellcheck source=scripts/firewall-setup.sh
  source "$ROOT_DIR/scripts/firewall-setup.sh"
  firewall_show_rules_summary "$backend_port" "$WIZ_NODE_AGENT_PORT" \
    "$WIZ_HTTPS_PUBLIC_PORT" "$WIZ_HTTP_ACME_PORT" "$has_node" "$has_nginx" \
    "${WIZ_NODE_AGENT_ALLOWED_IPS:-${WIZ_SERVER_ADDRESS:-}}"

  echo
  local fw_default="n"
  if [[ "$WIZ_APP_ENV" == "production" ]]; then
    fw_default="y"
  fi
  wiz_prompt_yesno "Настроить firewall автоматически (ufw/iptables)?" "$fw_default"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_CONFIGURE_FIREWALL="true"
    local tool
    tool="$(firewall_detect_tool)"
    if [[ "$tool" == "ufw" ]]; then
      wiz_prompt_yesno "Включить ufw, если он ещё не активен?" "y"
      if [[ "$REPLY" == "y" ]]; then
        WIZ_FIREWALL_ENABLE_UFW="true"
      fi
    elif [[ "$tool" == "none" ]]; then
      print_warn "ufw/iptables не найдены — после установки будут показаны команды вручную."
    fi
  else
    WIZ_CONFIGURE_FIREWALL="false"
    print_info "Настройте firewall вручную (см. SECURITY.md)."
  fi
  echo
}

wizard_ask_services() {
  wiz_step "Сервисы и автозапуск"
  ui_info_box "Как держать панель запущенной" \
    "Вручную — запускаете командой сами; удобно для проверки и разработки." \
    "Daemon — фоновый процесс с авто-перезапуском (watchdog), без systemd." \
    "Systemd — системный сервис: автозапуск при загрузке (рекомендуется)."
  echo
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_RUN_MODE="systemd"
    echo "Как запускать после установки? [3]: Systemd (рекомендуется для production)"
  else
    wiz_prompt_choice "Как запускать после установки?" \
      "Вручную (./start.sh / ./start_node_agent.sh)" \
      "Daemon через start.sh (watchdog)" \
      "Systemd (рекомендуется для production)"

    case "$REPLY" in
      1) WIZ_RUN_MODE="manual" ;;
      2) WIZ_RUN_MODE="daemon" ;;
      3) WIZ_RUN_MODE="systemd" ;;
    esac
  fi

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    local workers_default="$WIZ_UVICORN_WORKERS"
    if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
      WIZ_UVICORN_WORKERS="1"
    else
      print_info "Workers — параллельные процессы backend. Для большинства серверов"
      print_info "оставьте 1. Больше 1 имеет смысл под высокой нагрузкой (и требует Redis)."
      wiz_prompt "Количество uvicorn workers (1 = по умолчанию, >1 требует Redis для rate limit)" "$workers_default"
      if [[ "$REPLY" =~ ^[0-9]+$ ]] && (( REPLY >= 1 && REPLY <= 32 )); then
        WIZ_UVICORN_WORKERS="$REPLY"
      else
        WIZ_UVICORN_WORKERS="1"
      fi
      if [[ "$WIZ_UVICORN_WORKERS" -gt 1 ]]; then
        wizard_show_redis_rate_limit_hint
      fi
    fi
  fi
  echo
}

wizard_ask_resource_profile() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "Профиль ресурсов (VDS)"
  echo "Замер стека Full (панель + локальная нода): ≈411 MB (358+53); среднее за 7 дн. ~148 MB."
  echo "Minimal — для VDS 1 GB только под панель (без AntiZapret на том же хосте)."
  wiz_prompt_choice "Resource profile:" \
    "Minimal — 1 GB, panel-only (без traffic/CIDR collectors)" \
    "Standard — баланс (1 GB+, без CIDR scheduler)" \
    "Full — все фоновые задачи (≈411 MB стек; 1 GB+ / лучше 2 GB с VPN на хосте)"

  case "$REPLY" in
    1) WIZ_RESOURCE_PROFILE="minimal" ;;
    2) WIZ_RESOURCE_PROFILE="standard" ;;
    3) WIZ_RESOURCE_PROFILE="full" ;;
    *) WIZ_RESOURCE_PROFILE="standard" ;;
  esac
  echo "Выбран профиль: $WIZ_RESOURCE_PROFILE"
  echo
}

wizard_ask_optional() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "Опциональные функции"

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    if [[ "$WIZ_RESOURCE_PROFILE" == "minimal" ]]; then
      WIZ_CIDR_DB_REFRESH_ENABLED="false"
      WIZ_TRAFFIC_SYNC_ENABLED="false"
      WIZ_UVICORN_WORKERS="1"
      print_info "Minimal profile: CIDR scheduler и traffic sync отключены."
    elif [[ "$WIZ_RESOURCE_PROFILE" == "full" ]]; then
      WIZ_CIDR_DB_REFRESH_ENABLED="true"
      WIZ_TRAFFIC_SYNC_ENABLED="true"
    fi

    if [[ "$WIZ_RESOURCE_PROFILE" != "minimal" ]]; then
      wiz_prompt_yesno "Включить ночное обновление CIDR DB (CIDR_DB_REFRESH_ENABLED)?" "y"
      if [[ "$REPLY" == "y" ]]; then
        WIZ_CIDR_DB_REFRESH_ENABLED="true"
        wiz_prompt "Час запуска (0-23)" "$WIZ_CIDR_DB_REFRESH_HOUR"
        WIZ_CIDR_DB_REFRESH_HOUR="$REPLY"
        wiz_prompt "Минута запуска (0-59)" "$WIZ_CIDR_DB_REFRESH_MINUTE"
        WIZ_CIDR_DB_REFRESH_MINUTE="$REPLY"
      else
        WIZ_CIDR_DB_REFRESH_ENABLED="false"
      fi
    fi

    if [[ "$WIZ_RESOURCE_PROFILE" != "minimal" ]]; then
      wiz_prompt_yesno "Включить сбор трафика (TRAFFIC_SYNC_ENABLED)?" "y"
      if [[ "$REPLY" == "y" ]]; then
        WIZ_TRAFFIC_SYNC_ENABLED="true"
      else
        WIZ_TRAFFIC_SYNC_ENABLED="false"
      fi
    fi

    wiz_prompt_yesno "Настроить Telegram-уведомления (опционально, только bot token и chat_id)?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_TELEGRAM_ENABLED="true"
      print_info "Модуль Telegram и Mini App включаются позже в панели: Настройки → Модули → Telegram."
      wiz_prompt "Telegram Bot Token" ""
      WIZ_TELEGRAM_BOT_TOKEN="$REPLY"
      wiz_prompt "Telegram Chat ID" ""
      WIZ_TELEGRAM_CHAT_ID="$REPLY"
    fi

    wiz_prompt_yesno "Включить автоматические бэкапы?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_AUTO_BACKUP_ENABLED="true"
      wiz_prompt "Интервал автобэкапа (дней)" "$WIZ_AUTO_BACKUP_DAYS"
      WIZ_AUTO_BACKUP_DAYS="$REPLY"
    fi
  fi
  echo
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
    ui_summary_row "Доступ" "${WIZ_SERVER_ADDRESS:-localhost (127.0.0.1)}"
    if [[ "$WIZ_DDNS_PROVIDER" != "none" ]]; then
      ui_summary_row "DDNS" "$WIZ_DDNS_PROVIDER ($(wizard_ddns_fqdn))"
      ui_summary_row "DDNS auto-update" "$WIZ_DDNS_CONFIGURE_UPDATE"
    fi
    ui_summary_row "Backend (внутр.)" "${WIZ_BACKEND_HOST}:${WIZ_BACKEND_PORT} (только localhost)"
    ui_summary_row "Публикация (Nginx)" "$WIZ_NGINX_MODE"
    if [[ "$WIZ_NGINX_MODE" != "none" && -n "$WIZ_NGINX_DOMAIN" ]]; then
      ui_summary_row "Домен" "$WIZ_NGINX_DOMAIN"
      if [[ "$WIZ_NGINX_MODE" == "le" || "$WIZ_NGINX_MODE" == "selfsigned" ]]; then
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
    if [[ "$WIZ_UVICORN_WORKERS" -gt 1 ]]; then
      ui_summary_row "Rate limit" "${WIZ_AUTH_RATE_LIMIT_BACKEND}/${WIZ_API_RATE_LIMIT_BACKEND}${WIZ_REDIS_URL:+, REDIS_URL=$WIZ_REDIS_URL}"
    fi
    ui_summary_row "Профиль ресурсов" "$WIZ_RESOURCE_PROFILE"
    ui_summary_row "Обновление CIDR" "$WIZ_CIDR_DB_REFRESH_ENABLED"
    ui_summary_row "Сбор трафика" "$WIZ_TRAFFIC_SYNC_ENABLED"
    ui_summary_row "Telegram" "$WIZ_TELEGRAM_ENABLED"
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
  ui_summary_row "Настроить firewall" "$WIZ_CONFIGURE_FIREWALL"
  if [[ "$WIZ_INSTALL_TYPE" != "node" && "$WIZ_APP_ENV" == "production" && "$WIZ_NGINX_MODE" == "none" ]]; then
    echo
    print_warn "APP_ENV=production без HTTPS — для интернета настройте Nginx (./scripts/nginx-setup.sh)."
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
  if ui_confirm "Применить конфигурацию и начать установку?" "n"; then
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
    "Почти всё можно изменить позже в backend/.env и скриптах в scripts/."
  echo
  print_info "Подсказка: ответы 'y' (да) / 'n' (нет); выбор из списка — номер варианта."
  echo

  wizard_ask_install_type
  wizard_configure_antizapret
  wizard_ask_network
  wizard_ask_ddns
  wizard_ask_app_env
  wizard_ask_https
  wizard_ask_admin
  wizard_ask_node_agent
  wizard_ask_services
  wizard_ask_security_hardening
  wizard_ask_resource_profile
  wizard_ask_optional
  wizard_ask_paths
  wizard_ask_firewall
  wizard_show_summary
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
