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
WIZ_REDIS_URL="${WIZ_REDIS_URL:-}"
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

_wiz_use_color=false
if [[ -t 1 ]] && [[ "${TERM:-}" != "dumb" ]]; then
  _wiz_use_color=true
fi

_wiz_c() {
  local code="$1"
  shift
  if [[ "$_wiz_use_color" == true ]]; then
    printf '\033[%sm%s\033[0m' "$code" "$*"
  else
    printf '%s' "$*"
  fi
}

wiz_title() {
  echo
  _wiz_c "1;36" "=== $* ==="
  echo
}

wiz_step() {
  _wiz_c "1;33" "$*"
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
  echo "  ┌─ Rate limit и несколько воркеров uvicorn ─────────────────────────────"
  echo "  │ Uvicorn workers — это отдельные процессы, обрабатывающие запросы."
  echo "  │ In-memory счётчик лимита входа хранится в каждом процессе отдельно:"
  echo "  │ атакующий может обойти лимит, попадая на разные workers."
  echo "  │ Redis — общее хранилище счётчиков для всех workers."
  echo "  │ При 1 worker достаточно AUTH_RATE_LIMIT_BACKEND=memory (по умолчанию)."
  echo "  │ При workers > 1 задайте AUTH_RATE_LIMIT_BACKEND=redis и REDIS_URL."
  echo "  └──────────────────────────────────────────────────────────────────────"
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
    read -r -p "Выберите [1-${#options[@]}]: " choice
    choice="${choice:-1}"
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      REPLY="$choice"
      return 0
    fi
    echo "Неверный выбор."
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

wizard_check_antizapret() {
  if [[ -d "$WIZ_ANTIZAPRET_PATH" && -f "$WIZ_ANTIZAPRET_PATH/client.sh" ]]; then
    echo "  AntiZapret найден: $WIZ_ANTIZAPRET_PATH"
    return 0
  fi

  echo "  ВНИМАНИЕ: AntiZapret не найден в $WIZ_ANTIZAPRET_PATH"
  if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
    die "Установка прервана. Укажите корректный путь к AntiZapret или установите его: https://github.com/GubernievS/AntiZapret-VPN"
  fi
  wiz_prompt_yesno "  Продолжить установку без AntiZapret?" "n"
  if [[ "$REPLY" != "y" ]]; then
    die "Установка прервана. Укажите корректный путь к AntiZapret."
  fi
}

wizard_ask_install_type() {
  wiz_step "1. Тип установки"
  wiz_prompt_choice "Какой компонент устанавливаем?" \
    "Только панель (без локального AntiZapret)" \
    "Панель + локальный AntiZapret" \
    "Только Node agent (удалённый VPN-сервер)" \
    "Полный стек (панель + AntiZapret + Node agent)"

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
    4)
      WIZ_INSTALL_TYPE="controller_node"
      WIZ_REQUIRE_ANTIZAPRET=true
      ;;
  esac
  echo
}

wizard_ask_antizapret() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    wiz_step "2. AntiZapret (на VPN-сервере)"
  else
    wiz_step "2. AntiZapret"
  fi
  wiz_prompt "Путь к каталогу AntiZapret" "$WIZ_ANTIZAPRET_PATH"
  WIZ_ANTIZAPRET_PATH="$REPLY"
  wizard_check_antizapret
  echo
}

wizard_ask_network() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    wiz_step "3. Порты node agent"
    wiz_prompt_port "Порт node agent" "$WIZ_NODE_AGENT_PORT"
    WIZ_NODE_AGENT_PORT="$REPLY"
    echo
    return 0
  fi

  wiz_step "3. Сеть и порты"
  echo "  Рекомендуется: backend только на 127.0.0.1, наружу — через Nginx (шаг 5)."
  echo
  wiz_prompt "IP или домен для доступа к панели (для CORS и подсказок)" "$WIZ_SERVER_ADDRESS"
  WIZ_SERVER_ADDRESS="$REPLY"
  wiz_prompt_port "Внутренний порт backend (только localhost)" "$WIZ_BACKEND_PORT"
  WIZ_BACKEND_PORT="$REPLY"
  WIZ_BACKEND_HOST="127.0.0.1"
  wizard_derive_cors_origins "$WIZ_BACKEND_PORT"

  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    wiz_prompt_port_no_conflict "Порт node agent" "$WIZ_NODE_AGENT_PORT" "$WIZ_BACKEND_PORT"
    WIZ_NODE_AGENT_PORT="$REPLY"
  fi

  wiz_prompt_yesno "Разрешить внутренние IP для удалённых узлов (ALLOW_INTERNAL_NODES)?" "n"
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

  wiz_step "3a. Динамический DNS (бесплатный поддомен)"
  echo "  Если у вас нет своего домена, можно использовать бесплатный DDNS."
  echo "  Подробнее о провайдерах — в README.md (раздел «Бесплатные домены»)."
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

  wiz_step "4. Режим приложения и безопасность"
  echo "  APP_ENV=production включает проверку секретов, политику паролей и усиленные заголовки."
  echo "  Для доступа из интернета/LAN рекомендуется production + HTTPS (см. SECURITY.md)."
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

  wiz_step "5. Публикация через Nginx (рекомендуется)"
  echo "  Панель слушает только 127.0.0.1:${WIZ_BACKEND_PORT}."
  echo "  Наружу — только Nginx на HTTPS (и HTTP для ACME)."
  echo "  Позже можно изменить: ./scripts/nginx-setup.sh"
  echo
  wiz_prompt_choice "Способ публикации" \
    "Nginx + Let's Encrypt (домен, рекомендуется для интернета)" \
    "Nginx + самоподписанный сертификат (LAN / внутренняя сеть)" \
    "Пропустить Nginx (только localhost, dev/тесты)" \
    "HTTP напрямую без Nginx (не рекомендуется для интернета)"

  case "$REPLY" in
    1) WIZ_NGINX_MODE="le" ;;
    2) WIZ_NGINX_MODE="selfsigned" ;;
    3) WIZ_NGINX_MODE="none" ;;
    4) WIZ_NGINX_MODE="http_direct" ;;
  esac

  if [[ "$WIZ_NGINX_MODE" == "le" || "$WIZ_NGINX_MODE" == "selfsigned" ]]; then
    WIZ_BACKEND_HOST="127.0.0.1"
    WIZ_BEHIND_NGINX="true"
    local default_domain
    default_domain="$(wizard_ddns_fqdn)"
    if [[ -z "$default_domain" ]]; then
      default_domain="${WIZ_SERVER_ADDRESS:-}"
      default_domain="${default_domain#http://}"
      default_domain="${default_domain#https://}"
      default_domain="${default_domain%%/*}"
      default_domain="${default_domain%%:*}"
    fi
    wiz_prompt "Домен для сертификата и server_name" "${default_domain:-panel.example.com}"
    WIZ_NGINX_DOMAIN="$REPLY"
    if [[ "$WIZ_NGINX_MODE" == "le" ]]; then
      wiz_prompt "Email для Let's Encrypt (пусто — без email)" "$WIZ_NGINX_EMAIL"
      WIZ_NGINX_EMAIL="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTPS-порт (Nginx)" "$WIZ_HTTPS_PUBLIC_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT"
      WIZ_HTTPS_PUBLIC_PORT="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTP-порт для ACME" "$WIZ_HTTP_ACME_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT" "$WIZ_HTTPS_PUBLIC_PORT"
      WIZ_HTTP_ACME_PORT="$REPLY"
      if [[ "$WIZ_HTTP_ACME_PORT" != "80" ]]; then
        echo "  ВНИМАНИЕ: Let's Encrypt проверяет домен на порту 80. Нестандартный порт может потребовать DNS-challenge."
      fi
    else
      wiz_prompt_port_no_conflict "Публичный HTTPS-порт (Nginx)" "$WIZ_HTTPS_PUBLIC_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT"
      WIZ_HTTPS_PUBLIC_PORT="$REPLY"
      wiz_prompt_port_no_conflict "Публичный HTTP-порт (редирект на HTTPS)" "$WIZ_HTTP_ACME_PORT" \
        "$WIZ_BACKEND_PORT" "$WIZ_NODE_AGENT_PORT" "$WIZ_HTTPS_PUBLIC_PORT"
      WIZ_HTTP_ACME_PORT="$REPLY"
    fi
    if [[ "$WIZ_APP_ENV" == "production" ]]; then
      WIZ_CORS_ORIGINS="https://${WIZ_NGINX_DOMAIN},http://${WIZ_NGINX_DOMAIN},http://127.0.0.1:${WIZ_BACKEND_PORT},http://localhost:${WIZ_BACKEND_PORT}"
    fi
  elif [[ "$WIZ_NGINX_MODE" == "none" ]]; then
    WIZ_BACKEND_HOST="127.0.0.1"
    WIZ_BEHIND_NGINX="false"
    echo "  Backend будет доступен только на http://127.0.0.1:${WIZ_BACKEND_PORT}/"
  else
    WIZ_BACKEND_HOST="0.0.0.0"
    WIZ_BEHIND_NGINX="false"
    echo "  ВНИМАНИЕ: uvicorn будет слушать 0.0.0.0:${WIZ_BACKEND_PORT} — не используйте в интернете без firewall."
  fi
  echo
}

wizard_ask_admin() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "6. Администратор"
  wiz_prompt "Имя администратора по умолчанию" "$WIZ_ADMIN_USERNAME"
  WIZ_ADMIN_USERNAME="$REPLY"

  echo "Пароль администратора (Enter — сгенерировать случайный):"
  echo "  Политика (production): минимум 8 символов, буквы и цифры; не используйте admin/admin."
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_ADMIN_PASSWORD="${WIZ_ADMIN_PASSWORD:-admin}"
    echo "  [используется значение по умолчанию]"
  else
    read -r -s -p "Пароль (пусто = случайный): " _admin_pw
    echo
    if [[ -z "$_admin_pw" ]]; then
      WIZ_ADMIN_PASSWORD="$(random_hex | cut -c1-16)"
      echo "  Сгенерирован пароль: $WIZ_ADMIN_PASSWORD"
    else
      read -r -s -p "Подтвердите пароль: " _admin_pw2
      echo
      if [[ "$_admin_pw" != "$_admin_pw2" ]]; then
        die "Пароли не совпадают."
      fi
      WIZ_ADMIN_PASSWORD="$_admin_pw"
    fi
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

  wiz_step "7. Node agent"
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    echo "  Порт node agent: ${WIZ_NODE_AGENT_PORT} (задан на шаге 3)"
  fi

  wiz_prompt_yesno "Сгенерировать NODE_AGENT_API_KEY автоматически?" "y"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_NODE_AGENT_API_KEY="$(random_hex)"
    echo "  Будет сгенерирован ключ (покажем в конце установки)."
  else
    wiz_prompt_secret "Введите NODE_AGENT_API_KEY (мин. 24 символа в production)" ""
    if [[ -z "$REPLY" ]]; then
      die "NODE_AGENT_API_KEY обязателен для node agent."
    fi
    WIZ_NODE_AGENT_API_KEY="$REPLY"
  fi

  echo "  Ограничьте доступ к порту ${WIZ_NODE_AGENT_PORT} firewall: только IP панели управления."
  wiz_prompt "Разрешённые IP панели (NODE_AGENT_ALLOWED_IPS, CIDR через запятую, пусто = без ограничения)" ""
  WIZ_NODE_AGENT_ALLOWED_IPS="$REPLY"
  echo
}

wizard_ask_security_hardening() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    wiz_prompt_yesno "Включить mTLS для node agent (требует scripts/generate-mtls-certs.sh)?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_NODE_AGENT_MTLS_ENABLED="true"
      echo "  После установки: sudo ./scripts/generate-mtls-certs.sh"
    fi
    echo
    return 0
  fi

  if [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    if [[ "$WIZ_UVICORN_WORKERS" -gt 1 ]]; then
      wizard_show_redis_rate_limit_hint
      wiz_prompt_yesno "Настроить Redis для rate limit auth (AUTH_RATE_LIMIT_BACKEND=redis)?" "y"
      if [[ "$REPLY" == "y" ]]; then
        WIZ_AUTH_RATE_LIMIT_BACKEND="redis"
        wiz_prompt "REDIS_URL" "redis://127.0.0.1:6379/0"
        WIZ_REDIS_URL="$REPLY"
      fi
    fi
    echo
    return 0
  fi

  wiz_step "7a. Дополнительная безопасность"
  if [[ "$WIZ_UVICORN_WORKERS" -gt 1 ]]; then
    wizard_show_redis_rate_limit_hint
    wiz_prompt_yesno "Настроить Redis для rate limit auth (AUTH_RATE_LIMIT_BACKEND=redis)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_AUTH_RATE_LIMIT_BACKEND="redis"
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

  echo "  Рекомендуется закрыть внутренние порты с интернета и открыть только Nginx."
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
      echo "  ufw/iptables не найдены — после установки будут показаны команды вручную."
    fi
  else
    WIZ_CONFIGURE_FIREWALL="false"
    echo "  Настройте firewall вручную (см. SECURITY.md)."
  fi
  echo
}

wizard_ask_services() {
  local step_num="8"
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    step_num="4"
  fi
  wiz_step "${step_num}. Сервисы и автозапуск"
  wiz_prompt_choice "Как запускать после установки?" \
    "Вручную (./start.sh / ./start_node_agent.sh)" \
    "Daemon через start.sh (watchdog)" \
    "Systemd (рекомендуется для production)"

  case "$REPLY" in
    1) WIZ_RUN_MODE="manual" ;;
    2) WIZ_RUN_MODE="daemon" ;;
    3) WIZ_RUN_MODE="systemd" ;;
  esac

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    local workers_default="$WIZ_UVICORN_WORKERS"
    if [[ "$WIZ_RUN_MODE" == "systemd" && "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
      workers_default="1"
    fi
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
  echo
}

wizard_ask_optional() {
  local step_num="9"
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    step_num="4"
  elif [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    step_num="7"
  fi

  wiz_step "${step_num}. Опциональные функции"

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
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

    wiz_prompt_yesno "Включить сбор трафика (TRAFFIC_SYNC_ENABLED)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_TRAFFIC_SYNC_ENABLED="true"
    else
      WIZ_TRAFFIC_SYNC_ENABLED="false"
    fi

    wiz_prompt_yesno "Настроить Telegram-уведомления?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_TELEGRAM_ENABLED="true"
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
  local step_num="10"
  local default_state="$ROOT_DIR/.runtime"
  local default_node_state="$ROOT_DIR/.runtime/node"

  if [[ "$WIZ_RUN_MODE" == "systemd" ]]; then
    default_state="/var/lib/adminpanelaz"
    default_node_state="/var/lib/adminpanelaz-node"
  fi

  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    step_num="5"
  elif [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    step_num="8"
  fi

  wiz_step "${step_num}. Пути"
  wiz_prompt "Каталог состояния controller" "${WIZ_STATE_DIR:-$default_state}"
  WIZ_STATE_DIR="$REPLY"

  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    wiz_prompt "Каталог состояния node agent" "${WIZ_NODE_STATE_DIR:-$default_node_state}"
    WIZ_NODE_STATE_DIR="$REPLY"
  fi

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    wiz_prompt "Каталог бэкапов (BACKUP_ROOT)" "$WIZ_BACKUP_ROOT"
    WIZ_BACKUP_ROOT="$REPLY"
  fi
  echo
}

wizard_apply_run_mode_flags() {
  WITH_DAEMON=false
  WITH_SYSTEMD=false
  WITH_NODE_AGENT=false

  case "$WIZ_RUN_MODE" in
    daemon) WITH_DAEMON=true ;;
    systemd) WITH_SYSTEMD=true ;;
  esac

  case "$WIZ_INSTALL_TYPE" in
    controller_node|node) WITH_NODE_AGENT=true ;;
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

  wiz_title "Сводка конфигурации"

  local install_label="$WIZ_INSTALL_TYPE"
  case "$WIZ_INSTALL_TYPE" in
    controller)
      if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
        install_label="панель + локальный AntiZapret"
      else
        install_label="только панель"
      fi
      ;;
    controller_node) install_label="полный стек" ;;
    node) install_label="только node agent" ;;
  esac

  echo "  Тип установки:     $install_label"
  echo "  AntiZapret:        $WIZ_ANTIZAPRET_PATH"
  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    echo "  Доступ:            ${WIZ_SERVER_ADDRESS:-—}"
    if [[ "$WIZ_DDNS_PROVIDER" != "none" ]]; then
      echo "  DDNS:              $WIZ_DDNS_PROVIDER ($(wizard_ddns_fqdn))"
      echo "  DDNS auto-update:  $WIZ_DDNS_CONFIGURE_UPDATE"
    fi
    echo "  Backend:           ${WIZ_BACKEND_HOST}:${WIZ_BACKEND_PORT} (localhost only)"
    echo "  APP_ENV:           $WIZ_APP_ENV"
    echo "  CORS:              $WIZ_CORS_ORIGINS"
    echo "  Internal nodes:    $WIZ_ALLOW_INTERNAL_NODES"
    echo "  Nginx/HTTPS:       $WIZ_NGINX_MODE"
    echo "  BEHIND_NGINX:      $WIZ_BEHIND_NGINX"
    if [[ "$WIZ_NGINX_MODE" != "none" && -n "$WIZ_NGINX_DOMAIN" ]]; then
      echo "  Домен:             $WIZ_NGINX_DOMAIN"
      if [[ "$WIZ_NGINX_MODE" == "le" || "$WIZ_NGINX_MODE" == "selfsigned" ]]; then
        echo "  Публичные порты:   HTTPS ${WIZ_HTTPS_PUBLIC_PORT}, HTTP ${WIZ_HTTP_ACME_PORT}"
      fi
    fi
    echo "  Uvicorn workers:   $WIZ_UVICORN_WORKERS"
    if [[ "$WIZ_UVICORN_WORKERS" -gt 1 ]]; then
      echo "  Rate limit:        ${WIZ_AUTH_RATE_LIMIT_BACKEND}${WIZ_REDIS_URL:+, REDIS_URL=$WIZ_REDIS_URL}"
    fi
    echo "  Администратор:     $WIZ_ADMIN_USERNAME"
    echo "  Смена пароля:      $WIZ_ADMIN_MUST_CHANGE_PASSWORD"
    echo "  Политика паролей:  $WIZ_ENFORCE_PASSWORD_POLICY"
    echo "  BACKUP_ROOT:       $WIZ_BACKUP_ROOT"
    echo "  CIDR refresh:      $WIZ_CIDR_DB_REFRESH_ENABLED"
    echo "  Traffic sync:      $WIZ_TRAFFIC_SYNC_ENABLED"
    echo "  Telegram:          $WIZ_TELEGRAM_ENABLED"
    echo "  Auto-backup:       $WIZ_AUTO_BACKUP_ENABLED"
  fi
  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    echo "  Node agent port:   $WIZ_NODE_AGENT_PORT"
    echo "  Node API key:      ${WIZ_NODE_AGENT_API_KEY:0:8}..."
    echo "  Node allowed IPs:  ${WIZ_NODE_AGENT_ALLOWED_IPS:-(без ограничения)}"
    echo "  Node state dir:    $WIZ_NODE_STATE_DIR"
  fi
  echo "  State dir:         $WIZ_STATE_DIR"
  echo "  Режим запуска:     $WIZ_RUN_MODE"
  echo "  Firewall auto:     $WIZ_CONFIGURE_FIREWALL"
  if [[ "$WIZ_INSTALL_TYPE" != "node" && "$WIZ_APP_ENV" == "production" && "$WIZ_NGINX_MODE" == "none" ]]; then
    echo
    echo "  ВНИМАНИЕ: APP_ENV=production без HTTPS — для интернета настройте Nginx (шаг 5 или ./scripts/nginx-setup.sh)."
  fi
  echo
}

wizard_confirm_apply() {
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_APPLY_CONFIRMED=true
    return 0
  fi

  wiz_prompt_yesno "Применить конфигурацию?" "n"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_APPLY_CONFIRMED=true
  else
    WIZ_APPLY_CONFIRMED=false
    echo "Установка отменена."
    exit 0
  fi
}

run_install_wizard() {
  wiz_title "AdminPanelAZ — мастер установки"
  echo "Ответьте на вопросы ниже. Enter — значение по умолчанию в [скобках]."
  echo

  wizard_ask_install_type
  wizard_ask_antizapret
  wizard_ask_network
  wizard_ask_ddns
  wizard_ask_app_env
  wizard_ask_https
  wizard_ask_admin
  wizard_ask_node_agent
  wizard_ask_services
  wizard_ask_security_hardening
  wizard_ask_optional
  wizard_ask_paths
  wizard_ask_firewall
  wizard_show_summary
  wizard_confirm_apply
  wizard_apply_run_mode_flags
}

wizard_install_controller() {
  case "$WIZ_INSTALL_TYPE" in
    controller|controller_node) return 0 ;;
    *) return 1 ;;
  esac
}

wizard_install_node() {
  case "$WIZ_INSTALL_TYPE" in
    controller_node|node) return 0 ;;
    *) return 1 ;;
  esac
}
