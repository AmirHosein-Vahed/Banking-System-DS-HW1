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

ensure_vm() {
  local name="$1"
  if ! lxc info "$name" >/dev/null 2>&1; then
    lxc launch ubuntu:22.04 "$name" --vm
  else
    lxc start "$name" 2>/dev/null || true
  fi
}

ensure_vm "$VM_A"
ensure_vm "$VM_B"
ensure_vm "$VM_CLIENT"
ensure_vm "$VM_WITNESS"
lxc list

# pin static IPs (best effort)
lxc config device override "$VM_A" eth0 "ipv4.address=$IP_A" 2>/dev/null || true
lxc config device override "$VM_B" eth0 "ipv4.address=$IP_B" 2>/dev/null || true
lxc config device override "$VM_CLIENT" eth0 "ipv4.address=$IP_CLIENT" 2>/dev/null || true
lxc config device override "$VM_WITNESS" eth0 "ipv4.address=$IP_WITNESS" 2>/dev/null || true

# provision
for vm in "$VM_A" "$VM_B" "$VM_CLIENT" "$VM_WITNESS"; do
  lxc exec "$vm" -- bash -c 'apt update && apt install -y python3 python3-pip git python3-venv'
done

# copy project
tar czf /tmp/banking.tgz -C "$BASE_DIR" .
for vm in "$VM_A" "$VM_B" "$VM_CLIENT" "$VM_WITNESS"; do
  lxc exec "$vm" -- mkdir -p /opt/banking
  lxc file push /tmp/banking.tgz "$vm/tmp/banking.tgz"
  lxc exec "$vm" -- tar xzf /tmp/banking.tgz -C /opt/banking
done

# firewall
lxc exec "$VM_A" -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 7000/tcp; ufw allow 8000/tcp || true'
lxc exec "$VM_B" -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 7000/tcp; ufw allow 8000/tcp || true'
lxc exec "$VM_WITNESS" -- bash -c 'ufw allow 8000/tcp || true'

# stop old service processes
for vm in "$VM_A" "$VM_B"; do lxc exec "$vm" -- pkill -f server.py 2>/dev/null || true; done
lxc exec "$VM_WITNESS" -- pkill -f arbiter.py 2>/dev/null || true

if [[ "$CLUSTER" == "1" ]]; then
  lxc exec "$VM_A" -- bash -c "cd /opt/banking && python3 server.py --config banking.conf --cluster --role primary --node-id A --repl-port 6000 --peers ${IP_B}:6000 --arbiter ${IP_WITNESS}:8000 > /tmp/server.log 2>&1 &"
  lxc exec "$VM_B" -- bash -c "cd /opt/banking && python3 server.py --config banking.conf --cluster --role backup --node-id B --repl-port 6000 --peers ${IP_A}:6000 --arbiter ${IP_WITNESS}:8000 > /tmp/server.log 2>&1 &"
else
  lxc exec "$VM_A" -- bash -c 'cd /opt/banking && cp -f banking.conf.example banking.conf && python3 server.py --config banking.conf > /tmp/server.log 2>&1 &'
  lxc exec "$VM_B" -- bash -c 'cd /opt/banking && cp -f banking.conf.example banking.conf && python3 server.py --config banking.conf > /tmp/server.log 2>&1 &'
fi

lxc exec "$VM_WITNESS" -- bash -c 'cd /opt/banking && python3 arbiter.py --host 0.0.0.0 --port 8000 > /tmp/arbiter.log 2>&1 &'

# web frontend
lxc exec "$VM_CLIENT" -- bash -c '
cd /opt/banking
if [ ! -x .venv/bin/python ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  source /root/.local/bin/env
  uv venv .venv
  uv pip install -r web/requirements.txt
fi
source .venv/bin/activate
BANK_SERVERS='"${IP_A}:${BANK_PORT},${IP_B}:${BANK_PORT}"' WEB_PORT='"${WEB_PORT}"' uvicorn web.app:app --host 0.0.0.0 --port '"${WEB_PORT}"' > /tmp/web.log 2>&1 &
'

echo "Deployment started."
echo "Primary/backend: http://${IP_A}:${BANK_PORT}"
echo "Backup/backend:  http://${IP_B}:${BANK_PORT}"
echo "Web UI:         http://${IP_CLIENT}:${WEB_PORT}"
echo ""
echo "Use 'lxc list' to verify IPs and 'lxc file pull ...' to collect logs."

# keep script alive? comment next line out to let shell exit
wait
