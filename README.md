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
| `banking.conf.example` | Sample configuration |
| `requirements.txt` | Core runtime/dependency notes |
| `tests/test_core.py` | Core, durability, and error tests |
| `tests/test_concurrency.py` | Concurrency and malformed-request tests |
| `tests/test_protocol.py` | Protocol validation tests |
| `tests/test_cluster.py` | Replication and failover smoke test |
| `tests/test_web_ui.py` | Web UI integration tests |
| `run.sh` | End-to-end LXD bootstrap and launch script |
| `stop.sh` | Stop services and VMs |
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

```bash
python3 -m unittest tests.test_core tests.test_concurrency tests.test_protocol tests.test_cluster -v
.venv/bin/python -m unittest tests.test_web_ui -v
```

## Cluster and Bonus Mode

### Server A (primary)
```bash
python3 server.py --config banking.conf --cluster --role primary --node-id A \
  --repl-port 6000 --peers <B-ip>:6000 --arbiter <witness-ip>:8000
```

### Server B (backup)
```bash
python3 server.py --config banking.conf --cluster --role backup --node-id B \
  --repl-port 6000 --peers <A-ip>:6000 --arbiter <witness-ip>:8000
```

### Witness
```bash
python3 arbiter.py --host 0.0.0.0 --port 8000
```

### Client with failover
```bash
python3 client.py --servers <A-ip>:5000,<B-ip>:5000
```

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
lxc exec server-a -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 8000/tcp'
lxc exec server-b -- bash -c 'ufw allow 5000/tcp; ufw allow 6000/tcp; ufw allow 8000/tcp'
lxc exec witness -- bash -c 'ufw allow 8000/tcp'
```

### 7. Run services
```bash
lxc exec server-a -- bash -c 'cd /opt/banking && cp banking.conf.example banking.conf && python3 server.py --config banking.conf &'
lxc exec server-b -- bash -c 'cd /opt/banking && cp banking.conf.example banking.conf && python3 server.py --config banking.conf &'
lxc exec witness -- bash -c 'cd /opt/banking && python3 arbiter.py --host 0.0.0.0 --port 8000 &'
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
