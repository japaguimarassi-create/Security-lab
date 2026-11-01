import sqlite3
from pathlib import Path

class MemoryStore:
    def __init__(self, path: str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(namespace, memory_key)
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def put(self, namespace: str, key: str, value: str) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO memories(namespace,memory_key,value) VALUES(?,?,?)
                ON CONFLICT(namespace,memory_key) DO UPDATE SET value=excluded.value""",
                (namespace, key, value))

    def search(self, namespace: str, query: str, limit: int = 5) -> list[dict]:
        words = [w.lower() for w in query.split() if len(w) > 2]
        if not words:
            return []
        with self._connect() as db:
            rows = db.execute("SELECT memory_key,value,created_at FROM memories WHERE namespace=?",
                              (namespace,)).fetchall()
        ranked = []
        for row in rows:
            text = f"{row['memory_key']} {row['value']}".lower()
            score = sum(text.count(word) for word in words)
            if score:
                ranked.append((score, dict(row)))
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return [entry[1] for entry in ranked[:max(1, min(limit, 20))]]
