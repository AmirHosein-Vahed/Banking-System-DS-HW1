import socket, json, time, os, tempfile, shutil, subprocess, threading, unittest

class TestConcurrency(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.conf = os.path.join(self.d, "c.conf")
        open(self.conf, "w").write(f"[server]\nhost=127.0.0.1\nport=5299\nmax_clients=50\ndb_path={self.d}/c.db\nlog_path={self.d}/c.log\n")
        self.proc = subprocess.Popen(["python3", "server.py", "--config", self.conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

    def tearDown(self):
        self.proc.terminate(); self.proc.wait()
        shutil.rmtree(self.d, ignore_errors=True)

    def send(self, req):
        with socket.create_connection(("127.0.0.1", 5299), timeout=10) as s:
            f = s.makefile("rwb")
            f.write((json.dumps(req) + "\n").encode()); f.flush()
            return json.loads(f.readline().decode())

    def test_concurrent_withdrawals(self):
        # reset-ish: A1001 starts 1000 in seed; withdraw 10, 50 threads
        results = []
        def worker(i):
            try:
                r = self.send({"req_id": f"cw{i}", "action": "withdraw", "account": "A1001", "amount": 10})
                results.append(r)
            except Exception as e:
                results.append({"status": "error", "message": str(e)})
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in ts: t.start()
        for t in ts: t.join()
        succ = [r for r in results if r.get("status") == "success"]
        self.assertGreaterEqual(len(succ), 49)
        # final
        final = self.send({"req_id": "fin", "action": "balance", "account": "A1001"})["balance"]
        self.assertGreaterEqual(final, 0)
        # 1000 - (num_success*10) expected approx
        self.assertEqual(final, 1000 - len(succ) * 10)

    def test_malformed_random_bytes(self):
        with socket.create_connection(("127.0.0.1", 5299), timeout=5) as s:
            s.sendall(b"this is not json\n")
            data = s.recv(4096)
            self.assertIn(b"error", data)
        # server still alive
        r = self.send({"req_id": "after", "action": "balance", "account": "A1001"})
        self.assertEqual(r["status"], "success")

if __name__ == "__main__":
    unittest.main()
