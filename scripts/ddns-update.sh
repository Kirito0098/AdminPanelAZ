#!/usr/bin/env bash
# Обновление динамического DNS (DuckDNS, No-IP) для AdminPanelAZ
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${DDNS_CONFIG:-/etc/adminpanelaz/ddns.env}"
SERVICE_NAME="adminpanelaz-ddns"
TIMER_NAME="${SERVICE_NAME}.timer"
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"

log() {
  echo "[ddns] $*"
}


die() {
  echo "[ddns] ОШИБКА: $*" >&2
  exit 1
}

# Значение для конфигурации curl (-K) в кавычках. Перевод строки начал бы новую опцию curl — отказ.
curl_config_value() {
  local value="$1"
  [[ "$value" != *[$'\r\n']* ]] || return 1
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/ddns-update.sh [команда]

Команды:
  update          Обновить IP у провайдера DDNS (по умолчанию)
  install-timer   Установить systemd timer для периодического обновления
  remove-timer    Удалить systemd timer
  status          Показать конфигурацию и статус timer
  --help          Справка

Конфигурация: /etc/adminpanelaz/ddns.env
  Создаётся в панели (Настройки → Адрес сайта и HTTPS → Динамический DNS)
  или через env-override установщика (WIZ_DDNS_PROVIDER=…).

Переменные в ddns.env:
  DDNS_PROVIDER=duckdns|noip
  DDNS_DOMAIN=полное.имя.домена
  DDNS_TOKEN=...           # DuckDNS
  DDNS_SUBDOMAIN=...       # DuckDNS (без .duckdns.org)
  DDNS_USERNAME=...        # No-IP
  DDNS_PASSWORD=...        # No-IP
  DDNS_HOSTNAME=...        # No-IP (полное имя хоста)
EOF
}

load_config() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    die "Файл конфигурации не найден: $CONFIG_FILE (настройте в панели или через WIZ_DDNS_*)"
  fi
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  DDNS_PROVIDER="${DDNS_PROVIDER:-none}"
}

detect_public_ip() {
  local ip=""
  for url in \
    "https://api.ipify.org" \
    "https://ifconfig.me/ip" \
    "https://icanhazip.com"; do
    ip="$(curl -fsS --max-time 10 "$url" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "$ip"
      return 0
    fi
  done
  return 1
}

update_duckdns() {
  local subdomain="${DDNS_SUBDOMAIN:-}"
  local token="${DDNS_TOKEN:-}"

  [[ -n "$subdomain" && -n "$token" ]] || die "DuckDNS: задайте DDNS_SUBDOMAIN и DDNS_TOKEN в $CONFIG_FILE"

  local url_opt response
  url_opt="$(curl_config_value "https://www.duckdns.org/update?domains=${subdomain}&token=${token}&ip=")" \
    || die "DuckDNS: DDNS_SUBDOMAIN и DDNS_TOKEN не должны содержать перевод строки ($CONFIG_FILE)"
  response="$(printf 'url = %s\n' "$url_opt" | curl -fsS --max-time 15 -K - 2>/dev/null || echo "KO")"
  response="$(echo "$response" | tr -d '[:space:]')"

  case "$response" in
    OK)
      log "DuckDNS: ${subdomain}.duckdns.org обновлён"
      return 0
      ;;
    KO)
      die "DuckDNS вернул KO — проверьте token и subdomain"
      ;;
    *)
      die "DuckDNS: неожиданный ответ: $response"
      ;;
  esac
}

update_noip() {
  local hostname="${DDNS_HOSTNAME:-${DDNS_DOMAIN:-}}"
  local username="${DDNS_USERNAME:-}"
  local password="${DDNS_PASSWORD:-}"

  [[ -n "$hostname" && -n "$username" && -n "$password" ]] || \
    die "No-IP: задайте DDNS_HOSTNAME, DDNS_USERNAME и DDNS_PASSWORD в $CONFIG_FILE"

  local url_opt user_opt response
  url_opt="$(curl_config_value "https://dynupdate.no-ip.com/nic/update?hostname=${hostname}")" \
    && user_opt="$(curl_config_value "${username}:${password}")" \
    || die "No-IP: DDNS_HOSTNAME, DDNS_USERNAME и DDNS_PASSWORD не должны содержать перевод строки ($CONFIG_FILE)"
  response="$(printf 'url = %s\nuser = %s\n' "$url_opt" "$user_opt" | curl -fsS --max-time 15 -K - 2>/dev/null || echo "911")"
  local first_line status
  IFS= read -r first_line <<<"$response"
  first_line="${first_line%$'\r'}"
  read -r status _ <<<"$first_line"

  case "$status" in
    good|nochg)
      log "No-IP: $hostname обновлён ($first_line)"
      return 0
      ;;
    badauth)
      die "No-IP: неверный логин или пароль (badauth)"
      ;;
    !donator)
      die "No-IP: для этого хоста нужен платный аккаунт (!donator)"
      ;;
    notfqdn)
      die "No-IP: неверное имя хоста (notfqdn)"
      ;;
    *)
      die "No-IP: неожиданный ответ: $first_line"
      ;;
  esac
}

run_update() {
  load_config

  case "$DDNS_PROVIDER" in
    none|"")
      die "DDNS_PROVIDER не задан"
      ;;
    duckdns)
      update_duckdns
      ;;
    noip)
      update_noip
      ;;
    *)
      die "Неизвестный DDNS_PROVIDER: $DDNS_PROVIDER"
      ;;
  esac

  if [[ -n "${DDNS_DOMAIN:-}" ]]; then
    local ip=""
    ip="$(detect_public_ip 2>/dev/null || true)"
    if [[ -n "$ip" ]]; then
      log "Публичный IP: $ip → ${DDNS_DOMAIN}"
    fi
  fi
}

install_timer() {
  if [[ "$(id -u)" -ne 0 ]]; then
    die "install-timer требует root: sudo $0 install-timer"
  fi

  local service_src="$ROOT_DIR/systemd/${SERVICE_NAME}.service"
  local timer_src="$ROOT_DIR/systemd/${TIMER_NAME}"
  [[ -f "$service_src" && -f "$timer_src" ]] || die "Не найдены unit-файлы в $ROOT_DIR/systemd/"

  sed "s|/opt/AdminPanelAZ|$ROOT_DIR|g" "$service_src" >"$UNIT_DIR/${SERVICE_NAME}.service"
  cp "$timer_src" "$UNIT_DIR/${TIMER_NAME}"

  systemctl daemon-reload
  systemctl enable --now "$TIMER_NAME"
  log "Systemd timer установлен: $TIMER_NAME (каждые 5 минут)"
}

remove_timer() {
  if [[ "$(id -u)" -ne 0 ]]; then
    die "remove-timer требует root"
  fi

  systemctl stop "$TIMER_NAME" 2>/dev/null || true
  systemctl disable "$TIMER_NAME" 2>/dev/null || true
  rm -f "$UNIT_DIR/${SERVICE_NAME}.service" "$UNIT_DIR/${TIMER_NAME}"
  systemctl daemon-reload
  log "Systemd timer удалён"
}

show_status() {
  if [[ -f "$CONFIG_FILE" ]]; then
    echo "Конфигурация: $CONFIG_FILE"
    local provider domain
    provider="$(grep -E '^DDNS_PROVIDER=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- || true)"
    domain="$(grep -E '^DDNS_DOMAIN=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- || true)"
    echo "  Провайдер: ${provider:-—}"
    echo "  Домен:     ${domain:-—}"
  else
    echo "Конфигурация: не найдена ($CONFIG_FILE)"
  fi

  if systemctl is-enabled "$TIMER_NAME" >/dev/null 2>&1; then
    echo "Timer: активен ($TIMER_NAME)"
    systemctl status "$TIMER_NAME" --no-pager 2>/dev/null | head -5 || true
  else
    echo "Timer: не установлен"
  fi
}

main() {
  case "${1:-update}" in
    update)
      run_update
      ;;
    install-timer)
      install_timer
      ;;
    remove-timer)
      remove_timer
      ;;
    status)
      show_status
      ;;
    --help|-h|help)
      usage
      ;;
    *)
      usage
      die "Неизвестная команда: $1"
      ;;
  esac
}

main "$@"
