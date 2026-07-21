#!/usr/bin/env bash
# Проверка занятости портов для install.sh / install-wizard / install-easy-wizard.
# Не запускать напрямую — source из установщика.
#
# Ожидает (опционально): ROOT_DIR, print_warn/print_error/print_info/print_success,
# die, ui_warn_box, WIZ_* переменные мастера.

# port_is_listening <port> [bind_hint]
# bind_hint: any|0.0.0.0|127.0.0.1 (по умолчанию any)
# Возвращает 0 если порт слушается (с учётом bind_hint).
port_is_listening() {
  local port="$1"
  local bind_hint="${2:-any}"
  local line addr

  [[ "$port" =~ ^[0-9]+$ ]] || return 1

  if ! command -v ss >/dev/null 2>&1; then
    # Без ss не можем проверить — считаем свободным (не блокируем установку).
    return 1
  fi

  while IFS= read -r line; do
    # Примеры: 0.0.0.0:8000  127.0.0.1:8000  *:8000  [::]:8000  [::1]:8000
    addr="$(printf '%s\n' "$line" | awk '{print $4}')"
    [[ -n "$addr" ]] || continue
    case "$addr" in
      *":${port}") ;;
      *":${port}]") ;; # IPv6 [::]:port уже покрыт *:${port}
      *) continue ;;
    esac

    case "$bind_hint" in
      127.0.0.1|localhost)
        case "$addr" in
          127.0.0.1:"${port}"|\[::1\]:"${port}"|localhost:"${port}")
            return 0
            ;;
          0.0.0.0:"${port}"|\*:"${port}"|\[::\]:"${port}"|"[::]:${port}")
            # 0.0.0.0 также занимает localhost
            return 0
            ;;
        esac
        ;;
      0.0.0.0|any|"")
        return 0
        ;;
      *)
        # Конкретный IP: совпадение или wildcard
        case "$addr" in
          "${bind_hint}:${port}"|0.0.0.0:"${port}"|\*:"${port}"|\[::\]:"${port}")
            return 0
            ;;
        esac
        ;;
    esac
  done < <(ss -tlnH 2>/dev/null || ss -tln 2>/dev/null | tail -n +2 || true)

  return 1
}

# PID слушателя на порту (первый найденный). Пусто если не найден.
port_listener_pid() {
  local port="$1"
  local pid=""

  if command -v ss >/dev/null 2>&1; then
    # ss -tlnp: users:(("nginx",pid=123,fd=8))
    pid="$(ss -tlnp 2>/dev/null | awk -v p=":${port}" '
      $4 ~ p"$" || $4 ~ p"]$" {
        if (match($0, /pid=[0-9]+/)) {
          s = substr($0, RSTART+4, RLENGTH-4)
          print s
          exit
        }
      }
    ')"
  fi

  if [[ -z "$pid" ]] && command -v fuser >/dev/null 2>&1; then
    pid="$(fuser "${port}/tcp" 2>/dev/null | awk '{print $1; exit}' | tr -d '[:space:]')"
  fi

  printf '%s' "$pid"
}

# Краткое описание слушателя: "pid=123 nginx (unit: nginx.service)" или "неизвестно"
port_listener_info() {
  local port="$1"
  local pid comm unit cmdline=""
  pid="$(port_listener_pid "$port")"

  if [[ -z "$pid" || ! -d "/proc/$pid" ]]; then
    # Есть LISTEN, но PID не определили (нужен root / нет -p)
    if port_is_listening "$port"; then
      printf 'порт слушается (процесс не определён — запустите от root или проверьте: ss -tlnp | grep :%s)' "$port"
    else
      printf 'неизвестно'
    fi
    return 0
  fi

  comm="$(cat "/proc/$pid/comm" 2>/dev/null || echo "?")"
  if [[ -r "/proc/$pid/cmdline" ]]; then
    cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | sed 's/[[:space:]]*$//')"
  fi

  unit=""
  if command -v systemctl >/dev/null 2>&1; then
    unit="$(systemctl status "$pid" 2>/dev/null | awk '/Loaded:/{getline; print}' | head -1 || true)"
    # Более надёжно: cgroup
    if [[ -z "$unit" || "$unit" == *"not-found"* ]]; then
      unit="$(systemctl status "$pid" 2>/dev/null | head -1 | sed -E 's/^●[[:space:]]+//;s/\.service.*/.service/' || true)"
    fi
    # Попробовать через cgroup
    if [[ -r "/proc/$pid/cgroup" ]]; then
      local cg
      cg="$(grep -oE 'system.slice/[^/]+\.service' "/proc/$pid/cgroup" 2>/dev/null | head -1 | sed 's|system.slice/||' || true)"
      [[ -n "$cg" ]] && unit="$cg"
    fi
  fi

  local info="pid=${pid} ${comm}"
  if [[ -n "$unit" && "$unit" == *.service ]]; then
    info="${info} (unit: ${unit})"
  elif [[ -n "$cmdline" ]]; then
    # Укоротить cmdline
    if (( ${#cmdline} > 80 )); then
      cmdline="${cmdline:0:77}..."
    fi
    info="${info} (${cmdline})"
  fi
  printf '%s' "$info"
}

# Порт занят нашим сервисом AdminPanelAZ?
port_is_ours() {
  local port="$1"
  local pid comm cmdline unit="" root="${ROOT_DIR:-}"

  pid="$(port_listener_pid "$port")"
  if [[ -z "$pid" || ! -d "/proc/$pid" ]]; then
    # Не смогли определить PID — не считаем «нашим» (осторожнее)
    return 1
  fi

  comm="$(cat "/proc/$pid/comm" 2>/dev/null || true)"
  cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"

  if [[ -r "/proc/$pid/cgroup" ]]; then
    unit="$(grep -oE 'system.slice/[^/]+\.service' "/proc/$pid/cgroup" 2>/dev/null | head -1 | sed 's|system.slice/||' || true)"
  fi

  case "$unit" in
    adminpanelaz.service|adminpanelaz-node.service)
      return 0
      ;;
  esac

  # uvicorn / node_agent из каталога проекта
  if [[ -n "$root" ]]; then
    case "$cmdline" in
      *"${root}"*)
        case "$cmdline" in
          *uvicorn*|*node_agent*|*start.sh*|*start_node_agent*)
            return 0
            ;;
        esac
        ;;
    esac
  fi

  case "$comm" in
    uvicorn)
      [[ -n "$root" && "$cmdline" == *"$root"* ]] && return 0
      ;;
  esac

  # nginx с конфигом панели
  if [[ "$comm" == "nginx" ]] || [[ "$cmdline" == *nginx* ]]; then
    if [[ -f /etc/nginx/sites-enabled/adminpanelaz ]] \
      || [[ -f /etc/nginx/conf.d/adminpanelaz.conf ]] \
      || ls /etc/nginx/sites-enabled/adminpanelaz* >/dev/null 2>&1 \
      || ls /etc/nginx/conf.d/adminpanelaz* >/dev/null 2>&1; then
      # Проверим, что именно этот порт в конфиге панели (грубо)
      if grep -RqsE "listen[[:space:]]+${port}\\b|listen[[:space:]]+\\[::\\]:${port}\\b" \
        /etc/nginx/sites-enabled/adminpanelaz* /etc/nginx/conf.d/adminpanelaz* 2>/dev/null; then
        return 0
      fi
      # Если nginx слушает стандартные 80/443 и есть сайт панели — считаем нашим для preflight reinstall
      if [[ "$port" == "80" || "$port" == "443" ]]; then
        if [[ -f /etc/nginx/sites-enabled/adminpanelaz ]] \
          || [[ -f /etc/nginx/conf.d/adminpanelaz.conf ]] \
          || ls /etc/nginx/sites-enabled/adminpanelaz* >/dev/null 2>&1; then
          return 0
        fi
      fi
    fi
  fi

  return 1
}

# port_check_available <port> <role_label> [bind_hint] [quiet]
# 0 = свободен или наш; 1 = занят чужим.
# quiet=1 — не печатать warn (вызывающий покажет свой блок).
port_check_available() {
  local port="$1"
  local role="${2:-порт}"
  local bind_hint="${3:-any}"
  local quiet="${4:-0}"
  local info

  if ! port_is_listening "$port" "$bind_hint"; then
    return 0
  fi

  if port_is_ours "$port"; then
    if [[ "$quiet" != "1" ]] && declare -F print_info >/dev/null 2>&1; then
      print_info "${role}: порт ${port} занят сервисом AdminPanelAZ — OK (повторная установка)."
    fi
    return 0
  fi

  info="$(port_listener_info "$port")"
  if [[ "$quiet" != "1" ]]; then
    if declare -F print_warn >/dev/null 2>&1; then
      print_warn "${role}: порт ${port} уже занят — ${info}"
    else
      echo "[port-check] ВНИМАНИЕ: ${role}: порт ${port} уже занят — ${info}" >&2
    fi
  fi
  return 1
}

# Интерактивно потребовать свободный порт; пишет выбранный порт в REPLY.
# port_prompt_until_available <prompt> <default> <role_label> [bind_hint] [forbidden...]
# Использует wiz_prompt_port если доступен.
port_prompt_until_available() {
  local prompt="$1"
  local default="$2"
  local role="${3:-порт}"
  local bind_hint="${4:-any}"
  shift 4 || true
  local -a forbidden=("$@")
  local port f

  while true; do
    if declare -F wiz_prompt_port >/dev/null 2>&1; then
      # Без вложенной проверки занятости — только число
      wiz_prompt "$prompt" "$default"
      if [[ ! "$REPLY" =~ ^[0-9]+$ ]] || (( REPLY < 1 || REPLY > 65535 )); then
        echo "Введите число от 1 до 65535."
        continue
      fi
    else
      local reply=""
      read -r -p "$prompt [$default]: " reply
      REPLY="${reply:-$default}"
      if [[ ! "$REPLY" =~ ^[0-9]+$ ]] || (( REPLY < 1 || REPLY > 65535 )); then
        echo "Введите число от 1 до 65535."
        continue
      fi
    fi
    port="$REPLY"

    for f in "${forbidden[@]}"; do
      if [[ -n "$f" && "$port" == "$f" ]]; then
        echo "Порт ${port} уже используется другим сервисом установки. Выберите другой."
        continue 2
      fi
    done

    if port_check_available "$port" "$role" "$bind_hint" 1; then
      REPLY="$port"
      return 0
    fi

    # Занят чужим
    if [[ "${WIZ_ACCEPT_DEFAULTS:-false}" == true ]] \
      || [[ "${ACCEPT_DEFAULTS:-false}" == true ]] \
      || [[ "${NON_INTERACTIVE:-false}" == true ]]; then
      if declare -F die >/dev/null 2>&1; then
        die "${role}: порт ${port} занят ($(port_listener_info "$port")). Укажите свободный порт или остановите конфликтующий сервис."
      fi
      echo "ОШИБКА: ${role}: порт ${port} занят." >&2
      exit 1
    fi

    if declare -F ui_warn_box >/dev/null 2>&1; then
      ui_warn_box "Порт ${port} занят (${role})" \
        "$(port_listener_info "$port")" \
        "Выберите другой порт или остановите конфликтующий сервис и повторите."
    else
      echo "Порт ${port} занят (${role}): $(port_listener_info "$port")"
      echo "Выберите другой порт."
    fi
    default="$port"
  done
}

# Заполняет массив INSTALL_REQUIRED_PORTS элементами "port|role|bind_hint"
install_collect_required_ports() {
  INSTALL_REQUIRED_PORTS=()
  local install_type="${WIZ_INSTALL_TYPE:-controller}"
  local mode="${WIZ_NGINX_MODE:-none}"
  local backend_port="${WIZ_BACKEND_PORT:-${BACKEND_PORT:-8000}}"
  local backend_host="${WIZ_BACKEND_HOST:-${BACKEND_HOST:-127.0.0.1}}"
  local node_port="${WIZ_NODE_AGENT_PORT:-${NODE_AGENT_PORT:-9100}}"
  local https_port="${WIZ_HTTPS_PUBLIC_PORT:-443}"
  local http_port="${WIZ_HTTP_ACME_PORT:-80}"
  local bind_hint="any"

  case "$install_type" in
    node)
      INSTALL_REQUIRED_PORTS+=("${node_port}|Связь с панелью (node agent)|any")
      return 0
      ;;
  esac

  # Controller
  case "$backend_host" in
    127.0.0.1|localhost)
      bind_hint="127.0.0.1"
      ;;
    *)
      bind_hint="any"
      ;;
  esac

  case "$mode" in
    uvicorn_*|http_direct)
      INSTALL_REQUIRED_PORTS+=("${backend_port}|Панель (публичный порт)|any")
      ;;
    le|selfsigned|nginx_custom)
      INSTALL_REQUIRED_PORTS+=("${backend_port}|Панель (localhost)|127.0.0.1")
      INSTALL_REQUIRED_PORTS+=("${https_port}|HTTPS (nginx)|any")
      INSTALL_REQUIRED_PORTS+=("${http_port}|HTTP / Let's Encrypt (nginx)|any")
      ;;
    none|"")
      INSTALL_REQUIRED_PORTS+=("${backend_port}|Панель (localhost)|${bind_hint}")
      ;;
    *)
      INSTALL_REQUIRED_PORTS+=("${backend_port}|Панель|${bind_hint}")
      ;;
  esac
}

# Preflight: проверить все нужные порты. При занятых чужих — die (или return 1 если PORT_PREFLIGHT_SOFT=true).
install_preflight_ports() {
  local soft="${PORT_PREFLIGHT_SOFT:-false}"
  local entry port role bind_hint
  local -a conflicts=()
  local -a conflict_details=()

  install_collect_required_ports

  if [[ ${#INSTALL_REQUIRED_PORTS[@]} -eq 0 ]]; then
    return 0
  fi

  if declare -F print_info >/dev/null 2>&1; then
    print_info "Проверка доступности портов..."
  fi

  local rest
  for entry in "${INSTALL_REQUIRED_PORTS[@]}"; do
    port="${entry%%|*}"
    rest="${entry#*|}"
    role="${rest%%|*}"
    bind_hint="${rest#*|}"
    [[ "$bind_hint" == "$rest" ]] && bind_hint="any"

    if ! port_is_listening "$port" "$bind_hint"; then
      if declare -F print_success >/dev/null 2>&1; then
        print_success "${role}: порт ${port} свободен"
      fi
      continue
    fi

    if port_is_ours "$port"; then
      if declare -F print_info >/dev/null 2>&1; then
        print_info "${role}: порт ${port} — AdminPanelAZ (OK)"
      fi
      continue
    fi

    # Easy-мастер: пользователь уже подтвердил продолжение при занятых 80/443
    if [[ "${WIZ_ALLOW_BUSY_PUBLIC_PORTS:-false}" == true ]]; then
      case "$port" in
        80|443)
          if declare -F print_warn >/dev/null 2>&1; then
            print_warn "${role}: порт ${port} занят — продолжаем по подтверждению пользователя"
          fi
          continue
          ;;
      esac
    fi

    conflicts+=("$port")
    conflict_details+=("${role}: порт ${port} — $(port_listener_info "$port")")
  done

  if [[ ${#conflicts[@]} -eq 0 ]]; then
    return 0
  fi

  if declare -F ui_warn_box >/dev/null 2>&1; then
    local ports_re
    ports_re="$(IFS='|'; echo "${conflicts[*]}")"
    ui_warn_box "Занятые порты — установка не может продолжаться" \
      "${conflict_details[@]}" \
      "" \
      "Остановите конфликтующий сервис или выберите другие порты в мастере." \
      "Проверка: ss -tlnp | grep -E ':(${ports_re})'"
  else
    echo "[port-check] ОШИБКА: занятые порты:" >&2
    local d
    for d in "${conflict_details[@]}"; do
      echo "  - $d" >&2
    done
  fi

  if [[ "$soft" == true ]]; then
    return 1
  fi

  # Детали уже в ui_warn_box — короткий финал без второго большого блока
  if declare -F print_error >/dev/null 2>&1; then
    print_error "Установка остановлена: заняты порты ${conflicts[*]}."
    if declare -F print_info >/dev/null 2>&1; then
      print_info "Освободите порты или выберите другие в мастере, затем: sudo ./install.sh"
    fi
  else
    echo "[port-check] ОШИБКА: заняты порты ${conflicts[*]}." >&2
  fi
  INSTALL_FATAL_HANDLED=true
  exit 1
}
