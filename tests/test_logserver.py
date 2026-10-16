import os, socket, subprocess, sys, tempfile, time, unittest, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestLogServer(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.log = os.path.join(self.d, "server.log")
        self.port = free_port()
        # logserver.py must at least start cleanly (it used to fail with a SyntaxError)
        self.proc = subprocess.Popen(
            [sys.executable, "logserver.py", "--host", "127.0.0.1",
             "--port", str(self.port), "--log", self.log],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.url = f"http://127.0.0.1:{self.port}/logs"
        for _ in range(40):
            if self.proc.poll() is not None:
                self.fail("logserver.py exited during startup (crashed?)")
            try:
                urllib.request.urlopen(self.url, timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            self.fail("logserver.py did not start listening")

    def tearDown(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    def test_serves_log_lines(self):
        line = '{"action": "deposit", "account": "A1001", "result": "success"}\n'
        with open(self.log, "a") as f:
            f.write(line)
        with urllib.request.urlopen(self.url, timeout=5) as r:
            body = r.read().decode()
        self.assertIn('"deposit"', body)
        self.assertIn("A1001", body)

    def test_missing_log_file_returns_empty(self):
        with urllib.request.urlopen(self.url, timeout=5) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.read().decode(), "")


if __name__ == "__main__":
    unittest.main()
