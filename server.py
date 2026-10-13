import socket, threading, argparse, os, time, json, configparser
from storage import Storage
from accounts import AccountService
from protocol import parse_line, success_resp, error_resp
from logger import Logger
from cluster import Cluster

def load_config(path):
    cfg = configparser.ConfigParser()
    if path and os.path.exists(path):
        cfg.read(path)
    def get(key, env, default):
        if os.environ.get(env) is not None:
            return os.environ[env]
        try:
            return cfg.get("server", key)
        except Exception:
            return default
    return cfg, get

def client_thread(conn, addr, service, logger, max_clients_sem, cluster=None):
    ip = addr[0]
    start = time.time()
    # Note: semaphore already acquired by accept loop
    try:
        conn.settimeout(60)
        f = conn.makefile("rwb")
        while True:
            line = f.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            t0 = time.time()
            req_id = None
            try:
                ok, payload = parse_line(text)
                if not ok:
                    code, msg = payload
                    # no req_id known; use new
                    rid = None
                    # try extract req_id manually
                    try:
                        rid = json.loads(text).get("req_id")
                    except Exception:
                        rid = None
                    rid = rid or __import__("uuid").uuid4().hex[:12]
                    resp = error_resp(rid, code, msg)
                    # log
                    logger.log(req_id=rid, client_ip=ip, action="unknown", account="",
                               result="error", code=code, latency_ms=round((time.time()-t0)*1000,2))
                    f.write((json.dumps(resp)+"\n").encode()); f.flush()
                    # malformed/invalid: close connection? keep for more, but if random bytes maybe close
                    continue
                req = payload
                req_id = req["req_id"]
                # validate account existence handled in storage; but early for unknown
                if cluster is not None and not cluster.is_primary():
                    resp = error_resp(req["req_id"], "NOT_PRIMARY", "this node is not primary")
                    f.write((json.dumps(resp)+"\n").encode()); f.flush()
                    logger.log(req_id=req_id, client_ip=ip, action=req["action"], account=req["account"],
                               result="error", code="NOT_PRIMARY", latency_ms=round((time.time()-t0)*1000,2))
                    continue
                ok2, bal, msg = service.op(req_id, req["action"], req["account"], req["amount"])
                if ok2:
                    if cluster is not None and cluster.is_primary():
                        cluster.replicate(req, bal)
                    resp = success_resp(req, bal)
                    logger.log(req_id=req_id, client_ip=ip, action=req["action"], account=req["account"],
                               result="success", balance=bal, latency_ms=round((time.time()-t0)*1000,2))
                else:
                    # map internal error codes
                    code = msg if msg in ("UNKNOWN_ACCOUNT","INSUFFICIENT_FUNDS","UNSUPPORTED_ACTION") else "ERROR"
                    resp = error_resp(req_id, code, msg)
                    logger.log(req_id=req_id, client_ip=ip, action=req["action"], account=req["account"],
                               result="error", code=code, latency_ms=round((time.time()-t0)*1000,2))
                f.write((json.dumps(resp)+"\n").encode()); f.flush()
            except Exception as e:
                rid = req_id or __import__("uuid").uuid4().hex[:12]
                resp = error_resp(rid, "SERVER_ERROR", str(e))
                try:
                    f.write((json.dumps(resp)+"\n").encode()); f.flush()
                except Exception:
                    pass
                logger.log(req_id=rid, client_ip=ip, action="unknown", account="", result="error",
                           code="SERVER_ERROR", latency_ms=round((time.time()-t0)*1000,2))
                break
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="banking.conf")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--max-clients", type=int, default=None)
    ap.add_argument("--log", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--cluster", action="store_true")
    ap.add_argument("--role", default="primary", choices=["primary","backup"])
    ap.add_argument("--node-id", default="node")
    ap.add_argument("--repl-port", type=int, default=6000)
    ap.add_argument("--peers", default="", help="comma list host:port of other banking servers' repl ports")
    ap.add_argument("--arbiter", default=None, help="host:port of arbiter")
    args = ap.parse_args()

    cfg, get = load_config(args.config)
    host = args.host or get("host", "BANK_HOST", "0.0.0.0")
    port = args.port or int(get("port", "BANK_PORT", "5000"))
    max_clients = args.max_clients or int(get("max_clients", "BANK_MAX_CLIENTS", "10"))
    db_path = args.db or get("db_path", "BANK_DB", "data/bank.db")
    log_path = args.log or get("log_path", "BANK_LOG", "logs/server.log")

    storage = Storage(db_path)
    service = AccountService(storage)
    logger = Logger(log_path)

    cluster = None
    if args.cluster:
        peers = []
        for p in args.peers.split(","):
            p = p.strip()
            if not p: continue
            h, pt = p.rsplit(":", 1)
            peers.append((h, int(pt)))
        arbiter = None
        if args.arbiter:
            h,pt = args.arbiter.rsplit(":",1); arbiter = (h, int(pt))
        cluster = Cluster(args.node_id, args.role, ("0.0.0.0", args.repl_port), peers, arbiter, service, storage, logger)

    sem = threading.Semaphore(max_clients)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(128)
    print(f"Server listening on {host}:{port} (max_clients={max_clients})")

    try:
        while True:
            conn, addr = srv.accept()
            if not sem.acquire(blocking=False):
                # reject
                try:
                    conn.sendall((json.dumps({"status":"error","code":"BUSY","message":"max clients reached"})+"\n").encode())
                except Exception:
                    pass
                conn.close()
                continue
            def worker(c=conn, a=addr):
                try:
                    client_thread(c, a, service, logger, sem, cluster)
                finally:
                    sem.release()
            threading.Thread(target=worker, daemon=True).start()
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        storage.close()
        srv.close()

if __name__ == "__main__":
    main()
