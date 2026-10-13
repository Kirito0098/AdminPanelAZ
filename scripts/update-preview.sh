#!/usr/bin/env bash
# Экран «что изменится» перед полным обновлением (full-update.sh --preview). Его показывает код НОВОЙ версии,
# распакованный во временную папку, против рабочего каталога INSTALL_DIR; ничего не записывает. Подключается из
# full-update.sh.

UP_NEW_ROOT="$(cd "$FU_DIR/.." && pwd)"
UP_NEWS_LIMIT=6
UP_BULLET="-"
case "${MENU_USER_LOCALE,,}" in
  *utf-8* | *utf8*) UP_BULLET="•" ;;
esac
UP_ADD=()
UP_CHANGE=()
UP_KEEP=()
UP_REMOVE=()
UP_EFFECT=()
UP_NGINX_COPY=false

up_join() {
  local joined
  printf -v joined '%s, ' "$@"
  printf '%s' "${joined%, }"
}

# Заголовки «- **…**» из CHANGELOG новой версии выше раздела текущей версии.
up_news() {
  local log="$UP_NEW_ROOT/CHANGELOG.md"
  grep -qF "## [$1]" "$log" 2>/dev/null || return 0
  awk -v stop="## [$1]" 'index($0, stop) == 1 { exit } /^- \*\*/ { sub(/^- \*\*/, ""); sub(/\*\*.*/, ""); print }' "$log"
}

up_header() {
  local rev="$1" current new count title shown=0
  local -a news=()
  if [[ -z "$rev" ]]; then
    printf '  %s\n' "Не удалось узнать новую версию (нет связи с GitHub) — обновление всё равно можно запустить"
    return 0
  fi
  current="$(menu_version "$INSTALL_DIR")"
  count="$(git -C "$INSTALL_DIR" rev-list --count "HEAD..$rev" 2>/dev/null || echo 0)"
  if [[ "$count" == 0 ]]; then
    printf '  Версия: %s — новее нет; код не изменится, настройки сервера проверятся заново\n' "${current:-неизвестно}"
    return 0
  fi
  new="$(menu_version "$UP_NEW_ROOT")"
  printf '  Версия: %s %s %s (изменений: %s)\n' "${current:-неизвестно}" "$FU_ARROW" "${new:-неизвестно}" "$count"
  UP_CHANGE+=("Код панели — новая версия")
  mapfile -t news < <(up_news "$current")
  ((${#news[@]} > 0)) || return 0
  printf '  Что нового:\n'
  for title in "${news[@]}"; do
    ((shown < UP_NEWS_LIMIT)) || break
    printf '    %s %s\n' "$UP_BULLET" "$title"
    shown=$((shown + 1))
  done
  if ((${#news[@]} > UP_NEWS_LIMIT)); then
    printf '    %s … и ещё %s — полный список: CHANGELOG.md\n' "$UP_BULLET" "$((${#news[@]} - UP_NEWS_LIMIT))"
  fi
}

up_command() {
  local link
  # shellcheck source=scripts/console-command.sh
  source "$UP_NEW_ROOT/scripts/console-command.sh"
  link="$(console_command_path)"
  if [[ -L "$link" && "$(readlink -f "$link")" == "$(readlink -f "$INSTALL_DIR/scripts/adminpanel-menu.sh")" ]]; then
    return 0
  fi
  if [[ -e "$link" && ! -L "$link" ]]; then
    UP_KEEP+=("Команда sudo adminpanelaz не добавится: $link занят другим файлом")
    return 0
  fi
  UP_ADD+=("Команда sudo adminpanelaz — меню можно будет открывать ею из любой папки")
}

up_apt() {
  local -a missing=()
  mapfile -t missing < <(fu_apt_missing)
  if ((${#missing[@]} > 0)); then
    UP_ADD+=("Пакеты системы: $(up_join "${missing[@]}")")
  fi
}

# «имя версия» для строк имя==версия; имя — в нижнем регистре, без [extras].
up_requirements() {
  sed -n 's/^\([A-Za-z0-9_.-]*\)\(\[[^]]*\]\)\{0,1\}==\([^[:space:];#]*\).*/\1 \3/p' "$1" 2>/dev/null \
    | awk '{ print tolower($1), $2 }'
}

# Убранные из списка библиотеки pip не удаляет — их не показываем.
up_pip() {
  local name old new
  local -A before=()
  local -a added=() changed=()
  while read -r name old; do
    before[$name]="$old"
  done < <(up_requirements "$INSTALL_DIR/backend/requirements.txt")
  while read -r name new; do
    old="${before[$name]-}"
    if [[ -z "$old" ]]; then
      added+=("$name $new")
    elif [[ "$old" != "$new" ]]; then
      changed+=("$name $old $FU_ARROW $new")
    fi
  done < <(up_requirements "$UP_NEW_ROOT/backend/requirements.txt")
  if ((${#added[@]} > 0)); then
    UP_ADD+=("Библиотеки Python: $(up_join "${added[@]}")")
  fi
  if ((${#changed[@]} > 0)); then
    UP_CHANGE+=("Библиотеки Python: $(up_join "${changed[@]}")")
  fi
}

up_nginx() {
  local kind host file conf
  panel_uses_systemd && fu_nginx_published || return 0
  while IFS=$'\t' read -r kind host file; do
    if ! conf="$(fu_nginx_render "$kind" "$host" "$file" 2>/dev/null)"; then
      UP_KEEP+=("Конфиг nginx для $host — новый не собрать, останется прежний")
    elif [[ "$conf" == "$(cat "$file")" ]]; then
      UP_KEEP+=("Конфиг nginx для $host — уже актуален")
    else
      UP_CHANGE+=("Конфиг nginx для $host устарел — обновится")
      UP_NGINX_COPY=true
    fi
  done < <(fu_nginx_targets)
}

up_units() {
  local -a changed=()
  [[ -n "$(fu_units_list)" ]] || return 0
  mapfile -t changed < <(REFRESH_PREVIEW=1 SYSTEMD_UNIT_DIR="$UNIT_DIR" ADMINPANELAZ_UNIT_ROOT="$INSTALL_DIR" \
    bash "$UP_NEW_ROOT/scripts/refresh-systemd-units.sh" 2>/dev/null || true)
  if ((${#changed[@]} > 0)); then
    UP_CHANGE+=("Службы systemd: $(up_join "${changed[@]}")")
  else
    UP_KEEP+=("Службы systemd — без изменений")
  fi
}

up_server_settings() {
  if fu_firewall_configured; then
    UP_CHANGE+=("Правила firewall AdminPanelAZ проверятся, недостающие добавятся; ваши правила не трогаются")
  fi
  if [[ -f "${DDNS_CONFIG:-/etc/adminpanelaz/ddns.env}" ]]; then
    UP_CHANGE+=("Таймер DDNS обновится")
  fi
}

up_effects() {
  local unit
  if panel_uses_systemd; then
    UP_CHANGE+=("Интерфейс панели соберётся заново")
    UP_EFFECT+=("Панель будет недоступна примерно 10–30 секунд, пока перезапускается")
  fi
  while IFS= read -r unit; do
    UP_EFFECT+=("Агент $unit перезапустится — панель на несколько секунд потеряет связь с этим сервером")
  done < <(menu_agent_units)
  UP_EFFECT+=("VPN-клиенты остаются подключёнными: OpenVPN и WireGuard не перезапускаются")
  if panel_uses_systemd; then
    UP_EFFECT+=("Перед обновлением делается резервная копия панели; восстановить — sudo adminpanelaz $FU_ARROW 6")
  fi
  UP_REMOVE+=("Ваши данные не удаляются: база, настройки, пользователи, VPN-клиенты, сертификаты")
  if [[ "$UP_NGINX_COPY" == true ]]; then
    UP_REMOVE+=("Старый конфиг nginx останется рядом копией .bak-<дата>")
  fi
}

up_section() {
  local item
  (($# > 1)) || return 0
  ui_section "$1"
  shift
  for item in "$@"; do
    printf '  %s %s\n' "$UP_BULLET" "$item"
  done
}

# up_render <новая ревизия | "" — git fetch не прошёл>
up_render() {
  # Сборка конфига nginx на пробу не должна дописывать сниппеты Cloudflare: только в этом процессе.
  nginx_ensure_cloudflare_realip_snippet() { :; }
  nginx_ensure_cloudflare_origin_snippets() { :; }
  ui_section "Полное обновление AdminPanelAZ"
  up_header "$1"
  up_command
  up_apt
  up_pip
  up_nginx
  up_units
  up_server_settings
  up_effects
  up_section "Добавится" ${UP_ADD[@]+"${UP_ADD[@]}"}
  up_section "Изменится" ${UP_CHANGE[@]+"${UP_CHANGE[@]}"}
  up_section "Не изменится" ${UP_KEEP[@]+"${UP_KEEP[@]}"}
  up_section "Удалится" "${UP_REMOVE[@]}"
  up_section "Как это повлияет" "${UP_EFFECT[@]}"
  printf '\n'
}
