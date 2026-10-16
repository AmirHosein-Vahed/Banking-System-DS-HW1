import os, sys, json, time, socket
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from storage import Storage

ACCOUNTS = ["A1001","A1002","A1003","A1004","A1005"]
WEB_ADMIN_PASSWORD = os.environ.get("WEB_ADMIN_PASSWORD", "admin")

def tcp_request(server: str, req: dict, timeout: float = 5.0):
    host, port = server.rsplit(":", 1)
    port = int(port)
    with socket.create_connection((host, port), timeout=timeout) as s:
        f = s.makefile("rwb")
        f.write((json.dumps(req) + "\n").encode())
        f.flush()
        line = f.readline()
        if not line:
            raise RuntimeError("no response")
        return json.loads(line.decode())

app = FastAPI(title="Banking Web Frontend")
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))
static_dir = os.path.join(base_dir, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

SERVERS = [s for s in os.environ.get("BANK_SERVERS", "127.0.0.1:5000").split(",") if s.strip()]

def primary():
    return SERVERS[0]

def try_servers(req):
    last = None
    for srv in SERVERS:
        try:
            return srv, tcp_request(srv, req)
        except Exception as e:
            last = e
    raise RuntimeError(f"all servers failed: {last}")

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    balances = {}
    for a in ACCOUNTS:
        try:
            srv, resp = try_servers({"req_id": "web", "action": "balance", "account": a, "amount": 0})
            balances[a] = resp.get("balance")
        except Exception as e:
            balances[a] = "err"
    return templates.TemplateResponse(request, "index.html", {"balances": balances, "servers": SERVERS})

@app.post("/ops")
def ops(request: Request, action: str = Form(...), account: str = Form(...), amount: int = Form(0), server: str = Form(None)):
    target = server or primary()
    req = {"req_id": "web-" + str(int(time.time()*1000)), "action": action, "account": account, "amount": amount}
    try:
        resp = tcp_request(target, req)
    except Exception as e:
        resp = {"status": "error", "code": "CONNECT_ERROR", "message": str(e)}
    return templates.TemplateResponse(request, "ops.html", {"resp": resp, "servers": SERVERS, "default_server": target})

@app.get("/ops", response_class=HTMLResponse)
def ops_form(request: Request):
    return templates.TemplateResponse(request, "ops.html", {"resp": None, "servers": SERVERS, "default_server": primary()})

@app.post("/stress")
def stress(request: Request, n: int = Form(10), amount: int = Form(10), account: str = Form("A1001"), server: str = Form(None)):
    target = server or primary()
    import concurrent.futures
    results = []
    def one(i):
        try:
            r = tcp_request(target, {"req_id": f"web-stress-{i}", "action": "withdraw", "account": account, "amount": amount})
            return r.get("status")
        except Exception as e:
            return "error"
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 64)) as ex:
        futs = [ex.submit(one, i) for i in range(n)]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())
    summary = {s: results.count(s) for s in set(results)}
    return templates.TemplateResponse(request, "stress.html", {"summary": summary, "n": n, "account": account, "amount": amount, "servers": SERVERS})

@app.get("/stress", response_class=HTMLResponse)
def stress_form(request: Request):
    return templates.TemplateResponse(request, "stress.html", {"summary": None, "n": 10, "account": "A1001", "amount": 10, "servers": SERVERS})

def log_urls():
    explicit = os.environ.get("BANK_LOG_URLS")
    if explicit:
        return [u.strip() for u in explicit.split(",") if u.strip()]
    urls = []
    for srv in SERVERS:
        host = srv.rsplit(":", 1)[0]
        urls.append(f"http://{host}:9000/logs")
    return urls

@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request, node: str = None):
    import urllib.request
    sections = []
    for url in log_urls():
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                text = r.read().decode(errors="replace")
            sections.append((url, text.splitlines()[-200:]))
        except Exception as e:
            sections.append((url, [f"unreachable: {e}"]))
    # fallback to a local file only if nothing remote is configured/available
    if not sections:
        try:
            with open(os.environ.get("BANK_LOG_PATH", "logs/server.log"), errors="replace") as f:
                sections.append(("local", f.readlines()[-200:]))
        except Exception:
            sections.append(("local", ["no logs available"]))
    return templates.TemplateResponse(request, "logs.html", {"sections": sections})


@app.get("/cluster", response_class=HTMLResponse)
def cluster(request: Request):
    # Basic reachability info
    info = {}
    for srv in SERVERS:
        try:
            r = tcp_request(srv, {"req_id": "web", "action": "balance", "account": "A1001", "amount": 0})
            info[srv] = {"reachable": True, "sample_balance": r.get("balance")}
        except Exception as e:
            info[srv] = {"reachable": False, "error": str(e)}
    return templates.TemplateResponse(request, "cluster.html", {"info": info, "servers": SERVERS})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "8080")), reload=True)
