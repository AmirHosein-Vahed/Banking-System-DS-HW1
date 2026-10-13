import threading, time

class LockManager:
    def __init__(self):
        self._global = threading.Lock()
        self._locks = {}

    def acquire(self, *accounts):
        uniq = sorted(set(accounts))
        # acquire global briefly to get per-account locks
        with self._global:
            ls = [self._locks.setdefault(a, threading.Lock()) for a in uniq]
        acquired = []
        for lk in ls:
            lk.acquire()
            acquired.append(lk)
        return acquired

    def release_all(self, acquired):
        for lk in reversed(acquired):
            lk.release()

class AccountService:
    def __init__(self, storage):
        self.storage = storage
        self.locks = LockManager()

    def op(self, req_id, action, account, amount):
        lk = self.locks.acquire(account)
        try:
            ok, bal, msg = self.storage.apply(req_id, account, action, amount)
            return ok, bal, msg
        finally:
            self.locks.release_all(lk)
