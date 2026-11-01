import sqlite3
import struct
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
            db.execute("""CREATE TABLE IF NOT EXISTS memory_vectors (
                namespace TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                model_id TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY(namespace,memory_key,model_id)
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def put(self, namespace: str, key: str, value: str,
            embedding: list[float] | None = None, model_id: str | None = None) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO memories(namespace,memory_key,value) VALUES(?,?,?)
                ON CONFLICT(namespace,memory_key) DO UPDATE SET
                value=excluded.value, created_at=CURRENT_TIMESTAMP""",
                (namespace, key, value))
            db.execute("DELETE FROM memory_vectors WHERE namespace=? AND memory_key=?",
                       (namespace, key))
            if embedding is not None and model_id:
                if not embedding:
                    raise ValueError("Embedding vector cannot be empty")
                packed = struct.pack(f"<{len(embedding)}f", *[float(x) for x in embedding])
                db.execute("""INSERT INTO memory_vectors
                    (namespace,memory_key,model_id,dimension,vector) VALUES(?,?,?,?,?)""",
                    (namespace, key, model_id, len(embedding), packed))

    def search(self, namespace: str, query: str, limit: int = 5,
               query_embedding: list[float] | None = None,
               model_id: str | None = None) -> list[dict]:
        words = [w.lower() for w in query.split() if len(w) > 2]
        limit = max(1, min(int(limit), 20))
        with self._connect() as db:
            rows = db.execute("SELECT memory_key,value,created_at FROM memories WHERE namespace=?",
                              (namespace,)).fetchall()
        lexical = []
        for row in rows:
            text = f"{row['memory_key']} {row['value']}".lower()
            score = sum(text.count(word) for word in words)
            if score:
                lexical.append((score, dict(row)))
        lexical.sort(key=lambda entry: entry[0], reverse=True)
        fused = {}
        for rank, (_, item) in enumerate(lexical, 1):
            fused[item["memory_key"]] = {**item, "score": 1.0 / (60 + rank),
                                         "retrieval": "lexical"}
        if query_embedding and model_id:
            with self._connect() as db:
                vectors = db.execute("""SELECT v.memory_key,v.dimension,v.vector,m.value,m.created_at
                    FROM memory_vectors v JOIN memories m
                    ON m.namespace=v.namespace AND m.memory_key=v.memory_key
                    WHERE v.namespace=? AND v.model_id=?""", (namespace, model_id)).fetchall()
            semantic = []
            for row in vectors:
                dimension = int(row["dimension"])
                if dimension != len(query_embedding):
                    continue
                vector = struct.unpack(f"<{dimension}f", row["vector"])
                score = sum(float(a) * float(b) for a, b in zip(query_embedding, vector))
                semantic.append((score, dict(row)))
            semantic.sort(key=lambda entry: entry[0], reverse=True)
            for rank, (similarity, item) in enumerate(semantic[:limit * 3], 1):
                key = item["memory_key"]
                current = fused.setdefault(key, {
                    "memory_key": key, "value": item["value"],
                    "created_at": item["created_at"], "score": 0.0,
                    "retrieval": "semantic"
                })
                current["score"] += 1.0 / (60 + rank)
                if current["retrieval"] == "lexical":
                    current["retrieval"] = "hybrid"
                current["semantic_score"] = similarity
        return sorted(fused.values(), key=lambda item: item["score"], reverse=True)[:limit]
