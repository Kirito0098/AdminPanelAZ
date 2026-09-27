#!/usr/bin/env bash
# Сервер по умолчанию nginx (00-adminpanelaz-default-deny) без перегенерации vhost панели:
# запросы по IP сервера и к чужим именам не доходят до панели и портала.
# Обновление через веб-интерфейс не запускает nginx-repair.sh — отсюда кнопка «Закрыть доступ по IP»
# в «Настройки → Проверка работы». .env, vhost панели и TRUSTED_PROXY_IPS не трогаются.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/nginx-default-deny.sh --check|--apply

Закрывает доступ к панели по IP сервера: nginx отклоняет запросы без домена панели или портала
(HTTP — закрывает соединение, HTTPS — отклоняет рукопожатие).

  --check   Одна строка JSON: status = installed | needed | outdated | own_default | not_applicable | disabled,
            ports — план по портам панели и портала. Ничего не меняет; код 0, если проверка прошла.
            disabled — NGINX_DEFAULT_DENY=0 в backend/.env: сервер по умолчанию не ставится,
            --apply убирает уже поставленный.
  --apply   Ставит или обновляет только сервер по умолчанию; при изменении — nginx -t и
            systemctl reload nginx (без restart). Выводит ту же строку с changed и error;
            ненулевой код, если nginx -t или reload не прошли. Если не прошёл nginx -t,
            прежний сервер по умолчанию возвращается; после неудачного reload новый файл
            остаётся (nginx -t он прошёл) и применится при следующем запуске nginx.
            Параллельные --apply ждут друг друга (flock, до 20 с).
  --help    Справка
EOF
}

require_root() {
  [[ "$(id -u)" -eq 0 ]] || nginx_die "Запустите от root: sudo $0"
}

# dd_ports_json <план> → JSON-массив портов
dd_ports_json() {
  local port kind action rest item out=""
  while read -r port kind action rest; do
    [[ -n "$port" ]] || continue
    if [[ "$kind" == ssl ]]; then kind=https; else kind=http; fi
    item="{\"port\":${port},\"kind\":\"${kind}\",\"action\":\"${action}\""
    [[ "$action" == skip ]] && item+=",\"reason\":\"${rest}\""
    out+="${out:+,}${item}}"
  done <<<"$1"
  printf '[%s]' "$out"
}

dd_is_installed() {
  local base
  base="$(nginx_default_deny_basename)"
  [[ -e "$(nginx_sites_enabled_dir)/${base}" && -f "$(nginx_sites_available_dir)/${base}" ]]
}

# dd_evaluate: DD_PLAN, DD_STATUS, DD_INSTALLED по текущим файлам nginx
# HTTPS-порты без сертификата-заглушки (nginx < 1.19.4) — «skip no_cert»: так же их пропустит установка.
dd_evaluate() {
  local plan_installs expected current version_output
  if ! nginx_default_deny_enabled; then
    DD_PLAN=""
    DD_INSTALLED=false
    dd_is_installed && DD_INSTALLED=true
    DD_STATUS=disabled
    return 0
  fi
  version_output="$(nginx -v 2>&1 || true)"
  DD_PLAN="$(nginx_default_deny_plan_cert_fallback "$(nginx_default_deny_plan)" "$version_output")"
  plan_installs="$(nginx_default_deny_plan_listens "$DD_PLAN" plain)$(nginx_default_deny_plan_listens "$DD_PLAN" ssl)"
  DD_INSTALLED=false
  dd_is_installed && DD_INSTALLED=true

  if [[ "$DD_INSTALLED" == true ]]; then
    DD_STATUS=outdated
    if [[ -n "$plan_installs" ]]; then
      expected="$(nginx_default_deny_expected_conf "$DD_PLAN" "$version_output")"
      current="$(cat "$(nginx_sites_available_dir)/$(nginx_default_deny_basename)")"
      if [[ "$current" == "$expected" ]]; then DD_STATUS=installed; fi
    fi
  elif [[ -n "$plan_installs" ]] || grep -q ' skip no_cert$' <<<"$DD_PLAN"; then
    DD_STATUS=needed
  elif [[ -n "$DD_PLAN" ]] && ! grep -qv ' skip existing_default_server$' <<<"$DD_PLAN"; then
    DD_STATUS=own_default
  else
    DD_STATUS=not_applicable
  fi
}

# dd_print [changed] [error]
dd_print() {
  local changed="${1:-}" error="${2:-}" line
  line="{\"status\":\"${DD_STATUS}\",\"installed\":${DD_INSTALLED}"
  [[ -n "$changed" ]] && line+=",\"changed\":${changed}"
  [[ -n "$error" ]] && line+=",\"error\":\"${error}\""
  line+=",\"ports\":$(dd_ports_json "$DD_PLAN")}"
  printf '%s\n' "$line"
}

# Снимок default-deny до --apply: есть ли файл и ссылка, содержимое — во временном файле
dd_snapshot() {
  local base avail enabled
  base="$(nginx_default_deny_basename)"
  avail="$(nginx_sites_available_dir)/${base}"
  enabled="$(nginx_sites_enabled_dir)/${base}"
  DD_SNAP_FILE="$(mktemp)"
  DD_SNAP_HAS_FILE=false
  DD_SNAP_HAS_LINK=false
  if [[ -f "$avail" ]]; then
    cp "$avail" "$DD_SNAP_FILE"
    DD_SNAP_HAS_FILE=true
  fi
  [[ -e "$enabled" || -L "$enabled" ]] && DD_SNAP_HAS_LINK=true
  return 0
}

dd_snapshot_matches() {
  local base avail enabled has_link=false
  base="$(nginx_default_deny_basename)"
  avail="$(nginx_sites_available_dir)/${base}"
  enabled="$(nginx_sites_enabled_dir)/${base}"
  [[ -e "$enabled" || -L "$enabled" ]] && has_link=true
  [[ "$has_link" == "$DD_SNAP_HAS_LINK" ]] || return 1
  if [[ "$DD_SNAP_HAS_FILE" == true ]]; then
    [[ -f "$avail" ]] && cmp -s "$avail" "$DD_SNAP_FILE"
  else
    [[ ! -f "$avail" ]]
  fi
}

dd_restore_snapshot() {
  local base avail enabled
  base="$(nginx_default_deny_basename)"
  avail="$(nginx_sites_available_dir)/${base}"
  enabled="$(nginx_sites_enabled_dir)/${base}"
  nginx_remove_default_deny
  [[ "$DD_SNAP_HAS_FILE" == true ]] && cp "$DD_SNAP_FILE" "$avail"
  [[ "$DD_SNAP_HAS_LINK" == true ]] && ln -sf "$avail" "$enabled"
  return 0
}

dd_lock() {
  local lock="${NGINX_DEFAULT_DENY_LOCK:-/run/adminpanelaz-nginx-default-deny.lock}"
  local wait="${NGINX_DEFAULT_DENY_LOCK_WAIT:-20}"
  exec 9>"$lock" || nginx_die "Не удалось открыть блокировку ${lock}"
  flock -w "$wait" 9 || nginx_die "Другой запуск nginx-default-deny.sh --apply не завершился за ${wait} с — повторите позже"
}

dd_apply() {
  local changed=false
  dd_lock
  dd_snapshot
  trap 'rm -f "$DD_SNAP_FILE"' EXIT
  nginx_install_default_deny
  dd_evaluate
  if [[ "$DD_STATUS" == needed || "$DD_STATUS" == outdated ]]; then
    dd_restore_snapshot
    dd_evaluate
    dd_print false install_failed
    return 1
  fi
  dd_snapshot_matches || changed=true
  if [[ "$changed" == true ]]; then
    # Установка уже прогнала nginx -t для нового файла, но удаление устаревшего default-deny
    # (портов панели не осталось или нет сертификата-заглушки) идёт без проверки.
    if ! nginx -t >/dev/null 2>&1; then
      nginx_warn "nginx -t не прошёл — сервер по умолчанию возвращён к прежнему виду"
      dd_restore_snapshot
      dd_evaluate
      dd_print false nginx_test_failed
      return 1
    fi
    if ! systemctl reload nginx; then
      nginx_warn "systemctl reload nginx не удался — конфигурация применится при следующем запуске nginx"
      dd_print true reload_failed
      return 1
    fi
    nginx_log "nginx перечитал конфигурацию (reload)"
  fi
  dd_print "$changed"
}

MODE="${1:-}"
case "$MODE" in
  --check|--apply) ;;
  --help|-h)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

require_root
command -v nginx >/dev/null 2>&1 || nginx_die "nginx не установлен"

if [[ "$MODE" == --check ]]; then
  dd_evaluate
  dd_print
else
  dd_apply
fi
