#!/usr/bin/env bash
# Чтение и запись KEY=value в .env-файлах. Одна семантика для install.sh, nginx, firewall,
# меню, health-check и агентов:
#   * читается ПОСЛЕДНЕЕ присваивание ключа — так же, как .env разбирает панель (pydantic-settings);
#   * снимается завершающий \r и одна пара кавычек, пробелы внутри значения сохраняются;
#   * запись переписывает все существующие строки ключа и добавляет строку, если ключа нет.
# Подключать: source "<каталог скрипта>/env-file.sh".

env_file_has() {
  local file="$1" key="$2"
  [[ -n "$file" && -f "$file" ]] || return 1
  grep -qE "^${key}=" "$file" 2>/dev/null
}

env_file_get() {
  local file="$1" key="$2" line val
  [[ -n "$file" && -f "$file" ]] || return 0
  line="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -1 || true)"
  [[ -n "$line" ]] || return 0
  val="${line#*=}"
  val="${val%$'\r'}"
  if [[ ${#val} -ge 2 && ( "$val" == \"*\" || "$val" == \'*\' ) ]]; then
    val="${val:1:${#val}-2}"
  fi
  printf '%s' "$val"
}

env_file_set() {
  local file="$1" key="$2" value="$3" escaped
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "env-file: ${key}: перевод строки в значении недопустим" >&2
    return 1
  fi
  mkdir -p "$(dirname "$file")"
  [ -f "$file" ] || : >"$file"
  escaped=$(printf '%s' "$value" | sed -e 's/[\\&|]/\\&/g')
  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

env_file_unset() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 0
  sed -i "/^${key}=/d" "$file"
}
