#!/usr/bin/env bash
# Настройка firewall при установке AdminPanelAZ (вызывается из install.sh)
set -euo pipefail

firewall_log() {
  echo "[firewall] $*"
}

firewall_warn() {
  echo "[firewall] ВНИМАНИЕ: $*" >&2
}

firewall_detect_tool() {
  if command -v ufw >/dev/null 2>&1; then
    echo "ufw"
  elif command -v iptables >/dev/null 2>&1; then
    echo "iptables"
  else
    echo "none"
  fi
}

firewall_validate_ports() {
  local backend_port="$1"
  local node_port="$2"
  local https_port="$3"
  local http_port="$4"
  local has_node="$5"
  local has_nginx="$6"
  local -a ports=()
  local -a names=()

  if [[ "$backend_port" != "0" ]]; then
    ports+=("$backend_port")
    names+=("backend")
  fi
  if [[ "$has_nginx" == true ]]; then
    ports+=("$https_port" "$http_port")
    names+=("HTTPS" "HTTP (ACME)")
  fi
  if [[ "$has_node" == true ]]; then
    ports+=("$node_port")
    names+=("node agent")
  fi

  local i j
  for ((i = 0; i < ${#ports[@]}; i++)); do
    for ((j = i + 1; j < ${#ports[@]}; j++)); do
      if [[ "${ports[$i]}" == "${ports[$j]}" ]]; then
        echo "Конфликт портов: ${names[$i]} и ${names[$j]} — оба используют порт ${ports[$i]}."
        return 1
      fi
    done
  done
  return 0
}

firewall_show_rules_summary() {
  local backend_port="$1"
  local node_port="$2"
  local https_port="$3"
  local http_port="$4"
  local has_node="$5"
  local has_nginx="$6"
  local panel_ip="${7:-}"

  echo "  Планируемые правила firewall:"
  if [[ "$backend_port" != "0" ]]; then
    echo "    • Закрыть ${backend_port}/tcp с интернета (backend только на 127.0.0.1)"
  fi
  if [[ "$has_node" == true ]]; then
    if [[ -n "$panel_ip" ]]; then
      echo "    • Порт node agent ${node_port}/tcp — только с IP панели: ${panel_ip}"
    else
      echo "    • Закрыть ${node_port}/tcp с интернета (node agent)"
    fi
  fi
  if [[ "$has_nginx" == true ]]; then
    echo "    • Открыть ${https_port}/tcp (HTTPS, Nginx)"
    echo "    • Открыть ${http_port}/tcp (HTTP, ACME / редирект)"
  fi
}

firewall_show_manual_instructions() {
  local backend_port="$1"
  local node_port="$2"
  local https_port="$3"
  local http_port="$4"
  local has_node="$5"
  local has_nginx="$6"
  local panel_ip="${7:-}"

  firewall_warn "Автоматическая настройка firewall недоступна (нет ufw/iptables)."
  echo
  echo "Настройте firewall вручную (пример для ufw):"
  if [[ "$backend_port" != "0" ]]; then
    echo "  sudo ufw deny ${backend_port}/tcp comment 'AdminPanelAZ backend'"
  fi
  if [[ "$has_node" == true ]]; then
    if [[ -n "$panel_ip" ]]; then
      echo "  sudo ufw allow from ${panel_ip} to any port ${node_port} proto tcp comment 'AdminPanelAZ node agent'"
      echo "  sudo ufw deny ${node_port}/tcp comment 'AdminPanelAZ node agent'"
    else
      echo "  sudo ufw deny ${node_port}/tcp comment 'AdminPanelAZ node agent'"
    fi
  fi
  if [[ "$has_nginx" == true ]]; then
    echo "  sudo ufw allow ${https_port}/tcp comment 'AdminPanelAZ HTTPS'"
    echo "  sudo ufw allow ${http_port}/tcp comment 'AdminPanelAZ HTTP (ACME)'"
  fi
  echo "  sudo ufw enable   # если ufw ещё не активен"
  echo
  echo "Пример для iptables:"
  if [[ "$backend_port" != "0" ]]; then
    echo "  iptables -A INPUT -p tcp --dport ${backend_port} ! -s 127.0.0.1 -j DROP"
  fi
  if [[ "$has_node" == true && -n "$panel_ip" ]]; then
    echo "  iptables -A INPUT -p tcp --dport ${node_port} ! -s ${panel_ip} -j DROP"
  elif [[ "$has_node" == true ]]; then
    echo "  iptables -A INPUT -p tcp --dport ${node_port} -j DROP"
  fi
  if [[ "$has_nginx" == true ]]; then
    echo "  iptables -A INPUT -p tcp --dport ${https_port} -j ACCEPT"
    echo "  iptables -A INPUT -p tcp --dport ${http_port} -j ACCEPT"
  fi
}

firewall_apply_ufw_rules() {
  local backend_port="$1"
  local node_port="$2"
  local https_port="$3"
  local http_port="$4"
  local has_node="$5"
  local has_nginx="$6"
  local panel_ip="${7:-}"

  if ufw status 2>/dev/null | grep -q "Status: active"; then
    :
  elif [[ "${FIREWALL_ENABLE_UFW:-}" == "true" ]]; then
    firewall_log "Включение ufw..."
    ufw --force enable
  else
    firewall_warn "ufw установлен, но не активен. Правила будут добавлены; включите: sudo ufw enable"
  fi

  if [[ "$backend_port" != "0" ]]; then
    ufw deny "${backend_port}/tcp" comment "AdminPanelAZ backend" >/dev/null 2>&1 || \
      ufw deny "${backend_port}/tcp" >/dev/null 2>&1 || true
  fi

  if [[ "$has_node" == true ]]; then
    if [[ -n "$panel_ip" ]]; then
      ufw allow from "${panel_ip}" to any port "${node_port}" proto tcp \
        comment "AdminPanelAZ node agent" >/dev/null 2>&1 || \
        ufw allow from "${panel_ip}" to any port "${node_port}" proto tcp >/dev/null 2>&1 || true
    fi
    ufw deny "${node_port}/tcp" comment "AdminPanelAZ node agent" >/dev/null 2>&1 || \
      ufw deny "${node_port}/tcp" >/dev/null 2>&1 || true
  fi

  if [[ "$has_nginx" == true ]]; then
    ufw allow "${https_port}/tcp" comment "AdminPanelAZ HTTPS" >/dev/null 2>&1 || \
      ufw allow "${https_port}/tcp" >/dev/null 2>&1 || true
    ufw allow "${http_port}/tcp" comment "AdminPanelAZ HTTP (ACME)" >/dev/null 2>&1 || \
      ufw allow "${http_port}/tcp" >/dev/null 2>&1 || true
  fi

  ufw reload >/dev/null 2>&1 || true
}

firewall_apply_iptables_rules() {
  local backend_port="$1"
  local node_port="$2"
  local https_port="$3"
  local http_port="$4"
  local has_node="$5"
  local has_nginx="$6"
  local panel_ip="${7:-}"

  if [[ "$backend_port" != "0" ]]; then
    if ! iptables -C INPUT -p tcp --dport "$backend_port" ! -s 127.0.0.1 -j DROP 2>/dev/null; then
      iptables -A INPUT -p tcp --dport "$backend_port" ! -s 127.0.0.1 -j DROP
    fi
  fi

  if [[ "$has_node" == true ]]; then
    if [[ -n "$panel_ip" ]]; then
      if ! iptables -C INPUT -p tcp --dport "$node_port" ! -s "$panel_ip" -j DROP 2>/dev/null; then
        iptables -A INPUT -p tcp --dport "$node_port" ! -s "$panel_ip" -j DROP
      fi
    elif ! iptables -C INPUT -p tcp --dport "$node_port" -j DROP 2>/dev/null; then
      iptables -A INPUT -p tcp --dport "$node_port" -j DROP
    fi
  fi

  if [[ "$has_nginx" == true ]]; then
    if ! iptables -C INPUT -p tcp --dport "$https_port" -j ACCEPT 2>/dev/null; then
      iptables -A INPUT -p tcp --dport "$https_port" -j ACCEPT
    fi
    if ! iptables -C INPUT -p tcp --dport "$http_port" -j ACCEPT 2>/dev/null; then
      iptables -A INPUT -p tcp --dport "$http_port" -j ACCEPT
    fi
  fi

  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save >/dev/null 2>&1 || true
  elif [[ -d /etc/iptables ]]; then
    iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
  else
    firewall_warn "Сохраните правила iptables вручную (iptables-save > /etc/iptables/rules.v4)"
  fi
}

firewall_apply_rules() {
  local backend_port="$1"
  local node_port="$2"
  local https_port="$3"
  local http_port="$4"
  local has_node="$5"
  local has_nginx="$6"
  local panel_ip="${7:-}"

  if ! firewall_validate_ports "$backend_port" "$node_port" "$https_port" "$http_port" "$has_node" "$has_nginx"; then
    return 1
  fi

  local tool
  tool="$(firewall_detect_tool)"

  case "$tool" in
    ufw)
      firewall_log "Применение правил через ufw..."
      firewall_apply_ufw_rules "$backend_port" "$node_port" "$https_port" "$http_port" \
        "$has_node" "$has_nginx" "$panel_ip"
      firewall_log "Правила ufw применены."
      ;;
    iptables)
      firewall_log "Применение правил через iptables..."
      firewall_apply_iptables_rules "$backend_port" "$node_port" "$https_port" "$http_port" \
        "$has_node" "$has_nginx" "$panel_ip"
      firewall_log "Правила iptables применены."
      ;;
    none)
      firewall_show_manual_instructions "$backend_port" "$node_port" "$https_port" "$http_port" \
        "$has_node" "$has_nginx" "$panel_ip"
      return 0
      ;;
  esac
  return 0
}
