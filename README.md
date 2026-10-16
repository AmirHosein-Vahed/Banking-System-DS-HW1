# Mini Banking Transaction Server

A simulated client–server banking system built for the DS Assignment 1 brief. It provides account balance inquiry, deposit, and withdrawal over TCP sockets, with correct concurrent access, ACID-style persistence, meaningful errors, request/response logging, an optional fault-tolerant cluster, and a web frontend.

## Overview

- **Core:** Threaded Python TCP server with SQLite durability (`WAL`, `synchronous=FULL`)
- **Concurrency:** Configurable max clients, per-account locks, serializable balance updates
- **Safety:** Validates positive amounts, account existence, and sufficient funds
- **Durability:** Committed state is flushed to disk before replying
- **Errors:** Unknown account, insufficient funds, invalid amount, bad action, missing fields, malformed JSON/bytes
- **Logging:** JSON-line logs with request ID, client IP, action, account, timestamp, result, and latency
- **Bonus:** Primary/backup replication and arbiter-based split-brain prevention
- **Web UI:** FastAPI + Jinja2 dashboard for operations, stress tests, logs, and cluster status

## Repository Files

| File | Purpose |
|---|---|
| `server.py` | Threaded TCP banking server |
| `client.py` | Interactive and stress-test client |
| `storage.py` | SQLite persistence, schema, seed accounts, transactional apply |
| `accounts.py` | Lock manager and account service |
| `protocol.py` | Request parsing/validation and response builders |
| `logger.py` | JSON-line request/response logger |
| `cluster.py` | Replication, heartbeat promotion, and sync scaffolding |
| `arbiter.py` | Witness node for quorum decisions |
| `web/app.py` | FastAPI application and routes |
| `web/templates/` | Jinja2 HTML templates |
| `web/requirements.txt` | Python dependencies for the web UI |
| `logserver.py` | Exposes each node's JSON request log over HTTP for the web `/logs` page |
| `banking.conf.example` | Sample configuration |
| `requirements.txt` | Core runtime/dependency notes |
| `tests/test_core.py` | Core, durability, and error tests |
| `tests/test_concurrency.py` | Concurrency and malformed-request tests |
| `tests/test_protocol.py` | Protocol validation tests |
| `tests/test_cluster.py` | Replication and failover smoke test |
| `tests/test_logserver.py` | Log server startup/serving tests |
| `tests/test_web_ui.py` | Web UI integration tests |
| `run.sh` | End-to-end LXD bootstrap and launch script |
| `stop.sh` | Stop services and VMs |
| `do_tests.sh` | Run the full test suite |
| `AGENTS.md` | Repository notes for coding agents |

## Requirements

- Python 3.10+
- Core has no external dependencies
- Web UI dependencies: FastAPI, Uvicorn, Jinja2, python-multipart

## Running the Core Project

### 1. Create config
```bash
cp banking.conf.example banking.conf
```

### 2. Start server
```bash
python3 server.py --config banking.conf
```

### 3. Start client
```bash
python3 client.py --host <server-ip> --port 5000
```

### Interactive commands
```text
balance A1001
deposit A1001 100
withdraw A1001 50
withdraw A1001 10000
```

### Stress test
```bash
python3 client.py --host <server-ip> --port 5000 --stress 50
```

## Running the Web UI

Install dependencies with uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv venv .venv
uv pip install -r web/requirements.txt
source .venv/bin/activate
```

Run the web app:
```bash
BANK_SERVERS=<server-ip>:5000 uvicorn web.app:app --host 0.0.0.0 --port 8080
```

Open:
```text
http://<vm-ip>:8080
```

Pages:
- `/` Dashboard (balances)
- `/ops` Operations form
- `/stress` Stress test launcher
- `/logs` Recent logs
- `/cluster` Node reachability status

## Running Tests

Run everything (core + web UI) with one command:
```bash
./do_tests.sh
```

Or invoke the modules directly:

```bash
python3 -m unittest tests.test_core tests.test_concurrency tests.test_protocol tests.test_cluster tests.test_logserver -v
.venv/bin/python -m unittest tests.test_web_ui -v
```

## Fault-Tolerant Mode (Bonus)

This is the optional bonus part. It turns the single server into a primary/backup cluster so the
service keeps running when the primary dies, without losing or duplicating transactions.

### Topology
- **Server A** — primary; serves all client traffic
- **Server B** — backup; receives the replicated transaction stream
- **Witness** — `arbiter.py`; breaks ties / provides quorum so the backup does not self-promote during a partition
- **Clients** — connect to whichever node is currently primary (web UI receives both in `BANK_SERVERS`)

### Start manually
Server A (primary):
```bash
python3 server.py --config banking.conf --cluster --role primary --node-id A \
  --repl-port 6000 --peers <B-ip>:6000 --arbiter <witness-ip>:8000
```

Server B (backup):
```bash
python3 server.py --config banking.conf --cluster --role backup --node-id B \
  --repl-port 6000 --peers <A-ip>:6000 --arbiter <witness-ip>:8000
```

Witness:
```bash
python3 arbiter.py --host 0.0.0.0 --port 8000
```

Client with failover list:
```bash
python3 client.py --servers <A-ip>:5000,<B-ip>:5000
```

Or start the whole thing on LXD:
```bash
CLUSTER=1 ./run.sh
```

### How it works
- Every write on the primary is committed locally, then replicated to the backup, and only after
  the backup acknowledges is `success` returned to the client (synchronous replication).
- The primary sends periodic heartbeats to the backup and the witness.
- Each transaction carries a `req_id`; `storage.apply` is idempotent, so a replayed or retried
  request never applies twice.
- If the primary stops heartbeating for about 5 seconds **and the witness is reachable**, the
  backup promotes itself to primary and begins serving clients.
- If the witness is unreachable, the backup refuses to promote. That is the split-brain guard:
  during a real network partition only the side that can still reach a majority may serve writes.

### Algorithms and Mechanisms Used
- **Synchronous primary–backup replication** (passive / state-machine replication): the primary
  serializes writes and forwards each transaction to the backup, waiting for an `ack` before
  replying. `cluster.replicate()` in `cluster.py`.
- **Timeout-based failure detector**: the primary sends a heartbeat every 1s; the backup treats the
  primary as failed after a 5s timeout (`_heartbeat` / `_monitor`).
- **Leader election via timeout + witness reachability (quorum check)**: the backup promotes only
  when the primary is timed out **and** the arbiter is reachable. The witness acts as a tie-breaker
  for the 3-node set, which is what prevents split brain. A `term` field is carried in heartbeats but
  is not used for formal voting or fencing.
- **Idempotency for exactly-once effects**: every request has a `req_id`; `storage.apply()` records
  applied transactions and safely ignores replays, preventing double application across retries or
  failover.
- **Full-state snapshot sync (state transfer)**: `sync_request` / `snapshot` / `sync_apply` copy all
  balances to a lagging node. There is no incremental log-based catch-up.
- **Durability before acknowledgment**: SQLite in WAL mode with `synchronous=FULL` commits to disk
  before a success response is sent (`storage.py`).

### What Is Not Implemented (Limitations)
This is deliberately a small custom scheme, **not** a consensus algorithm such as Raft or Paxos.
- No persistent replication log, log indexes, term-based voting (`RequestVote` / `AppendEntries`),
  or fencing tokens.
- No automatic catch-up on reconnect: `request_sync_from_peer()` exists but is not wired into
  startup or promotion.
- A revived old primary is not forced to step down through a formal protocol.
- Replication is **fail-open**: if the backup is unreachable, the primary logs `replication_failed`
  and still returns success, so cluster-wide durability is not guaranteed in that case.
- The arbiter is a plain TCP responder, not a stateful membership service.
- The correct way to describe this in the report: **primary–backup replication with heartbeat
  failure detection and witness-based quorum promotion**, not distributed consensus.

All of this lives in `cluster.py` (replication, heartbeat, promotion, sync) and `arbiter.py`
(witness), and is only active with `--cluster` / `CLUSTER=1`.

### Demo flow
```bash
CLUSTER=1 ./run.sh

# traffic
lxc exec client1 -- bash -c 'cd /opt/banking && python3 client.py --host 10.187.220.10 --port 5000'

# kill the primary
lxc exec server-a -- pkill -f server.py

# watch the backup take over
lxc exec server-b -- journalctl -u banking-server -n 30 --no-pager
curl --noproxy '*' http://10.187.220.20:8080/cluster
```

### Network partition / split brain
Cut the link between the servers while both keep running:
```bash
lxc exec server-a -- bash -c 'iptables -A INPUT -s 10.187.220.11 -j DROP; iptables -A OUTPUT -d 10.187.220.11 -j DROP'

# restore
lxc exec server-a -- bash -c 'iptables -F'
```
During the split the minority side must not accept writes; after the link returns, the backup
resynchronizes from the primary. See `cluster.py` for replication, promotion, and sync logic.

### Notes
- This mode is opt-in: without `CLUSTER=1` (or the `--cluster` flag) only the plain single-server code runs.
- The backup intentionally rejects client operations with `NOT_PRIMARY` until it is promoted, so
  you will not see mirrored reads on Server B before failover.
- The witness is required for promotion; without it the cluster stays safe but will not fail over.

## LXD VM Deployment

### 1. Install and initialize LXD
```bash
sudo snap install lxd
sudo lxd init
```

### 2. Launch VMs
```bash
lxc launch ubuntu:24.04 server-a --vm
lxc launch ubuntu:24.04 server-b --vm
lxc launch ubuntu:24.04 client1 --vm
lxc launch ubuntu:24.04 witness --vm
lxc list
```

### 3. Use actual bridge IPs
```bash
lxc network show lxdbr0
```
Use the subnet shown (for example, `10.187.220.0/24`).

### 4. Provision VMs
```bash
for vm in server-a server-b client1 witness; do
  lxc exec $vm -- bash -c 'apt update && apt install -y python3 python3-pip git python3-venv'
done
```

### 5. Copy project
```bash
cd /home/ah/dev/DS-Assignment1-Banking
tar czf /tmp/banking.tgz .
for vm in server-a server-b client1 witness; do
  lxc exec $vm -- mkdir -p /opt/banking
  lxc file push /tmp/banking.tgz $vm/tmp/banking.tgz
  lxc exec $vm -- tar xzf /tmp/banking.tgz -C /opt/banking
done
```

### 6. Open firewall ports
```bash
lxc exec server-a -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 8000/tcp; ufw allow 9000/tcp'
lxc exec server-b -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 8000/tcp; ufw allow 9000/tcp'
lxc exec witness -- bash -c 'ufw allow 8000/tcp'
```

### 7. Run services
```bash
lxc exec server-a -- bash -c 'cd /opt/banking && cp banking.conf.example banking.conf && python3 server.py --config banking.conf &'
lxc exec server-b -- bash -c 'cd /opt/banking && cp banking.conf.example banking.conf && python3 server.py --config banking.conf &'
lxc exec witness -- bash -c 'cd /opt/banking && python3 arbiter.py --host 0.0.0.0 --port 8000 &'
# log servers, one per banking node, so the web /logs page can read their logs
lxc exec server-a -- bash -c 'cd /opt/banking && python3 logserver.py --host 0.0.0.0 --port 9000 --log /opt/banking/logs/server.log &'
lxc exec server-b -- bash -c 'cd /opt/banking && python3 logserver.py --host 0.0.0.0 --port 9000 --log /opt/banking/logs/server.log &'
```

### 8. Run client
```bash
lxc exec client1 -- bash -c 'cd /opt/banking && python3 client.py --host <server-a-ip> --port 5000'
```

### 9. Run web UI
```bash
lxc exec client1 -- bash -c '
cd /opt/banking
curl -LsSf https://astral.sh/uv/install.sh | sh
source /root/.local/bin/env
uv venv .venv
uv pip install -r web/requirements.txt
source .venv/bin/activate
BANK_SERVERS=<server-a-ip>:5000,<server-b-ip>:5000 uvicorn web.app:app --host 0.0.0.0 --port 8080
'
```

Open:
```text
http://<client1-ip>:8080
```

## Automated Full Setup
```bash
./run.sh
```

Cluster mode:
```bash
CLUSTER=1 ./run.sh
```

Stop everything:
```bash
./stop.sh
```

## Git History
The project is organized into small commits for config, core storage, protocol/logging, server, client, tests, cluster, and documentation.
EOF
echo written
## Troubleshooting

### "502 Bad Gateway" when opening the web UI
This is usually an HTTP proxy on the host/browser intercepting the request to the LXD bridge subnet,
not a problem with the app. Bypass the proxy for the LXD network:

```bash
export no_proxy=localhost,127.0.0.1,10.187.220.0/24
export NO_PROXY=localhost,127.0.0.1,10.187.220.0/24
curl --noproxy '*' http://10.187.220.20:8080/
```

In a browser, add the LXD subnet (for example `10.187.220.0/24`) to the proxy bypass list.

### Web UI does not start
Check status and logs inside the client VM:
```bash
lxc exec client1 -- systemctl status banking-web --no-pager
lxc exec client1 -- journalctl -u banking-web -n 50 --no-pager
```

If dependencies are missing, reinstall:
```bash
lxc exec client1 -- bash -c 'cd /opt/banking && rm -rf .venv && uv venv .venv && uv pip install -r web/requirements.txt'
```

### Logs page is empty or shows "unreachable"
The `/logs` page reads each banking node's JSON log from its log server on port `9000`
(configured via `BANK_LOG_URLS`, otherwise derived from `BANK_SERVERS` host + `:9000`).
If every section says `unreachable`, the log servers are not running or not reachable:

```bash
lxc exec server-a -- systemctl status banking-log --no-pager
lxc exec server-a -- journalctl -u banking-log -n 30 --no-pager
lxc exec server-a -- bash -c 'curl -fsS http://127.0.0.1:9000/logs | tail'
```

Check that port `9000` is allowed in `ufw` on both server VMs and that the log path the log
server reads (`/opt/banking/logs/server.log`) matches `log_path` in `banking.conf`.
