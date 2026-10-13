import socket, argparse, json, threading, time, uuid

def send(host, port, req):
    with socket.create_connection((host, port), timeout=10) as s:
        f = s.makefile("rwb")
        f.write((json.dumps(req)+"\n").encode()); f.flush()
        resp = f.readline()
        return json.loads(resp.decode())

def repl(host, port):
    print(f"Connected target {host}:{port}. Commands: balance/deposit/withdraw account amount")
    ridctr=0
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line: continue
        parts = line.split()
        if parts[0] in ("quit","exit"): break
        if len(parts) < 2:
            print("usage: <action> <account> [amount]")
            continue
        action = parts[0]; account = parts[1]
        amount = int(parts[2]) if len(parts) > 2 else 0
        req = {"req_id": uuid.uuid4().hex[:12], "action": action, "account": account, "amount": amount}
        try:
            print(send(host,port,req))
        except Exception as e:
            print("ERROR", e)

def stress(host, port, n):
    def worker(i):
        try:
            r = send(host,port,{"req_id":f"s{i}","action":"withdraw","account":"A1001","amount":10})
            print(i, r)
        except Exception as e:
            print(i, "ERR", e)
    ts=[threading.Thread(target=worker,args=(i,)) for i in range(n)]
    for t in ts: t.start()
    for t in ts: t.join()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--servers", default=None, help="comma list host:port for failover (not fully used yet)")
    ap.add_argument("--stress", type=int, default=0)
    args=ap.parse_args()
    if args.stress:
        stress(args.host, args.port, args.stress)
    else:
        repl(args.host, args.port)

if __name__=="__main__":
    main()
