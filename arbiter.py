import socket, argparse, time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(16)
    print(f"Arbiter listening on {args.host}:{args.port}")
    while True:
        c,_ = srv.accept()
        threading = __import__("threading")
        def h(conn):
            try:
                conn.settimeout(5)
                while True:
                    d = conn.recv(1024)
                    if not d: break
                    conn.sendall(b"pong\n")
            except Exception:
                pass
            finally:
                try: conn.close()
                except: pass
        threading.Thread(target=h, args=(c,), daemon=True).start()

if __name__ == "__main__":
    main()
