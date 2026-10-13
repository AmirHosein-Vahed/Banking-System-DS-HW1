import subprocess, time, urllib.request, urllib.parse, os, tempfile, shutil, unittest, socket

class TestWebUI(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        # banking config
        self.conf = os.path.join(self.d, "b.conf")
        open(self.conf, "w").write(
            f"[server]\nhost=127.0.0.1\nport=5210\nmax_clients=10\ndb_path={self.d}/b.db\nlog_path={self.d}/b.log\n"
        )
        self.bank = subprocess.Popen(
            ["python3", "server.py", "--config", self.conf],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        env = dict(os.environ)
        env["BANK_SERVERS"] = "127.0.0.1:5210"
        env["BANK_LOG_PATH"] = f"{self.d}/b.log"
        self.web = subprocess.Popen(
            [os.path.join(os.getcwd(), ".venv", "bin", "python"), "-m", "uvicorn", "web.app:app",
             "--host", "127.0.0.1", "--port", "8220"],
            cwd=os.getcwd(), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # wait
        for _ in range(30):
            try:
                urllib.request.urlopen("http://127.0.0.1:8220/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)

    def tearDown(self):
        for p in (self.web, self.bank):
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()
        shutil.rmtree(self.d, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen("http://127.0.0.1:8220" + path, timeout=10) as r:
            return r.status, r.read().decode()

    def test_pages_render(self):
        for path in ["/", "/ops", "/stress", "/logs", "/cluster"]:
            status, html = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn("<html", html)
            self.assertIn("Dashboard" if path == "/" else path.lstrip("/").capitalize() or "", html.lower() if False else html)

    def test_ops_submit(self):
        data = urllib.parse.urlencode({"action": "balance", "account": "A1001", "amount": "0"}).encode()
        req = urllib.request.Request("http://127.0.0.1:8220/ops", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode()
            self.assertIn("success", html)
            self.assertIn("A1001", html)

if __name__ == "__main__":
    unittest.main()
