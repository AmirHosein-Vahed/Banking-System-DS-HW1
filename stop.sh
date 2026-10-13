#!/usr/bin/env bash
set -euo pipefail

for vm in server-a server-b client1 witness; do
  if lxc info "$vm" >/dev/null 2>&1; then
    lxc exec "$vm" -- pkill -f 'server.py' 2>/dev/null || true
    lxc exec "$vm" -- pkill -f 'arbiter.py' 2>/dev/null || true
    lxc exec "$vm" -- pkill -f 'uvicorn web.app:app' 2>/dev/null || true
    lxc stop "$vm" --force 2>/dev/null || true
  fi
done

echo "Stopped project services and VMs."
