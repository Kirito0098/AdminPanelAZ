#!/usr/bin/env bash
# Генерация CA и клиентских сертификатов для mTLS панель ↔ node agent.
# Для ручной отладки и legacy-установок. В штатном режиме mTLS включается из панели
# (страница «Узлы» → «Включить mTLS» на каждом удалённом узле).
set -euo pipefail

OUT_DIR="${1:-/etc/adminpanelaz/mtls}"
DAYS="${MTLS_CERT_DAYS:-3650}"
CN_CA="${MTLS_CA_CN:-AdminPanelAZ-CA}"
CN_PANEL="${MTLS_PANEL_CN:-adminpanelaz-panel}"
CN_AGENT="${MTLS_AGENT_CN:-adminpanelaz-node-agent}"

log() { echo "[generate-mtls-certs] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Запустите от root: sudo $0 [output_dir]"
  exit 1
fi

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
cd "$OUT_DIR"

if [[ -f ca.crt && -f panel.crt && -f agent.crt ]]; then
  log "Сертификаты уже существуют в $OUT_DIR — удалите вручную для перегенерации"
  exit 0
fi

log "Создание CA..."
openssl genrsa -out ca.key 4096
chmod 600 ca.key
openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS" -out ca.crt \
  -subj "/CN=$CN_CA/O=AdminPanelAZ/C=RU"

gen_client() {
  local name="$1"
  local cn="$2"
  openssl genrsa -out "${name}.key" 2048
  chmod 600 "${name}.key"
  openssl req -new -key "${name}.key" -out "${name}.csr" \
    -subj "/CN=$cn/O=AdminPanelAZ/C=RU"
  openssl x509 -req -in "${name}.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out "${name}.crt" -days "$DAYS" -sha256
  rm -f "${name}.csr"
}

log "Сертификат панели (клиент)..."
gen_client panel "$CN_PANEL"

log "Сертификат node agent (сервер)..."
gen_client agent "$CN_AGENT"

chmod 644 ca.crt panel.crt agent.crt

log "Готово: $OUT_DIR"
echo ""
echo "Панель (backend/.env):"
echo "  NODE_AGENT_MTLS_ENABLED=true"
echo "  NODE_AGENT_MTLS_CA_CERT=$OUT_DIR/ca.crt"
echo "  NODE_AGENT_MTLS_CLIENT_CERT=$OUT_DIR/panel.crt"
echo "  NODE_AGENT_MTLS_CLIENT_KEY=$OUT_DIR/panel.key"
echo ""
echo "Node agent (backend/node_agent.env):"
echo "  NODE_AGENT_MTLS_ENABLED=true"
echo "  NODE_AGENT_MTLS_SERVER_CERT=$OUT_DIR/agent.crt"
echo "  NODE_AGENT_MTLS_SERVER_KEY=$OUT_DIR/agent.key"
echo "  NODE_AGENT_MTLS_CA_CERT=$OUT_DIR/ca.crt"
echo ""
echo "Перезапустите панель и node agent после настройки."
