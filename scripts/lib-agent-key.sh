#!/usr/bin/env bash
# Подключается install-node-systemd.sh и install-proxy-systemd.sh.
# API-ключ агента хранится только в env-файле с правами 600: unit-файлы и `systemctl show` читает любой пользователь.

# persist_agent_api_key <env-файл> <переменная> <значение>
# Записывает ключ, только если в файле его нет или стоит плейсхолдер: ключ в файле мог смениться ротацией.
persist_agent_api_key() {
  local file="$1" key="$2" value="$3" current tmp
  (umask 077 && : >>"$file")
  chmod 600 "$file"
  if [[ -z "$value" || "$value" == change-me* ]]; then
    return 0
  fi
  current="$(sed -n "s/^${key}=//p" "$file" | head -1)"
  if [[ -n "$current" && "$current" != change-me* ]]; then
    return 0
  fi
  tmp="$(mktemp "${file}.XXXXXX")"
  grep -v "^${key}=" "$file" >"$tmp" || true
  printf '%s=%s\n' "$key" "$value" >>"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$file"
}
