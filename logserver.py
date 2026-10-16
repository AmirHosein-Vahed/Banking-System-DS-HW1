import argparse, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG_PATH = os.environ.get("BANK_LOG_PATH", "/opt/banking/logs/server.log")
TAIL = int(os.environ.get("BANK_LOG_TAIL", "200"))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") in ("", "/logs"):
            try:
                with open(LOG_PATH, "r", errors="replace") as f:
                    lines = f.readlines()[-TAIL:]
            except FileNotFoundError:
                lines = []
            except Exception as e:
                lines = [f"error reading log: {e}\n"]
            body = "".join(lines).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass

def main():
    global LOG_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--log", default=LOG_PATH)
    args = ap.parse_args()
    LOG_PATH = args.log
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Log server on {args.host}:{args.port} reading {LOG_PATH}")
    srv.serve_forever()

if __name__ == "__main__":
    main()
