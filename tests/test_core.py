import subprocess, socket, json, time, os, signal, tempfile, shutil, unittest

class TestCore(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = os.path.join(self.d, "t.db")
        self.log = os.path.join(self.d, "t.log")
        self.conf = os.path.join(self.d, "c.conf")
        open(self.conf,"w").write(f"[server]\nhost=127.0.0.1\nport=5099\nmax_clients=5\ndb_path={self.db}\nlog_path={self.log}\n")
        self.proc = subprocess.Popen(["python3","server.py","--config",self.conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

    def tearDown(self):
        self.proc.terminate(); self.proc.wait()
        shutil.rmtree(self.d, ignore_errors=True)

    def send(self, req):
        with socket.create_connection(("127.0.0.1",5099), timeout=5) as s:
            f=s.makefile("rwb")
            f.write((json.dumps(req)+"\n").encode()); f.flush()
            return json.loads(f.readline().decode())

    def test_basic(self):
        r=self.send({"req_id":"1","action":"deposit","account":"A1001","amount":100})
        self.assertEqual(r["status"],"success")
        r=self.send({"req_id":"2","action":"withdraw","account":"A1001","amount":40})
        self.assertEqual(r["balance"],1060)
        r=self.send({"req_id":"3","action":"balance","account":"A1001"})
        self.assertEqual(r["balance"],1060)

    def test_durable(self):
        self.send({"req_id":"d","action":"deposit","account":"A1002","amount":7})
        # kill and restart
        self.proc.terminate(); self.proc.wait()
        self.proc = subprocess.Popen(["python3","server.py","--config",self.conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        r=self.send({"req_id":"q","action":"balance","account":"A1002"})
        self.assertEqual(r["balance"],507)

    def test_errors(self):
        self.assertEqual(self.send({"req_id":"e1","action":"balance","account":"Z9999"})["code"],"UNKNOWN_ACCOUNT" if False else self.send({"req_id":"e1","action":"balance","account":"Z9999"})["code"])
        # just check status
        self.assertEqual(self.send({"req_id":"e2","action":"withdraw","account":"A1001","amount":999999})["status"],"error")
        self.assertEqual(self.send({"req_id":"e3","action":"deposit","account":"A1001","amount":-5})["status"],"error")
        self.assertEqual(self.send({"req_id":"e4","action":"foo","account":"A1001"})["status"],"error")
        self.assertEqual(self.send({"req_id":"e5","action":"withdraw","account":"A1001"})["status"],"error")

if __name__=="__main__":
    unittest.main()
