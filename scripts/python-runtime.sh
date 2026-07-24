#!/usr/bin/env bash
# Общий выбор Python для backend/.venv (install.sh, start.sh, start_node_agent.sh).
# Не запускать напрямую — только source.
#
# Предпочтение: Python 3.13 (Debian 13 / CI). Запасной вариант: 3.12 (Ubuntu 24.04,
# где python3.13 нет в apt). Системный python3 3.14+ не подставляется без проверки.
#
# Переопределение:
#   ADMINPANELAZ_PYTHON_MINOR=13|12   — только эта ветка (без fallback)
#   ADMINPANELAZ_PYTHON_BIN=/path     — явный интерпретатор

ADMINPANELAZ_PYTHON_MAJOR="${ADMINPANELAZ_PYTHON_MAJOR:-3}"
# Пустой MINOR = авто: сначала 3.13, затем 3.12. Явный MINOR отключает fallback.
_AP_PYTHON_MINOR_PINNED=0
if [[ -n "${ADMINPANELAZ_PYTHON_MINOR+x}" && -n "${ADMINPANELAZ_PYTHON_MINOR}" ]]; then
  _AP_PYTHON_MINOR_PINNED=1
else
  ADMINPANELAZ_PYTHON_MINOR="${ADMINPANELAZ_PYTHON_MINOR:-13}"
fi
ADMINPANELAZ_PYTHON_VERSION="${ADMINPANELAZ_PYTHON_MAJOR}.${ADMINPANELAZ_PYTHON_MINOR}"
# Кандидаты major.minor по приоритету (для apt и поиска бинарника).
ADMINPANELAZ_PYTHON_FALLBACK_MINOR="${ADMINPANELAZ_PYTHON_FALLBACK_MINOR:-12}"

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

# Список веток "3.13" "3.12" …
ap_python_candidate_versions() {
  local versions=()
  versions+=("${ADMINPANELAZ_PYTHON_MAJOR}.${ADMINPANELAZ_PYTHON_MINOR}")
  if [[ "$_AP_PYTHON_MINOR_PINNED" -eq 0 \
    && -n "${ADMINPANELAZ_PYTHON_FALLBACK_MINOR}" \
    && "${ADMINPANELAZ_PYTHON_FALLBACK_MINOR}" != "${ADMINPANELAZ_PYTHON_MINOR}" ]]; then
    versions+=("${ADMINPANELAZ_PYTHON_MAJOR}.${ADMINPANELAZ_PYTHON_FALLBACK_MINOR}")
  fi
  printf '%s\n' "${versions[@]}"
}

# Версия интерпретатора: "3.13.5" или пусто при ошибке.
ap_python_report_version() {
  local bin="${1:-}"
  [[ -n "$bin" && -x "$bin" ]] || return 1
  "$bin" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null
}

# major.minor из полной версии ("3.13.5" → "3.13").
ap_python_mm() {
  local ver="${1:-}"
  [[ "$ver" =~ ^([0-9]+\.[0-9]+) ]] && printf '%s\n' "${BASH_REMATCH[1]}"
}

# true, если major.minor совпадает с целевой веткой ($2 или ADMINPANELAZ_PYTHON_VERSION).
ap_python_version_matches() {
  local ver="${1:-}"
  local want="${2:-$ADMINPANELAZ_PYTHON_VERSION}"
  [[ "$ver" == "${want}."* ]] || [[ "$ver" == "$want" ]]
}

# true, если версия входит в список кандидатов (3.13 или 3.12).
ap_python_version_allowed() {
  local ver="${1:-}"
  local mm cand
  mm="$(ap_python_mm "$ver" || true)"
  [[ -n "$mm" ]] || return 1
  while IFS= read -r cand; do
    [[ "$mm" == "$cand" ]] && return 0
  done < <(ap_python_candidate_versions)
  return 1
}

# Зафиксировать выбранную ветку (после resolve / apt).
ap_python_set_active_version() {
  local mm="${1:-}"
  [[ -n "$mm" ]] || return 1
  ADMINPANELAZ_PYTHON_VERSION="$mm"
  ADMINPANELAZ_PYTHON_MAJOR="${mm%%.*}"
  ADMINPANELAZ_PYTHON_MINOR="${mm#*.}"
}

# Путь к python3.13 / python3.12 (или совместимому python3). Печатает путь в stdout.
ap_resolve_python() {
  local candidates=()
  local override="${ADMINPANELAZ_PYTHON_BIN:-}"
  local bin ver mm cand
  local tried=()

  if [[ -n "$override" ]]; then
    candidates+=("$override")
  fi

  while IFS= read -r cand; do
    candidates+=("python${cand}" "/usr/bin/python${cand}")
  done < <(ap_python_candidate_versions)

  for bin in "${candidates[@]}"; do
    [[ " ${tried[*]} " == *" $bin "* ]] && continue
    tried+=("$bin")
    if command -v "$bin" >/dev/null 2>&1; then
      bin="$(command -v "$bin")"
    elif [[ ! -x "$bin" ]]; then
      continue
    fi
    ver="$(ap_python_report_version "$bin" || true)"
    if ap_python_version_allowed "$ver"; then
      mm="$(ap_python_mm "$ver")"
      ap_python_set_active_version "$mm"
      printf '%s\n' "$bin"
      return 0
    fi
  done

  # Системный python3 — только если ветка из списка кандидатов
  if command -v python3 >/dev/null 2>&1; then
    bin="$(command -v python3)"
    ver="$(ap_python_report_version "$bin" || true)"
    if ap_python_version_allowed "$ver"; then
      mm="$(ap_python_mm "$ver")"
      ap_python_set_active_version "$mm"
      printf '%s\n' "$bin"
      return 0
    fi
  fi
  return 1
}

ap_require_python() {
  local bin ver want
  want="$(ap_python_candidate_versions | paste -sd '/' -)"
  if ! bin="$(ap_resolve_python)"; then
    _ap_python_die \
      "Нужен Python ${want}.x. Установите: apt-get install -y python${ADMINPANELAZ_PYTHON_MAJOR}.${ADMINPANELAZ_PYTHON_MINOR}{,-venv,-dev} (на Ubuntu 24.04 — python3.12) или задайте ADMINPANELAZ_PYTHON_BIN"
  fi
  ver="$(ap_python_report_version "$bin")"
  if ! ap_python_version_allowed "$ver"; then
    _ap_python_die "Python ${want}.x обязателен, сейчас: $bin ($ver)"
  fi
  printf '%s\n' "$bin"
}

# Версия python внутри существующего venv (bin/python).
ap_venv_report_version() {
  local venv_dir="${1:-}"
  local py="${venv_dir}/bin/python"
  ap_python_report_version "$py"
}

# Пакеты apt для одной ветки: python3.13 python3.13-venv python3.13-dev
ap_python_apt_packages_for() {
  local mm="${1:-}"
  printf 'python%s python%s-venv python%s-dev\n' "$mm" "$mm" "$mm"
}

# Установить python через apt: сначала 3.13, при отсутствии пакетов — 3.12.
# Возвращает 0 и печатает выбранный mm в stdout при успехе.
ap_apt_install_python() {
  local cand pkgs
  while IFS= read -r cand; do
    if ! apt-cache show "python${cand}" >/dev/null 2>&1; then
      _ap_python_warn "Пакет python${cand} отсутствует в apt — пробуем следующую ветку"
      continue
    fi
    pkgs="$(ap_python_apt_packages_for "$cand")"
    # shellcheck disable=SC2086
    if apt-get install -y $pkgs; then
      ap_python_set_active_version "$cand"
      printf '%s\n' "$cand"
      return 0
    fi
    _ap_python_warn "Пакеты Python ${cand} не установились — пробуем следующую ветку"
  done < <(ap_python_candidate_versions)
  return 1
}

# Создать venv на выбранном Python; пересоздать, если версия не из кандидатов
# или не совпадает с фактически выбранным интерпретатором.
ap_ensure_venv() {
  local venv_dir="${1:-}"
  local py bin ver mm
  [[ -n "$venv_dir" ]] || _ap_python_die "ap_ensure_venv: не указан каталог venv"

  bin="$(ap_require_python)"
  mm="$ADMINPANELAZ_PYTHON_VERSION"

  if [[ -x "${venv_dir}/bin/python" ]]; then
    ver="$(ap_venv_report_version "$venv_dir" || true)"
    if ap_python_version_matches "$ver" "$mm"; then
      _ap_python_log "venv OK: ${venv_dir} (Python ${ver})"
      return 0
    fi
    _ap_python_warn "venv на Python ${ver:-unknown} — пересоздаём под ${mm} (${venv_dir})"
    rm -rf "$venv_dir"
  fi

  _ap_python_log "Создание venv: $venv_dir (интерпретатор $bin)"
  "$bin" -m venv "$venv_dir"
  py="${venv_dir}/bin/python"
  ver="$(ap_python_report_version "$py" || true)"
  if ! ap_python_version_matches "$ver" "$mm"; then
    _ap_python_die "После создания venv ожидался Python ${mm}.x, получено: ${ver:-unknown}"
  fi
}
