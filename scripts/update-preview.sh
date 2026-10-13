#!/usr/bin/env bash
# Экран «что изменится» перед полным обновлением (full-update.sh --preview). Его показывает код НОВОЙ версии,
# распакованный во временную папку, против рабочего каталога INSTALL_DIR; ничего не записывает. Подключается из
# full-update.sh.

UP_NEW_ROOT="$(cd "$FU_DIR/.." && pwd)"
UP_NEWS_LIMIT=6
UP_DETAIL_LIMIT=12
UP_BULLET="-"
case "${MENU_USER_LOCALE,,}" in
  *utf-8* | *utf8*) UP_BULLET="•" ;;
esac
UP_ADD=()
UP_CHANGE=()
UP_KEEP=()
UP_REMOVE=()
UP_EFFECT=()
UP_RECHECK=()
UP_NGINX_COPY=false
UP_UNITS_CHANGED=false
# Подробности пункта: строки «вид<TAB>текст», вид — minus | plus | why | info.
declare -A UP_DETAIL=()
# --server-only: без кода, Python, сборки и перезапуска. UP_FORMAT=tsv — строки «раздел<TAB>пункт» для веба.
UP_SERVER_ONLY="${UP_SERVER_ONLY:-false}"
UP_FORMAT="${UP_FORMAT:-text}"

up_detail() {
  UP_DETAIL[$1]+="$2"$'\t'"$3"$'\n'
}

# up_detail_list <пункт> <вид> [строка…]: не больше UP_DETAIL_LIMIT строк, остальное — «… и ещё N».
up_detail_list() {
  local item="$1" kind="$2" line shown=0
  shift 2
  for line in "$@"; do
    if ((shown == UP_DETAIL_LIMIT)); then
      up_detail "$item" "$kind" "… и ещё $(($# - UP_DETAIL_LIMIT))"
      return 0
    fi
    up_detail "$item" "$kind" "$line"
    shown=$((shown + 1))
  done
}

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

# Отступы, пустые строки и перевод строки в конце файла отличием не считаются.
up_conf_lines() {
  sed -e 's/\t/ /g' -e 's/^ *//' -e 's/ *$//' -e '/^$/d'
}

# Почему важно — по тому, какие строки меняются. Новая причина — новая ветка здесь, когда меняется шаблон nginx.
up_nginx_why() {
  if grep -qE 'add_header (Strict-Transport-Security|X-Content-Type-Options|X-Frame-Options|Referrer-Policy|Permissions-Policy)' <<<"$1"; then
    printf '%s\n' "Заголовки безопасности теперь ставит сама панель: если их ставит и nginx, браузер получает их дважды с разными значениями, а сканеры безопасности считают это ошибкой. Защита не ослабевает"
  else
    printf '%s\n' "Конфиг собран по шаблону новой версии — что поменялось в шаблоне, описано в CHANGELOG"
  fi
}

up_nginx_detail() {
  local item="$1" file="$2" conf="$3" line
  local -a minus=() plus=()
  while IFS= read -r line; do
    case "$line" in
      "< "*) minus+=("${line#< }") ;;
      "> "*) plus+=("${line#> }") ;;
    esac
  done < <(diff <(up_conf_lines <"$file") <(up_conf_lines <<<"$conf") || true)
  up_detail_list "$item" minus ${minus[@]+"${minus[@]}"}
  up_detail_list "$item" plus ${plus[@]+"${plus[@]}"}
  up_detail "$item" why "$(up_nginx_why "$(printf '%s\n' ${minus[@]+"${minus[@]}"} ${plus[@]+"${plus[@]}"})")"
}

up_nginx() {
  local kind host file conf item
  panel_uses_systemd && fu_nginx_published || return 0
  while IFS=$'\t' read -r kind host file; do
    if ! conf="$(fu_nginx_render "$kind" "$host" "$file" 2>/dev/null)"; then
      UP_KEEP+=("Конфиг nginx для $host — новый не собрать, останется прежний")
    elif [[ "$(up_conf_lines <<<"$conf")" == "$(up_conf_lines <"$file")" ]]; then
      UP_KEEP+=("Конфиг nginx для $host — уже актуален")
    else
      item="Конфиг nginx для $host устарел — обновится"
      UP_CHANGE+=("$item")
      up_nginx_detail "$item" "$file" "$conf"
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
    UP_UNITS_CHANGED=true
  else
    UP_KEEP+=("Службы systemd — без изменений")
  fi
}

up_firewall_detail() {
  local item="$1" backend https http nginx ip open
  if ! fu_firewall_args; then
    up_detail "$item" info "Правила не изменятся: IP панели не записан в node_agent.env / proxy_agent.env"
    return 0
  fi
  backend="${FU_FW_ARGS[0]}" https="${FU_FW_ARGS[2]}" http="${FU_FW_ARGS[3]}" nginx="${FU_FW_ARGS[5]}" ip="${FU_FW_ARGS[6]}"
  if [[ "$nginx" == true ]]; then
    open="$https"
    [[ "$http" == 0 ]] || open+=", $http"
    if [[ "$backend" != 0 ]]; then
      up_detail "$item" info "Открыты для всех: $open — сайт панели через nginx"
    else
      up_detail "$item" info "Открыт для всех: $open — панель"
    fi
  fi
  if [[ "$backend" != 0 ]]; then
    if [[ "$nginx" == true ]]; then
      up_detail "$item" info "Закрыт снаружи: $backend — сама панель, доступ к ней только через nginx"
    else
      up_detail "$item" info "Закрыт снаружи: $backend — внутренний порт панели"
    fi
  fi
  if [[ "${FU_FW_ARGS[4]}" == true ]]; then
    up_detail "$item" info "Только с IP панели $ip: ${FU_FW_ARGS[1]} — агент узла"
  fi
  if [[ "${FU_FW_ARGS[7]}" == true ]]; then
    up_detail "$item" info "Только с IP панели $ip: ${FU_FW_ARGS[8]} — прокси-агент"
  fi
  up_detail "$item" info "SSH остаётся открытым"
  up_detail "$item" why "Если правило пропало (сброс firewall, чужой скрипт), сайт панели может перестать открываться, а внутренний порт — оказаться открытым в интернет"
}

up_server_settings() {
  local item
  if fu_firewall_configured; then
    item="Правила firewall AdminPanelAZ проверятся, недостающие добавятся; ваши правила не трогаются"
    UP_RECHECK+=("$item")
    up_firewall_detail "$item"
  fi
  if [[ -f "${DDNS_CONFIG:-/etc/adminpanelaz/ddns.env}" ]]; then
    UP_RECHECK+=("Таймер DDNS обновится")
  fi
}

up_effects() {
  local unit
  if [[ "$UP_SERVER_ONLY" == true ]]; then
    UP_EFFECT+=("Панель и агенты не перезапускаются")
    if [[ "$UP_NGINX_COPY" == true ]]; then
      UP_EFFECT+=("nginx перечитает настройки без обрыва соединений")
    fi
    if [[ "$UP_UNITS_CHANGED" == true ]]; then
      UP_EFFECT+=("Новые настройки служб применятся при следующем перезапуске панели")
    fi
  else
    if panel_uses_systemd; then
      UP_CHANGE+=("Интерфейс панели соберётся заново")
      UP_EFFECT+=("Панель будет недоступна примерно 10–30 секунд, пока перезапускается")
    fi
    while IFS= read -r unit; do
      UP_EFFECT+=("Агент $unit перезапустится — панель на несколько секунд потеряет связь с этим сервером")
    done < <(menu_agent_units)
  fi
  UP_EFFECT+=("VPN-клиенты остаются подключёнными: OpenVPN и WireGuard не перезапускаются")
  if [[ "$UP_SERVER_ONLY" != true ]] && panel_uses_systemd; then
    UP_EFFECT+=("Перед обновлением делается резервная копия панели; восстановить — sudo adminpanelaz $FU_ARROW 6")
  fi
  UP_REMOVE+=("Ваши данные не удаляются: база, настройки, пользователи, VPN-клиенты, сертификаты")
  if [[ "$UP_NGINX_COPY" == true ]]; then
    UP_REMOVE+=("Старый конфиг nginx останется рядом копией .bak-<дата>")
  fi
}

up_print_details() {
  local kind text
  [[ -n "${UP_DETAIL[$1]-}" ]] || return 0
  while IFS=$'\t' read -r kind text; do
    if [[ "$UP_FORMAT" == tsv ]]; then
      printf '%s\t%s\n' "$kind" "$text"
      continue
    fi
    case "$kind" in
      minus) printf '      уберётся: %s\n' "$text" ;;
      plus) printf '      добавится: %s\n' "$text" ;;
      why) printf '      почему: %s\n' "$text" ;;
      *) printf '      %s\n' "$text" ;;
    esac
  done <<<"${UP_DETAIL[$1]%$'\n'}"
}

# up_section <ключ для tsv> <заголовок> [пункт…]; под пунктом — его подробности.
up_section() {
  local key="$1" title="$2" item
  shift 2
  (($# > 0)) || return 0
  [[ "$UP_FORMAT" == tsv ]] || ui_section "$title"
  for item in "$@"; do
    if [[ "$UP_FORMAT" == tsv ]]; then
      printf '%s\t%s\n' "$key" "$item"
    else
      printf '  %s %s\n' "$UP_BULLET" "$item"
    fi
    up_print_details "$item"
  done
}

# up_render <новая ревизия | "" — git fetch не прошёл>
up_render() {
  # Сборка конфига nginx на пробу не должна дописывать сниппеты Cloudflare: только в этом процессе.
  nginx_ensure_cloudflare_realip_snippet() { :; }
  nginx_ensure_cloudflare_origin_snippets() { :; }
  if [[ "$UP_FORMAT" != tsv ]]; then
    ui_section "Полное обновление AdminPanelAZ"
  fi
  if [[ "$UP_SERVER_ONLY" != true ]]; then
    up_header "$1"
  fi
  up_command
  up_apt
  if [[ "$UP_SERVER_ONLY" != true ]]; then
    up_pip
  fi
  up_nginx
  up_units
  up_server_settings
  up_effects
  up_section add "Добавится" ${UP_ADD[@]+"${UP_ADD[@]}"}
  if [[ "$UP_FORMAT" == tsv ]]; then
    up_section change "" ${UP_CHANGE[@]+"${UP_CHANGE[@]}"}
    up_section recheck "" ${UP_RECHECK[@]+"${UP_RECHECK[@]}"}
  else
    up_section change "Изменится" ${UP_CHANGE[@]+"${UP_CHANGE[@]}"} ${UP_RECHECK[@]+"${UP_RECHECK[@]}"}
  fi
  up_section keep "Не изменится" ${UP_KEEP[@]+"${UP_KEEP[@]}"}
  up_section remove "Удалится" "${UP_REMOVE[@]}"
  up_section effect "Как это повлияет" "${UP_EFFECT[@]}"
  if [[ "$UP_FORMAT" != tsv ]]; then
    printf '\n'
  fi
}
