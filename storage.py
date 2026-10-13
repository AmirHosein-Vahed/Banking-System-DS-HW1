import sqlite3, os, threading

class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=FULL;")
        self.conn.execute("PRAGMA busy_timeout=30000;")
        self._init_schema()
        self.seed_accounts()

    def _init_schema(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL CHECK (balance >= 0)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    req_id TEXT PRIMARY KEY,
                    account TEXT NOT NULL,
                    action TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                );
            """)
            self.conn.commit()

    def seed_accounts(self):
        seeds = {"A1001": 1000, "A1002": 500, "A1003": 2500,
                 "A1004": 0, "A1005": 10000}
        with self._lock:
            cur = self.conn.cursor()
            for acct, bal in seeds.items():
                cur.execute("INSERT OR IGNORE INTO accounts(account,balance) VALUES (?,?)", (acct, bal))
            self.conn.commit()

    def get_balance(self, account):
        with self._lock:
            row = self.conn.execute("SELECT balance FROM accounts WHERE account=?", (account,)).fetchone()
            return None if row is None else row[0]

    def exists(self, account):
        return self.get_balance(account) is not None

    def apply(self, req_id, account, action, amount):
        # returns (ok, balance_or_error, message)
        now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        with self._lock:
            # idempotency
            row = self.conn.execute("SELECT balance_after FROM transactions WHERE req_id=?", (req_id,)).fetchone()
            if row:
                # already applied; return current committed balance
                return True, row[0], "idempotent-replay"
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                r = cur.execute("SELECT balance FROM accounts WHERE account=?", (account,)).fetchone()
                if r is None:
                    raise ValueError("UNKNOWN_ACCOUNT")
                bal = r[0]
                if action == "deposit":
                    newbal = bal + amount
                elif action == "withdraw":
                    if amount > bal:
                        raise ValueError("INSUFFICIENT_FUNDS")
                    newbal = bal - amount
                elif action == "balance":
                    newbal = bal
                else:
                    raise ValueError("UNSUPPORTED_ACTION")
                if action in ("deposit", "withdraw"):
                    cur.execute("UPDATE accounts SET balance=? WHERE account=?", (newbal, account))
                    cur.execute("""INSERT INTO transactions(req_id,account,action,amount,balance_after,timestamp)
                                   VALUES (?,?,?,?,?,?)""", (req_id, account, action, amount, newbal, now))
                self.conn.commit()
                return True, newbal, "success"
            except Exception as e:
                self.conn.rollback()
                return False, None, str(e)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
