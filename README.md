# Mini Banking Transaction Server

Python TCP banking server/client for the DS Assignment 1 brief.

## Run single server

```bash
cp banking.conf.example banking.conf
python3 server.py --config banking.conf
```

Client (another VM/terminal):

```bash
python3 client.py --host <server-ip> --port 5000
```

Interactive commands:

```text
balance A1001
deposit A1001 100
withdraw A1001 50
```

Stress test:

```bash
python3 client.py --host <server-ip> --port 5000 --stress 50
```

## Tests

```bash
python3 -m unittest tests.test_core -v
```

## Cluster / fault-tolerant mode (bonus)

```bash
# Server A
python3 server.py --config banking.conf --cluster --role primary --node-id A \
  --repl-port 6000 --peers <B-ip>:6000 --arbiter <witness-ip>:8000

# Server B
python3 server.py --config banking.conf --cluster --role backup --node-id B \
  --repl-port 6000 --peers <A-ip>:6000 --arbiter <witness-ip>:8000

# Witness
python3 arbiter.py --host 0.0.0.0 --port 8000
```

Client failover:

```bash
python3 client.py --servers <A-ip>:5000,<B-ip>:5000
```

## Deployment
Client and server must run on separate VMs (e.g. LXD VMs with `--vm`). Use each server VM’s real bridge IP, not `localhost`.
