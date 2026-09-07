"""Local task persistence. No cookies, passwords or automatic task execution."""
import json
import sqlite3
import threading
from pathlib import Path
from hashlib import sha256
from .config import AutoElectiveConfig


class TaskStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (account TEXT, id TEXT, data TEXT, PRIMARY KEY(account,id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS cache (account TEXT PRIMARY KEY, data TEXT)')
        self.db.commit()
        self.account_key = self.account()

    def account(self):
        cfg = AutoElectiveConfig()
        return sha256((cfg.iaaa_id + ':' + cfg.identity).encode()).hexdigest()

    def save(self, task):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?)',
                            (self.account_key, task['id'], json.dumps(task, ensure_ascii=False)))

    def delete(self, tid):
        with self.lock, self.db:
            self.db.execute('DELETE FROM tasks WHERE account=? AND id=?', (self.account_key, tid))

    def load(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute('SELECT data FROM tasks WHERE account=?', (self.account_key,))]

    def save_catalog(self, catalog):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)',
                            (self.account_key, json.dumps(catalog, ensure_ascii=False)))

    def load_catalog(self):
        with self.lock:
            row = self.db.execute('SELECT data FROM cache WHERE account=?', (self.account_key,)).fetchone()
            return json.loads(row[0]) if row else None
