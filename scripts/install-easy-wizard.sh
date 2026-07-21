#!/usr/bin/env bash
# Простой мастер установки для начинающих (вызывается из install-easy.sh / install.sh --easy)
set -euo pipefail

if [[ "${UI_INITIALIZED:-false}" != true ]]; then
  # shellcheck source=scripts/install-ui.sh
  source "$ROOT_DIR/scripts/install-ui.sh"
  ui_init
fi

# Общие переменные и хелперы wiz_* — из полного мастера
# shellcheck source=scripts/install-wizard.sh
source "$ROOT_DIR/scripts/install-wizard.sh"

EASY_CURRENT_STEP=0
EASY_TOTAL_STEPS=4

easy_step() {
  local title="$1"
  (( ++EASY_CURRENT_STEP )) || true
  ui_step_header "$EASY_CURRENT_STEP" "$EASY_TOTAL_STEPS" "$title"
}

easy_pause() {
  echo
  read -r -p "Нажмите Enter, чтобы продолжить..." _
  echo
}

easy_ask_choice() {
  wiz_prompt_choice "$@"
}

easy_show_welcome() {
  ui_show_banner
  ui_box_top "Простая установка AdminPanelAZ"
  ui_box_line "Пошаговый мастер для тех, кто не знаком с Linux и кодом."
  ui_box_line "Отвечайте на вопросы — остальное сделает установщик."
  ui_box_bottom
  echo
  ui_info_box "Что будет установлено" \
    "Программа «панель управления» — сайт в браузере для настройки VPN." \
    "Сама VPN-программа AntiZapret ставится отдельно (если ещё не стоит)." \
    "Установка займёт несколько минут. Нужен интернет на сервере."
  easy_pause
}

easy_ask_what_to_install() {
  ui_box_top "Что устанавливаем?"
  ui_box_bottom
  echo
  ui_info_box "Подсказка" \
    "«Панель» — сайт, где вы управляете VPN и клиентами." \
    "«VPN на этом же сервере» — если AntiZapret уже установлен в /root/antizapret." \
    "«Связь с панелью» — ставится на другом сервере, где работает VPN."
  echo
  easy_ask_choice "Выберите ваш случай:" \
    "Только панель (VPN на других серверах или пока без VPN)" \
    "Панель и VPN на этом же сервере (AntiZapret уже установлен)" \
    "Только связь с панелью (отдельный VPN-сервер, панель уже есть на другом)"

  case "$REPLY" in
    1)
      WIZ_INSTALL_TYPE="controller"
      WIZ_REQUIRE_ANTIZAPRET=false
      EASY_TOTAL_STEPS=4
      ;;
    2)
      WIZ_INSTALL_TYPE="controller"
      WIZ_REQUIRE_ANTIZAPRET=true
      EASY_TOTAL_STEPS=4
      ;;
    3)
      WIZ_INSTALL_TYPE="node"
      WIZ_REQUIRE_ANTIZAPRET=true
      EASY_TOTAL_STEPS=2
      ;;
  esac
  echo
}

easy_ask_access() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  easy_step "Как открывать панель в браузере?"
  ui_info_box "Зачем это нужно" \
    "Чтобы зайти в панель, нужен адрес — как сайт в интернете." \
    "Свой домен — если уже есть (например vpn.mydomain.ru)." \
    "Бесплатный адрес — DuckDNS, регистрация за 2 минуты на duckdns.org." \
    "Только на этом сервере — для проверки, без доступа из интернета."
  echo
  easy_ask_choice "Как вы будете заходить в панель?" \
    "Из интернета — у меня есть свой домен" \
    "Из интернета — нет домена, хочу бесплатный адрес (DuckDNS)" \
    "Только на этом сервере (без домена и без интернета)"

  case "$REPLY" in
    1)
      WIZ_DDNS_PROVIDER="none"
      WIZ_APP_ENV="production"
      WIZ_ENFORCE_PASSWORD_POLICY="true"
      echo
      wiz_prompt "Введите ваш домен (без https://, например vpn.example.com)" ""
      WIZ_NGINX_DOMAIN="$REPLY"
      WIZ_SERVER_ADDRESS="$REPLY"
      WIZ_NGINX_MODE="le"
      WIZ_BACKEND_HOST="127.0.0.1"
      WIZ_BEHIND_NGINX="true"
      echo
      print_info "Будет настроен защищённый вход (HTTPS) через Let's Encrypt."
      print_info "На сервере должны быть открыты порты 80 и 443."
      wiz_prompt "Email для уведомлений Let's Encrypt (можно оставить пустым)" ""
      WIZ_NGINX_EMAIL="$REPLY"
      ;;
    2)
      WIZ_APP_ENV="production"
      WIZ_ENFORCE_PASSWORD_POLICY="true"
      WIZ_DDNS_PROVIDER="duckdns"
      WIZ_NGINX_MODE="le"
      WIZ_BACKEND_HOST="127.0.0.1"
      WIZ_BEHIND_NGINX="true"
      echo
      ui_info_box "DuckDNS — бесплатный адрес" \
        "1. Откройте https://www.duckdns.org и войдите (Google/GitHub)." \
        "2. Создайте поддомен, например: myvpn → myvpn.duckdns.org" \
        "3. Скопируйте token со страницы домена."
      echo
      wiz_prompt "Имя поддомена (только myvpn, без .duckdns.org)" ""
      WIZ_DDNS_SUBDOMAIN="${REPLY,,}"
      WIZ_DDNS_SUBDOMAIN="${WIZ_DDNS_SUBDOMAIN%.duckdns.org}"
      wiz_prompt_secret "Token с сайта DuckDNS" "" ""
      WIZ_DDNS_TOKEN="$REPLY"
      WIZ_NGINX_DOMAIN="${WIZ_DDNS_SUBDOMAIN}.duckdns.org"
      WIZ_SERVER_ADDRESS="$WIZ_NGINX_DOMAIN"
      WIZ_DDNS_CONFIGURE_UPDATE="true"
      echo
      print_info "Адрес панели: https://${WIZ_NGINX_DOMAIN}/"
      print_info "IP будет обновляться автоматически. Нужны открытые порты 80 и 443."
      wiz_prompt "Email для Let's Encrypt (можно пусто)" ""
      WIZ_NGINX_EMAIL="$REPLY"
      ;;
    3)
      WIZ_DDNS_PROVIDER="none"
      WIZ_APP_ENV="development"
      WIZ_ENFORCE_PASSWORD_POLICY="false"
      WIZ_NGINX_MODE="none"
      WIZ_BACKEND_HOST="127.0.0.1"
      WIZ_BEHIND_NGINX="false"
      WIZ_SERVER_ADDRESS="127.0.0.1"
      echo
      print_info "Панель будет доступна только на этом сервере:"
      print_info "  http://127.0.0.1:${WIZ_BACKEND_PORT}/"
      print_info "Для доступа из интернета позже запустите: sudo ./scripts/nginx-setup.sh"
      ;;
  esac

  WIZ_BACKEND_PORT="8000"
  wizard_derive_cors_origins "$WIZ_BACKEND_PORT"
  if [[ "$WIZ_NGINX_MODE" == "le" && -n "$WIZ_NGINX_DOMAIN" ]]; then
    wizard_ask_access_path_and_status
    wizard_build_nginx_cors_origins "$WIZ_NGINX_DOMAIN" "$WIZ_HTTPS_PUBLIC_PORT" "$WIZ_BACKEND_PORT"
  else
    WIZ_ACCESS_PATH=""
    WIZ_NGINX_SUBPATH_INTEGRATE="false"
  fi

  # Проверка занятости портов (backend / 80 / 443)
  echo
  if ! port_check_available "$WIZ_BACKEND_PORT" "Внутренний порт панели" "127.0.0.1" 1; then
    ui_warn_box "Порт панели ${WIZ_BACKEND_PORT} занят" \
      "$(port_listener_info "$WIZ_BACKEND_PORT")" \
      "Можно выбрать другой внутренний порт."
    wiz_prompt_port "Другой порт панели (только localhost)" "8001" "Внутренний порт панели" "127.0.0.1"
    WIZ_BACKEND_PORT="$REPLY"
    wizard_derive_cors_origins "$WIZ_BACKEND_PORT"
    if [[ "$WIZ_NGINX_MODE" == "le" && -n "$WIZ_NGINX_DOMAIN" ]]; then
      wizard_build_nginx_cors_origins "$WIZ_NGINX_DOMAIN" "$WIZ_HTTPS_PUBLIC_PORT" "$WIZ_BACKEND_PORT"
    fi
  fi
  if [[ "$WIZ_NGINX_MODE" == "le" ]]; then
    local _easy_port_ok=true
    if ! port_check_available "80" "HTTP (Let's Encrypt)" "any" 1; then
      _easy_port_ok=false
      print_warn "Порт 80 занят — $(port_listener_info 80)"
    fi
    if ! port_check_available "443" "HTTPS" "any" 1; then
      _easy_port_ok=false
      print_warn "Порт 443 занят — $(port_listener_info 443)"
    fi
    if [[ "$_easy_port_ok" != true ]]; then
      ui_warn_box "Порты 80 и/или 443 заняты" \
        "Для HTTPS (Let's Encrypt) нужны свободные порты 80 и 443." \
        "Остановите конфликтующий сервис (nginx, apache, OpenVPN на 443)" \
        "или продолжите на свой риск — шаг nginx может завершиться ошибкой." \
        "Проверка: ss -tlnp | grep -E ':80|:443'"
      echo
      if ! ui_confirm "Продолжить несмотря на занятые порты?" "n"; then
        print_info "Установка отменена. Освободите порты 80/443 и запустите снова."
        exit 0
      fi
      WIZ_ALLOW_BUSY_PUBLIC_PORTS=true
    fi
  fi
  echo
}

easy_ask_admin() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  easy_step "Логин и пароль администратора"
  ui_info_box "Это ваш вход в панель" \
    "Логин — имя пользователя (можно оставить admin)." \
    "Пароль — придумайте надёжный или нажмите Enter — сгенерируем случайный." \
    "Запишите пароль — он понадобится при первом входе в браузере."
  echo
  wiz_prompt "Логин администратора" "$WIZ_ADMIN_USERNAME"
  WIZ_ADMIN_USERNAME="$REPLY"

  echo
  read -r -s -p "Пароль (Enter — сгенерировать автоматически): " _easy_pw
  echo
  if [[ -z "$_easy_pw" ]]; then
    if command -v openssl >/dev/null 2>&1; then
      WIZ_ADMIN_PASSWORD="$(openssl rand -hex 8)"
    else
      WIZ_ADMIN_PASSWORD="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-16)"
    fi
    print_success "Сгенерирован пароль: $WIZ_ADMIN_PASSWORD"
    print_info "Обязательно сохраните его в надёжном месте!"
  else
    read -r -s -p "Повторите пароль: " _easy_pw2
    echo
    if [[ "$_easy_pw" != "$_easy_pw2" ]]; then
      print_error "Пароли не совпадают. Запустите установку заново."
      exit 1
    fi
    WIZ_ADMIN_PASSWORD="$_easy_pw"
  fi
  WIZ_ADMIN_MUST_CHANGE_PASSWORD="true"
  echo
}

easy_ask_node_panel() {
  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    return 0
  fi

  easy_step "Подключение к панели"
  ui_info_box "Node agent — «мост» между панелью и VPN" \
    "Панель управления должна быть уже установлена на другом сервере." \
    "Укажите IP-адрес того сервера — доступ к порту агента ограничим только им."
  echo
  wiz_prompt "IP-адрес сервера с панелью (например 203.0.113.10)" ""
  WIZ_NODE_AGENT_ALLOWED_IPS="$REPLY"
  WIZ_NODE_AGENT_PORT="9100"
  if ! port_check_available "$WIZ_NODE_AGENT_PORT" "Связь с панелью" "any" 1; then
    ui_warn_box "Порт ${WIZ_NODE_AGENT_PORT} занят (связь с панелью)" \
      "$(port_listener_info "$WIZ_NODE_AGENT_PORT")" \
      "Выберите другой порт."
    wiz_prompt_port "Порт связи с панелью" "9101" "Связь с панелью" "any"
    WIZ_NODE_AGENT_PORT="$REPLY"
  fi
  WIZ_NODE_AGENT_API_KEY="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  echo
  print_info "Ключ связи с панелью будет показан в конце установки — сохраните его."
  echo
}

easy_ask_server_size() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  easy_step "Профиль ресурсов"
  ui_info_box "Оперативная память (RAM)" \
    "Замер стека Full (панель + VPN на сервере): ≈411 MB (358+53)." \
    "Средний стек за 7 дней: ~148 MB. Сторонние проекты на VDS не учитываются."
  echo
  easy_ask_choice "Сколько оперативной памяти (RAM) на этом сервере?" \
    "1 GB — профиль Minimal (только панель, VPN на других серверах)" \
    "1 GB и больше — Standard / Full (панель+VPN на одном VDS: ≈411 MB)"

  case "$REPLY" in
    1)
      WIZ_RESOURCE_PROFILE="minimal"
      WIZ_CIDR_DB_REFRESH_ENABLED="false"
      WIZ_TRAFFIC_SYNC_ENABLED="false"
      WIZ_UVICORN_WORKERS="1"
      if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
        print_warn "На 1 GB с VPN на том же сервере может не хватить памяти. Лучше 1 GB+ или отдельный сервер для панели."
      fi
      ;;
    *)
      if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
        WIZ_RESOURCE_PROFILE="full"
        WIZ_CIDR_DB_REFRESH_ENABLED="true"
        WIZ_TRAFFIC_SYNC_ENABLED="true"
      else
        WIZ_RESOURCE_PROFILE="standard"
        WIZ_CIDR_DB_REFRESH_ENABLED="false"
        WIZ_TRAFFIC_SYNC_ENABLED="true"
      fi
      WIZ_UVICORN_WORKERS="1"
      ;;
  esac
  echo
}

easy_ask_autostart_and_firewall() {
  local step_title="Автозапуск и защита"
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    step_title="Автозапуск"
  fi
  easy_step "$step_title"

  ui_info_box "Автозапуск" \
    "Рекомендуем включить — панель (или связь с панелью) будет" \
    "запускаться сама после перезагрузки сервера."
  WIZ_RUN_MODE="systemd"
  print_success "Автозапуск через systemd — включён (рекомендуется)."

  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    echo
    return 0
  fi

  echo
  if [[ "$WIZ_NGINX_MODE" == "le" ]]; then
    ui_info_box "Firewall (брандмауэр)" \
      "Закрывает лишние порты и открывает только нужные для сайта (80, 443)." \
      "Рекомендуется, если панель доступна из интернета."
    echo
    wiz_prompt_yesno "Настроить защиту портов (firewall) автоматически?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_CONFIGURE_FIREWALL="true"
      WIZ_FIREWALL_ENABLE_UFW="true"
    else
      WIZ_CONFIGURE_FIREWALL="false"
    fi
  else
    WIZ_CONFIGURE_FIREWALL="false"
    print_info "Firewall не настраиваем — панель только для локального доступа."
  fi
  echo
}

easy_apply_defaults() {
  WIZ_ANTIZAPRET_PATH="/root/antizapret"
  WIZ_STATE_DIR="/var/lib/adminpanelaz"
  WIZ_NODE_STATE_DIR="/var/lib/adminpanelaz-node"
  WIZ_BACKUP_ROOT="/var/backups/adminpanelaz"
  WIZ_ALLOW_INTERNAL_NODES="false"
  WIZ_HTTPS_PUBLIC_PORT="443"
  WIZ_HTTP_ACME_PORT="80"
  WIZ_AUTH_RATE_LIMIT_BACKEND="memory"
  WIZ_API_RATE_LIMIT_BACKEND="memory"
  WIZ_NODE_AGENT_MTLS_ENABLED="false"
  WIZ_TELEGRAM_ENABLED="false"
  WIZ_AUTO_BACKUP_ENABLED="false"
  WIZ_ALLOW_BUSY_PUBLIC_PORTS="${WIZ_ALLOW_BUSY_PUBLIC_PORTS:-false}"
}

easy_show_simple_summary() {
  easy_apply_defaults
  wizard_apply_run_mode_flags

  echo
  ui_box_top "Проверьте перед установкой"
  ui_box_bottom
  echo

  case "$WIZ_INSTALL_TYPE" in
    controller)
      if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]]; then
        ui_summary_row "Устанавливаем" "Панель + VPN на этом сервере"
      else
        ui_summary_row "Устанавливаем" "Только панель управления"
      fi
      if [[ "$WIZ_NGINX_MODE" == "le" && -n "${WIZ_NGINX_DOMAIN:-}" ]]; then
        ui_summary_row "Адрес в браузере" \
          "https://${WIZ_NGINX_DOMAIN}$(wizard_access_path_url_suffix)"
        if [[ -n "$(wizard_normalized_access_path)" ]]; then
          ui_summary_row "Подпуть" "$(wizard_normalized_access_path)"
        fi
        if [[ "${WIZ_NGINX_SUBPATH_INTEGRATE:-false}" == "true" ]]; then
          ui_summary_row "Интеграция nginx" "да"
        fi
      else
        ui_summary_row "Адрес в браузере" \
          "http://127.0.0.1:${WIZ_BACKEND_PORT}/"
      fi
      ui_summary_row "Логин" "$WIZ_ADMIN_USERNAME"
      ui_summary_row "Профиль ресурсов" "${WIZ_RESOURCE_PROFILE:-standard}"
      ui_summary_row "Автозапуск" "Да (после перезагрузки сервера)"
      ;;
    node)
      ui_summary_row "Устанавливаем" "Связь VPN-сервера с панелью"
      ui_summary_row "Порт" "$WIZ_NODE_AGENT_PORT"
      ui_summary_row "Доступ с IP панели" "${WIZ_NODE_AGENT_ALLOWED_IPS:-не ограничен}"
      ui_summary_row "Автозапуск" "Да"
      ;;
  esac
  echo
}

easy_confirm() {
  echo
  ui_separator
  if ui_confirm "Всё верно? Начать установку?" "y"; then
    WIZ_APPLY_CONFIRMED=true
    print_success "Отлично! Идёт установка — подождите несколько минут..."
  else
    WIZ_APPLY_CONFIRMED=false
    print_info "Установка отменена. Запустите снова: sudo ./install-easy.sh"
    exit 0
  fi
}

run_install_easy_wizard() {
  EASY_CURRENT_STEP=0
  easy_show_welcome
  easy_ask_what_to_install

  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    WIZ_ANTIZAPRET_PATH="/root/antizapret"
    if [[ ! -d "$WIZ_ANTIZAPRET_PATH" || ! -f "$WIZ_ANTIZAPRET_PATH/client.sh" ]]; then
      ui_warn_box "AntiZapret не найден на этом VPN-сервере" \
        "Ожидается: $WIZ_ANTIZAPRET_PATH" \
        "Сначала установите VPN: https://github.com/GubernievS/AntiZapret-VPN"
      echo
      if ! ui_confirm "Всё равно продолжить?" "n"; then
        exit 0
      fi
    else
      print_success "AntiZapret найден — всё в порядке."
    fi
    echo
  fi

  if [[ "$WIZ_REQUIRE_ANTIZAPRET" == true && "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    WIZ_ANTIZAPRET_PATH="/root/antizapret"
    if [[ ! -d "$WIZ_ANTIZAPRET_PATH" || ! -f "$WIZ_ANTIZAPRET_PATH/client.sh" ]]; then
      ui_warn_box "AntiZapret не найден" \
        "Ожидается каталог: $WIZ_ANTIZAPRET_PATH" \
        "Сначала установите VPN: https://github.com/GubernievS/AntiZapret-VPN" \
        "Или выберите «Только панель» при следующем запуске."
      echo
      if ! ui_confirm "Продолжить установку панели без VPN?" "n"; then
        exit 0
      fi
      WIZ_REQUIRE_ANTIZAPRET=false
    else
      print_success "AntiZapret найден — всё в порядке."
    fi
    echo
  fi

  easy_ask_access
  easy_ask_admin
  easy_ask_node_panel
  easy_ask_server_size
  easy_ask_autostart_and_firewall
  easy_apply_defaults
  easy_show_simple_summary
  echo
  install_preflight_ports
  easy_confirm
  wizard_apply_run_mode_flags
}
