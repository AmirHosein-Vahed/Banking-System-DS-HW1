import json, time, os, threading

class Logger:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()

    def log(self, **fields):
        entry = {"ts": datetime_now(), **fields}
        line = json.dumps(entry)
        with self._lock:
            with open(self.path, "a") as f:
                f.write(line + "\n")
        print(line)

def datetime_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
