#!/usr/bin/env bash
# Подключается install-node-systemd.sh и install-proxy-systemd.sh.
# API-ключ агента хранится только в env-файле с правами 600: unit-файлы и `systemctl show` читает любой пользователь.

# Те же плейсхолдеры, что is_placeholder_secret в install.sh.
_agent_key_is_placeholder() {
  case "$1" in
    ""|change-me*|CHANGE-ME*|your-secret*|YOUR-SECRET*) return 0 ;;
  esac
  return 1
}

# persist_agent_api_key <env-файл> <переменная> <значение>
# Записывает ключ, только если в файле его нет или стоит плейсхолдер: ключ в файле мог смениться ротацией.
persist_agent_api_key() {
  local file="$1" key="$2" value="$3" current tmp rc
  file="$(readlink -f "$file")"
  (umask 077 && : >>"$file")
  chmod 600 "$file"
  if _agent_key_is_placeholder "$value"; then
    return 0
  fi
  current="$(sed -n "s/^${key}=//p" "$file" | head -1)"
  if ! _agent_key_is_placeholder "$current"; then
    return 0
  fi
  # Префикс .tmp_ есть в .gitignore: остаток после сбоя с ключом внутри не попадёт в git.
  tmp="$(mktemp "$(dirname "$file")/.tmp_$(basename "$file").XXXXXX")"
  rc=0
  grep -v "^${key}=" "$file" >"$tmp" || rc=$?
  if [[ "$rc" -gt 1 ]]; then
    rm -f "$tmp"
    echo "Не удалось прочитать $file" >&2
    return 1
  fi
  printf '%s=%s\n' "$key" "$value" >>"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$file"
}
