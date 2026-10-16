#!/usr/bin/env bash
set -euo pipefail

# run.sh - bootstrap and run the LXD-based banking deployment

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SUBNET="${BRIDGE_SUBNET:-10.187.220}"
IP_A="${IP_A:-${BRIDGE_SUBNET}.10}"
IP_B="${IP_B:-${BRIDGE_SUBNET}.11}"
IP_CLIENT="${IP_CLIENT:-${BRIDGE_SUBNET}.20}"
IP_WITNESS="${IP_WITNESS:-${BRIDGE_SUBNET}.30}"
CLUSTER="${CLUSTER:-0}"
WEB_PORT="${WEB_PORT:-8080}"
BANK_PORT="${BANK_PORT:-5000}"

VM_A="server-a"
VM_B="server-b"
VM_CLIENT="client1"
VM_WITNESS="witness"

info() { echo "[run.sh] $*"; }

ensure_vm() {
  local name="$1"
  if ! lxc info "$name" >/dev/null 2>&1; then
    info "launching $name"
    lxc launch ubuntu:22.04 "$name" --vm
  else
    lxc start "$name" 2>/dev/null || true
  fi
  # wait until running
  for _ in $(seq 1 60); do
    state="$(lxc info "$name" 2>/dev/null | awk '/^Status:/{print $2}')"
    [[ "$state" == "RUNNING" ]] && break
    sleep 2
  done
  # wait until the VM agent is reachable (lxc exec works)
  for _ in $(seq 1 60); do
    if lxc exec "$name" -- true 2>/dev/null; then
      break
    fi
    sleep 2
  done
}

ensure_vm "$VM_A"
ensure_vm "$VM_B"
ensure_vm "$VM_CLIENT"
ensure_vm "$VM_WITNESS"

# pin static IPs (best effort)
lxc config device override "$VM_A" eth0 "ipv4.address=$IP_A" 2>/dev/null || true
lxc config device override "$VM_B" eth0 "ipv4.address=$IP_B" 2>/dev/null || true
lxc config device override "$VM_CLIENT" eth0 "ipv4.address=$IP_CLIENT" 2>/dev/null || true
lxc config device override "$VM_WITNESS" eth0 "ipv4.address=$IP_WITNESS" 2>/dev/null || true

# provision
for vm in "$VM_A" "$VM_B" "$VM_CLIENT" "$VM_WITNESS"; do
  if ! lxc exec "$vm" -- bash -c 'command -v python3 >/dev/null && python3 -c "import venv" >/dev/null 2>&1'; then
    info "provisioning $vm"
    lxc exec "$vm" -- bash -c 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv curl'
  fi
done

# copy project (exclude host-specific / generated files)
info "copying project into VMs"
tar czf /tmp/banking.tgz \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='data' \
  --exclude='logs' \
  --exclude='banking.conf' \
  -C "$BASE_DIR" .

for vm in "$VM_A" "$VM_B" "$VM_CLIENT" "$VM_WITNESS"; do
  lxc exec "$vm" -- mkdir -p /opt/banking
  lxc exec "$vm" -- rm -f /tmp/banking.tgz
  lxc file push --mode=0644 /tmp/banking.tgz "$vm/tmp/banking.tgz"
  lxc exec "$vm" -- tar xzf /tmp/banking.tgz -C /opt/banking
done

# firewall
lxc exec "$VM_A" -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 7000/tcp; ufw allow 8000/tcp' 2>/dev/null || true
lxc exec "$VM_B" -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 7000/tcp; ufw allow 8000/tcp' 2>/dev/null || true
lxc exec "$VM_WITNESS" -- bash -c 'ufw allow 8000/tcp' 2>/dev/null || true

# stop old service processes / units
for vm in "$VM_A" "$VM_B"; do
  lxc exec "$vm" -- bash -c 'systemctl stop banking-server 2>/dev/null; systemctl reset-failed banking-server 2>/dev/null; pkill -f server.py 2>/dev/null' || true
done
lxc exec "$VM_WITNESS" -- bash -c 'systemctl stop banking-arbiter 2>/dev/null; systemctl reset-failed banking-arbiter 2>/dev/null; pkill -f arbiter.py 2>/dev/null' || true
lxc exec "$VM_CLIENT" -- bash -c 'systemctl stop banking-web 2>/dev/null; systemctl reset-failed banking-web 2>/dev/null; pkill -f "uvicorn web.app:app" 2>/dev/null' || true
sleep 1

lxc exec "$VM_A" -- bash -c 'cd /opt/banking && cp -f banking.conf.example banking.conf'
lxc exec "$VM_B" -- bash -c 'cd /opt/banking && cp -f banking.conf.example banking.conf'

start_unit() {
  local vm="$1"; shift
  lxc exec "$vm" -- systemd-run --unit=banking-server --collect --property=WorkingDirectory=/opt/banking "$@"
}

if [[ "$CLUSTER" == "1" ]]; then
  info "starting cluster mode"
  start_unit "$VM_A" python3 server.py --config /opt/banking/banking.conf --cluster --role primary --node-id A --repl-port 6000 --peers "${IP_B}:6000" --arbiter "${IP_WITNESS}:8000"
  start_unit "$VM_B" python3 server.py --config /opt/banking/banking.conf --cluster --role backup --node-id B --repl-port 6000 --peers "${IP_A}:6000" --arbiter "${IP_WITNESS}:8000"
else
  info "starting single-server mode"
  start_unit "$VM_A" python3 server.py --config /opt/banking/banking.conf
  start_unit "$VM_B" python3 server.py --config /opt/banking/banking.conf
fi

lxc exec "$VM_WITNESS" -- systemd-run --unit=banking-arbiter --collect --property=WorkingDirectory=/opt/banking python3 arbiter.py --host 0.0.0.0 --port 8000

# web frontend (install deps only if missing/broken)
info "preparing web frontend on $VM_CLIENT"
lxc exec "$VM_CLIENT" -- bash -c '
cd /opt/banking
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import fastapi, uvicorn, jinja2" >/dev/null 2>&1; then
  rm -rf .venv
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="/root/.local/bin:$PATH"
  uv venv .venv
  uv pip install -r web/requirements.txt
fi
'

lxc exec "$VM_CLIENT" -- systemd-run --unit=banking-web --collect --property=WorkingDirectory=/opt/banking --setenv=BANK_SERVERS="${IP_A}:${BANK_PORT},${IP_B}:${BANK_PORT}" /opt/banking/.venv/bin/python -m uvicorn web.app:app --host 0.0.0.0 --port "${WEB_PORT}"

# health checks
sleep 5
info "health checks"
if ! lxc exec "$VM_CLIENT" -- bash -c "curl -fsS http://127.0.0.1:${WEB_PORT}/ >/dev/null 2>&1"; then
  echo "[run.sh] WEB HEALTH CHECK FAILED. Last log lines:"
  lxc exec "$VM_CLIENT" -- journalctl -u banking-web -n 40 --no-pager || true
  exit 1
fi

if ! lxc exec "$VM_A" -- bash -c "python3 - <<'PY'
import socket,sys
s=socket.socket(); s.settimeout(2)
sys.exit(0 if s.connect_ex(('127.0.0.1',${BANK_PORT}))==0 else 1)
PY"; then
  echo "[run.sh] BANKING SERVER HEALTH CHECK FAILED. Last log lines:"
  lxc exec "$VM_A" -- journalctl -u banking-server -n 40 --no-pager || true
  exit 1
fi

echo ""
echo "Deployment is running."
echo "Bank primary: http://${IP_A}:${BANK_PORT}"
echo "Bank backup:  http://${IP_B}:${BANK_PORT}"
echo "Web UI:       http://${IP_CLIENT}:${WEB_PORT}"
echo ""
echo "NOTE: if you use an HTTP proxy, bypass it for the LXD subnet (${BRIDGE_SUBNET}.0/24),"
echo "      otherwise browsers/curl may show '502 Bad Gateway'."
echo "      Example: export no_proxy=localhost,127.0.0.1,${BRIDGE_SUBNET}.0/24"
echo "               curl --noproxy '*' http://${IP_CLIENT}:${WEB_PORT}/"
echo ""
lxc list
