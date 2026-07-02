#!/usr/bin/env bash
# Простая установка AdminPanelAZ — для тех, кто не знаком с Linux и кодом.
#
# Запуск:
#   sudo bash install-easy.sh              # меню
#   sudo bash install-easy.sh --easy       # простой мастер установки
#   sudo bash install-easy.sh --uninstall  # удаление (с вопросами, как install.sh)
#   sudo bash install-easy.sh --uninstall -y   # удаление без вопросов (CI/скрипты)
#   sudo bash install-easy.sh --purge-all      # удалить всё без следов
#   sudo bash install-easy.sh --purge-all -y   # полное удаление без вопросов
#
# Или: wget -qO /tmp/install-easy.sh URL && sudo bash /tmp/install-easy.sh
set -euo pipefail

DEFAULT_INSTALL_GIT="https://github.com/Kirito0098/AdminPanelAZ.git"
DEFAULT_INSTALL_TARGET="/opt/AdminPanelAZ"

_script_path="${BASH_SOURCE[0]:-}"
if [[ -n "$_script_path" && "$_script_path" != bash && "$_script_path" != -bash ]]; then
  _script_dir="$(cd "$(dirname "$_script_path")" && pwd)"
else
  _script_dir=""
fi

bootstrap_remote_install() {
  if [[ -n "$_script_dir" \
    && -f "$_script_dir/scripts/install-easy-wizard.sh" \
    && -f "$_script_dir/install.sh" \
    && -f "$_script_dir/scripts/install-ui.sh" \
    && -f "$_script_dir/backend/requirements.txt" ]]; then
    return 0
  fi

  local git_url="${INSTALL_FROM_GIT:-$DEFAULT_INSTALL_GIT}"
  local target="${INSTALL_TARGET:-$DEFAULT_INSTALL_TARGET}"

  echo "[install-easy] Загрузка AdminPanelAZ из $git_url в $target ..."

  if ! command -v git >/dev/null 2>&1; then
    if [[ "$(id -u)" -eq 0 ]] && command -v apt-get >/dev/null 2>&1; then
      echo "[install-easy] git не найден — установка через apt..."
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y git
    fi
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "[install-easy] ОШИБКА: git не найден. Установите: apt install -y git" >&2
    exit 1
  fi

  if [[ "$(id -u)" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      echo "[install-easy] Перезапуск с sudo..."
      exec sudo -E env INSTALL_FROM_GIT="$git_url" INSTALL_TARGET="$target" bash -s "$@" <<'BOOTSTRAP'
set -euo pipefail
git_url="${INSTALL_FROM_GIT}"
target="${INSTALL_TARGET}"
mkdir -p "$(dirname "$target")"
if [[ -d "$target/.git" ]]; then
  git -C "$target" pull --ff-only || true
elif [[ -d "$target" ]]; then
  echo "[install-easy] ОШИБКА: $target существует, но это не git-репозиторий" >&2
  exit 1
else
  git clone "$git_url" "$target"
fi
exec bash "$target/install-easy.sh" "$@"
BOOTSTRAP
    fi
    echo "[install-easy] ОШИБКА: нужны права root (sudo)." >&2
    exit 1
  fi

  mkdir -p "$(dirname "$target")"
  if [[ -d "$target/.git" ]]; then
    echo "[install-easy] Обновление репозитория (git pull)..."
    git -C "$target" pull --ff-only || echo "[install-easy] ВНИМАНИЕ: git pull не удался" >&2
  elif [[ -d "$target" ]]; then
    echo "[install-easy] ОШИБКА: $target существует, но это не git-репозиторий" >&2
    exit 1
  else
    git clone "$git_url" "$target"
  fi

  exec bash "$target/install-easy.sh" "$@"
}

easy_delegates_to_install_sh() {
  for arg in "$@"; do
    case "$arg" in
      --uninstall|--purge-all|--purge|--reinstall)
        return 0
        ;;
    esac
  done
  return 1
}

show_easy_menu() {
  local choice=""
  # shellcheck source=scripts/install-ui.sh
  source "$ROOT_DIR/scripts/install-ui.sh"
  ui_init

  while true; do
    ui_show_banner
    ui_box_top "Простая установка — выберите действие"
    ui_box_line "  1) Установить панель (простой мастер)"
    ui_box_line "  2) Удалить панель (с подтверждениями)"
    ui_box_line "  3) Удалить панель без вопросов (для скриптов)"
    ui_box_line "  4) Удалить всё без следов"
    ui_box_line "  5) Полный установщик (для опытных пользователей)"
    ui_box_line "  6) Справка"
    ui_box_bottom
    read -r -p "Выберите пункт [1]: " choice
    choice="${choice:-1}"
    case "$choice" in
      1) return 0 ;;
      2)
        # install.sh → пункт «Удаление»
        exec bash "$ROOT_DIR/install.sh" --uninstall
        ;;
      3)
        # install.sh --uninstall -y (дефолты: state, nginx, firewall)
        exec bash "$ROOT_DIR/install.sh" --uninstall -y
        ;;
      4)
        # install.sh → пункт «Удалить всё без следов»
        exec bash "$ROOT_DIR/install.sh" --purge-all
        ;;
      5)
        exec bash "$ROOT_DIR/install.sh" "$@"
        ;;
      6)
        cat <<'EOF'

Простая установка AdminPanelAZ
==============================
Запускайте из SSH-терминала на сервере (Ubuntu 24.04 / Debian 13+):

  sudo bash install-easy.sh

Или скачайте с GitHub:

  wget -qO /tmp/install-easy.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install-easy.sh
  sudo bash /tmp/install-easy.sh

Мастер задаст несколько простых вопросов с пояснениями.

Удаление (те же сценарии, что в sudo ./install.sh):
  sudo bash install-easy.sh --uninstall       # с вопросами
  sudo bash install-easy.sh --uninstall -y    # без вопросов (CI/скрипты)
  sudo bash install-easy.sh --purge-all       # всё без следов
  sudo bash install-easy.sh --purge-all -y    # полное удаление без вопросов

Для расширенных настроек используйте: sudo ./install.sh

EOF
        read -r -p "Нажмите Enter..." _
        ;;
      *)
        echo "Неизвестный пункт: $choice"
        ;;
    esac
  done
}

main() {
  bootstrap_remote_install "$@"

  ROOT_DIR="${_script_dir:-$(pwd)}"

  if [[ "$(id -u)" -ne 0 ]]; then
    echo "[install-easy] ОШИБКА: запустите от root: sudo $0" >&2
    exit 1
  fi

  # Удаление / переустановка — делегируем в install.sh (в т.ч. без TTY для -y / CI)
  if easy_delegates_to_install_sh "$@"; then
    exec bash "$ROOT_DIR/install.sh" "$@"
  fi

  if [[ ! -t 0 ]]; then
    cat >&2 <<'EOF'
[install-easy] ОШИБКА: нужен интерактивный терминал (SSH).
Не используйте curl | bash — скачайте файл и запустите:

  wget -qO /tmp/install-easy.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install-easy.sh
  sudo bash /tmp/install-easy.sh
EOF
    exit 1
  fi

  local original_argc=$#
  if [[ "$original_argc" -eq 0 ]]; then
    show_easy_menu "$@"
  fi

  exec bash "$ROOT_DIR/install.sh" --easy "$@"
}

main "$@"
