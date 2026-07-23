#!/usr/bin/env bash
# Общий выбор Python для backend/.venv (install.sh, start.sh, start_node_agent.sh).
# Не запускать напрямую — только source.
#
# Панель рассчитана на Python 3.12 (CI, SQLAlchemy pin). Системный python3 на новых
# дистрибутивах может быть 3.13/3.14 — его нельзя подставлять в venv без явной проверки.

ADMINPANELAZ_PYTHON_MAJOR="${ADMINPANELAZ_PYTHON_MAJOR:-3}"
ADMINPANELAZ_PYTHON_MINOR="${ADMINPANELAZ_PYTHON_MINOR:-12}"
ADMINPANELAZ_PYTHON_VERSION="${ADMINPANELAZ_PYTHON_MAJOR}.${ADMINPANELAZ_PYTHON_MINOR}"

_ap_python_die() {
  if declare -F die >/dev/null 2>&1; then
    die "$@"
  fi
  echo "[python] ОШИБКА: $*" >&2
  exit 1
}

_ap_python_log() {
  if declare -F log >/dev/null 2>&1; then
    log "$@"
    return
  fi
  echo "[python] $*"
}

_ap_python_warn() {
  if declare -F warn >/dev/null 2>&1; then
    warn "$@"
    return
  fi
  echo "[python] ВНИМАНИЕ: $*" >&2
}

# Версия интерпретатора: "3.12.3" или пусто при ошибке.
ap_python_report_version() {
  local bin="${1:-}"
  [[ -n "$bin" && -x "$bin" ]] || return 1
  "$bin" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null
}

# true, если major.minor совпадает с требуемой веткой (3.12.x).
ap_python_version_matches() {
  local ver="${1:-}"
  [[ "$ver" == "${ADMINPANELAZ_PYTHON_VERSION}."* ]] || [[ "$ver" == "$ADMINPANELAZ_PYTHON_VERSION" ]]
}

# Путь к python3.12 (или совместимому python3 == 3.12.x). Печатает путь в stdout.
ap_resolve_python() {
  local candidates=()
  local override="${ADMINPANELAZ_PYTHON_BIN:-}"
  local bin ver

  if [[ -n "$override" ]]; then
    candidates+=("$override")
  fi
  candidates+=("python${ADMINPANELAZ_PYTHON_VERSION}")
  # Явный /usr/bin чаще надёжнее PATH после apt install
  candidates+=("/usr/bin/python${ADMINPANELAZ_PYTHON_VERSION}")

  for bin in "${candidates[@]}"; do
    if command -v "$bin" >/dev/null 2>&1; then
      bin="$(command -v "$bin")"
    elif [[ ! -x "$bin" ]]; then
      continue
    fi
    ver="$(ap_python_report_version "$bin" || true)"
    if ap_python_version_matches "$ver"; then
      printf '%s\n' "$bin"
      return 0
    fi
  done

  # Системный python3 — только если это ровно требуемая ветка
  if command -v python3 >/dev/null 2>&1; then
    bin="$(command -v python3)"
    ver="$(ap_python_report_version "$bin" || true)"
    if ap_python_version_matches "$ver"; then
      printf '%s\n' "$bin"
      return 0
    fi
  fi
  return 1
}

ap_require_python() {
  local bin ver
  if ! bin="$(ap_resolve_python)"; then
    _ap_python_die \
      "Нужен Python ${ADMINPANELAZ_PYTHON_VERSION}.x (найден другой или отсутствует). Установите: apt-get install -y python${ADMINPANELAZ_PYTHON_VERSION} python${ADMINPANELAZ_PYTHON_VERSION}-venv python${ADMINPANELAZ_PYTHON_VERSION}-dev"
  fi
  ver="$(ap_python_report_version "$bin")"
  if ! ap_python_version_matches "$ver"; then
    _ap_python_die "Python ${ADMINPANELAZ_PYTHON_VERSION}.x обязателен, сейчас: $bin ($ver)"
  fi
  printf '%s\n' "$bin"
}

# Версия python внутри существующего venv (bin/python).
ap_venv_report_version() {
  local venv_dir="${1:-}"
  local py="${venv_dir}/bin/python"
  ap_python_report_version "$py"
}

# Создать venv на Python 3.12; пересоздать, если уже есть, но версия не та.
ap_ensure_venv() {
  local venv_dir="${1:-}"
  local py bin ver
  [[ -n "$venv_dir" ]] || _ap_python_die "ap_ensure_venv: не указан каталог venv"

  bin="$(ap_require_python)"

  if [[ -x "${venv_dir}/bin/python" ]]; then
    ver="$(ap_venv_report_version "$venv_dir" || true)"
    if ap_python_version_matches "$ver"; then
      _ap_python_log "venv OK: ${venv_dir} (Python ${ver})"
      return 0
    fi
    _ap_python_warn "venv на Python ${ver:-unknown} — пересоздаём под ${ADMINPANELAZ_PYTHON_VERSION} (${venv_dir})"
    rm -rf "$venv_dir"
  fi

  _ap_python_log "Создание venv: $venv_dir (интерпретатор $bin)"
  "$bin" -m venv "$venv_dir"
  py="${venv_dir}/bin/python"
  ver="$(ap_python_report_version "$py" || true)"
  if ! ap_python_version_matches "$ver"; then
    _ap_python_die "После создания venv ожидался Python ${ADMINPANELAZ_PYTHON_VERSION}.x, получено: ${ver:-unknown}"
  fi
}
