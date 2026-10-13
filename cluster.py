import socket, threading, json, time, argparse, os

class Cluster:
    def __init__(self, node_id, role, self_repl_addr, peers, arbiter, service, storage, logger):
        self.node_id = node_id
        self.role = role  # "primary" or "backup"
        self.self_addr = self_repl_addr
        self.peers = peers  # list of (host,port) for other banking servers (replication)
        self.arbiter = arbiter  # (host,port) or None
        self.service = service
        self.storage = storage
        self.logger = logger
        self.term = 0
        self.last_heartbeat = time.time()
        self._stop = False
        # start replication listener
        threading.Thread(target=self._listen_repl, daemon=True).start()
        if role == "backup":
            threading.Thread(target=self._monitor, daemon=True).start()
        if role == "primary":
            threading.Thread(target=self._heartbeat, daemon=True).start()

    def is_primary(self):
        return self.role == "primary"

    def _listen_repl(self):
        host, port = self.self_addr
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port)); srv.listen(16)
        while not self._stop:
            try:
                c, _ = srv.accept()
            except Exception:
                continue
            threading.Thread(target=self._handle_repl_conn, args=(c,), daemon=True).start()

    def _handle_repl_conn(self, conn):
        try:
            f = conn.makefile("rwb")
            while True:
                line = f.readline()
                if not line: break
                msg = json.loads(line.decode())
                if msg.get("type") == "ping":
                    # heartbeat from primary
                    self.term = max(self.term, msg.get("term", 0))
                    self.last_heartbeat = time.time()
                    f.write((json.dumps({"type":"pong"})+"\n").encode()); f.flush()
                elif msg.get("type") == "replicate":
                    tx = msg["tx"]
                    self.service.op(tx["req_id"], tx["action"], tx["account"], tx["amount"])
                    f.write((json.dumps({"type":"ack","req_id":tx["req_id"]})+"\n").encode()); f.flush()
                elif msg.get("type") == "sync_request":
                    # send full balances snapshot
                    snap = {}
                    for acct in ["A1001","A1002","A1003","A1004","A1005"]:
                        b = self.storage.get_balance(acct)
                        if b is not None: snap[acct]=b
                    f.write((json.dumps({"type":"snapshot","balances":snap})+"\n").encode()); f.flush()
                elif msg.get("type") == "sync_apply":
                    for acct,bal in msg["balances"].items():
                        # force update
                        if self.storage.exists(acct):
                            with self.storage._lock:
                                self.storage.conn.execute("UPDATE accounts SET balance=? WHERE account=?",(bal,acct))
                                self.storage.conn.commit()
                            if not hasattr(self.storage,'_mem'): pass
                else:
                    pass
        except Exception:
            pass
        finally:
            try: conn.close()
            except: pass

    def replicate(self, req, balance):
        # primary calls after local commit
        if self.role != "primary": return True
        for host, port in self.peers:
            try:
                with socket.create_connection((host, port), timeout=5) as s:
                    f = s.makefile("rwb")
                    tx = {"req_id":req["req_id"],"action":req["action"],"account":req["account"],"amount":req["amount"]}
                    f.write((json.dumps({"type":"replicate","tx":tx})+"\n").encode()); f.flush()
                    line = f.readline()
                    if not line:
                        raise RuntimeError("no ack")
                    ack = json.loads(line.decode())
                    if ack.get("type") != "ack":
                        raise RuntimeError("bad ack")
            except Exception as e:
                if self.logger:
                    self.logger.log(component="cluster", event="replication_failed", peer=f"{host}:{port}", error=str(e))
                # fail-open for demo; mark degraded
                return False
        return True

    def _heartbeat(self):
        while not self._stop and self.role == "primary":
            for host, port in self.peers:
                try:
                    with socket.create_connection((host, port), timeout=2) as s:
                        f = s.makefile("rwb")
                        self.term += 0  # keep term
                        f.write((json.dumps({"type":"ping","term":self.term})+"\n").encode()); f.flush()
                        f.readline()
                except Exception:
                    pass
            # arbiter heartbeat too
            if self.arbiter:
                try:
                    host,port = self.arbiter
                    with socket.create_connection((host,port), timeout=2) as s:
                        pass
                except Exception:
                    pass
            time.sleep(1)

    def _monitor(self):
        while not self._stop:
            time.sleep(1)
            if self.role != "backup": continue
            if time.time() - self.last_heartbeat > 5:
                # check arbiter reachability
                arb_ok = True
                if self.arbiter:
                    try:
                        host,port = self.arbiter
                        with socket.create_connection((host,port), timeout=2):
                            pass
                    except Exception:
                        arb_ok = False
                if arb_ok:
                    # promote
                    self.role = "primary"
                    if self.logger:
                        self.logger.log(component="cluster", event="promoted", node=self.node_id)
                    # sync from? new primary already has replicated state
                    # start heartbeat
                    threading.Thread(target=self._heartbeat, daemon=True).start()
                self.last_heartbeat = time.time()  # avoid tight loop

    def request_sync_from_peer(self, host, port):
        try:
            with socket.create_connection((host,port), timeout=5) as s:
                f = s.makefile("rwb")
                f.write((json.dumps({"type":"sync_request"})+"\n").encode()); f.flush()
                line = f.readline()
                if line:
                    msg = json.loads(line.decode())
                    if msg.get("type")=="snapshot":
                        # apply
                        for acct,bal in msg["balances"].items():
                            if self.storage.exists(acct):
                                with self.storage._lock:
                                    self.storage.conn.execute("UPDATE accounts SET balance=? WHERE account=?",(bal,acct))
                                    self.storage.conn.commit()
        except Exception as e:
            if self.logger: self.logger.log(component="cluster", event="sync_failed", error=str(e))

def parse_peer(s):
    host, port = s.rsplit(":",1)
    return (host, int(port))
