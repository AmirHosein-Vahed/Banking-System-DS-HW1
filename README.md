# Mini Banking Transaction Server

Simulated client–server banking system for DS Assignment 1. Python, TCP sockets, newline-delimited JSON, SQLite (WAL, fsync) for durability.

## Features
- Ops: `balance`, `deposit`, `withdraw` (plus cluster replication)
- Configurable max simultaneous clients
- Per-account locks + SQLite transactions (serializable writes, non-negative balances)
- Meaningful errors, JSON-line logging with request ID/IP/action/account/timestamp/result/latency
- Optional fault-tolerant cluster (`--cluster`) and arbiter/witness for split-brain prevention

## Quick start (single server)
```bash
cp banking.conf.example banking.conf
python3 server.py --config banking.conf
python3 client.py --host <server-ip> --port 5000
```

Commands:
```text
balance A1001
deposit A1001 100
withdraw A1001 50
```

Stress:
```bash
python3 client.py --host <server-ip> --port 5000 --stress 50
```

## Tests
```bash
python3 -m unittest tests.test_core -v
python3 -m unittest tests.test_cluster -v
```

## Error cases
Unknown account, insufficient funds, negative/zero/non-numeric amount, unsupported action, missing fields, malformed JSON/random bytes. Server stays running.

## ACID demos
- Concurrency: 50 threads withdraw from the same account; final balance is correct, no negatives.
- Half-failed request leaves account unchanged.
- Kill/restart server; committed balances persist (SQLite WAL).

## Cluster mode (+fault tolerance)
```bash
# Server A (primary)
python3 server.py --config banking.conf --cluster --role primary --node-id A \
  --repl-port 6000 --peers <B-ip>:6000 --arbiter <witness-ip>:8000

# Server B (backup)
python3 server.py --config banking.conf --cluster --role backup --node-id B \
  --repl-port 6000 --peers <A-ip>:6000 --arbiter <witness-ip>:8000

# Witness
python3 arbiter.py --host 0.0.0.0 --port 8000
```

Client failover:
```bash
python3 client.py --servers <A-ip>:5000,<B-ip>:5000
```

## LXD deployment (VMs)
Install and init LXD:
```bash
sudo snap install lxd
sudo lxd init
```

Create VMs:
```bash
lxc launch ubuntu:22.04 server-a --vm
lxc launch ubuntu:22.04 server-b --vm
lxc launch ubuntu:22.04 client1  --vm
lxc launch ubuntu:22.04 witness  --vm
lxc list
```

Provision each VM:
```bash
lxc exec server-a -- bash -c 'apt update && apt install -y python3 python3-pip git'
```

Copy code:
```bash
lxc file push -r . server-a/opt/banking
```

Create static IP (example):
```bash
lxc config device override server-a eth0 ipv4.address=10.0.0.10
```

Snapshots:
```bash
lxc snapshot server-a baseline
lxc restore server-a baseline
```

Failure injection:
```bash
# crash primary
lxc exec server-a -- pkill -f server.py
# network partition example (inside VM or host tc/iptables)
```

Collect logs:
```bash
lxc file pull server-a/opt/banking/logs/server.log ./server-a.log
```

Always use real VM IPs (never `localhost`) for client connections.

## Project files
- `server.py` — threaded TCP server, request handling, concurrency cap, role checks
- `client.py` — interactive client, `--stress` load generator, failover list
- `storage.py` — SQLite persistence, schema, seed accounts, transactional apply, idempotency
- `accounts.py` — per-account lock manager and account service
- `protocol.py` — request parsing/validation and response builders
- `logger.py` — JSON-line request/response logging
- `cluster.py` — replication, heartbeat promotion, sync scaffolding
- `arbiter.py` — witness node for quorum decisions
- `banking.conf.example` — sample server configuration
- `requirements.txt` — dependency/runtime notes
- `tests/test_core.py` — core, durability, and error tests
- `tests/test_cluster.py` — replication and failover smoke test
- `AGENTS.md` — repository guidance for coding agents
