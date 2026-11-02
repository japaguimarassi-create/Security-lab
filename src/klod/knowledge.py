import hashlib
import re
import sqlite3

from klod.db import connect, prepare_database_path
import struct
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_LICENSES = {
    "ODC-By-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0",
    "MIT", "Apache-2.0", "Public-Domain"
}

class KnowledgeStore:
    def __init__(self, path: str):
        self.path = str(path)
        prepare_database_path(self.path)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS knowledge_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                source_url TEXT NOT NULL,
                license TEXT NOT NULL,
                attribution TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(namespace, content_hash)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS knowledge_vectors (
                doc_id INTEGER NOT NULL,
                passage_index INTEGER NOT NULL,
                model_id TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                passage TEXT NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY(doc_id, passage_index, model_id),
                FOREIGN KEY(doc_id) REFERENCES knowledge_docs(id) ON DELETE CASCADE
            )""")
            try:
                db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                    USING fts5(doc_id UNINDEXED, title, body,
                    tokenize='unicode61 remove_diacritics 2')""")
                self._has_fts = True
            except sqlite3.OperationalError:
                self._has_fts = False

    def _connect(self):
        connection = connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _validate_source(source_url: str, license_id: str, attribution: str) -> None:
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTPS URL")
        if license_id not in ALLOWED_LICENSES:
            raise ValueError(f"Unsupported or unverified license: {license_id}")
        if not attribution.strip():
            raise ValueError("Attribution is required")

    @staticmethod
    def split_passages(title: str, body: str, max_chars: int = 1800,
                       overlap: int = 180) -> list[str]:
        if max_chars < 300 or overlap < 0 or overlap >= max_chars:
            raise ValueError("Invalid passage chunking configuration")
        text = f"{title.strip()}\n\n{body.strip()}"
        passages, start = [], 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):
                boundary = text.rfind(" ", start + max_chars // 2, end)
                if boundary > start:
                    end = boundary
            passage = text[start:end].strip()
            if passage:
                passages.append(passage)
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
        return passages

    def put(self, namespace: str, title: str, body: str, source_url: str,
            license_id: str, attribution: str) -> dict:
        self._validate_source(source_url, license_id, attribution)
        title, body = title.strip(), body.strip()
        if not namespace.strip() or not title or len(body) < 80:
            raise ValueError("namespace/title are required and body must contain at least 80 characters")
        if len(body) > 100000:
            raise ValueError("body exceeds 100000 characters")
        digest = hashlib.sha256(body.casefold().encode("utf-8")).hexdigest()
        with self._connect() as db:
            existing = db.execute(
                "SELECT id FROM knowledge_docs WHERE namespace=? AND content_hash=?",
                (namespace, digest)).fetchone()
            if existing:
                return {"id": existing["id"], "duplicate": True, "content_hash": digest}
            cursor = db.execute("""INSERT INTO knowledge_docs
                (namespace,title,body,source_url,license,attribution,content_hash)
                VALUES(?,?,?,?,?,?,?) RETURNING id""",
                (namespace, title, body, source_url, license_id, attribution, digest))
            doc_id = cursor.fetchone()["id"]
            if self._has_fts:
                db.execute("INSERT INTO knowledge_fts(doc_id,title,body) VALUES(?,?,?)",
                           (str(doc_id), title, body))
        return {"id": doc_id, "duplicate": False, "content_hash": digest}

    def documents_to_index(self, namespace: str, model_id: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as db:
            rows = db.execute("""SELECT d.id,d.title,d.body FROM knowledge_docs d
                WHERE d.namespace=? AND NOT EXISTS (
                    SELECT 1 FROM knowledge_vectors v
                    WHERE v.doc_id=d.id AND v.model_id=?)
                ORDER BY d.id LIMIT ?""", (namespace, model_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def save_vectors(self, doc_id: int, model_id: str, passages: list[str],
                     vectors: list[list[float]]) -> int:
        if len(passages) != len(vectors) or not passages:
            raise ValueError("Passages and embedding vectors must have equal nonzero lengths")
        dimension = len(vectors[0])
        if dimension < 1 or any(len(vector) != dimension for vector in vectors):
            raise ValueError("Embedding dimensions are inconsistent")
        records = []
        for index, (passage, vector) in enumerate(zip(passages, vectors)):
            packed = struct.pack(f"<{dimension}f", *[float(value) for value in vector])
            records.append((doc_id, index, model_id, dimension, passage, packed))
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM knowledge_docs WHERE id=?", (doc_id,)).fetchone():
                raise ValueError(f"Unknown knowledge document id: {doc_id}")
            db.execute("DELETE FROM knowledge_vectors WHERE doc_id=? AND model_id=?",
                       (doc_id, model_id))
            db.executemany("""INSERT INTO knowledge_vectors
                (doc_id,passage_index,model_id,dimension,passage,vector)
                VALUES(?,?,?,?,?,?)""", records)
        return len(records)

    def _lexical_search(self, namespace: str, query: str, limit: int) -> list[dict]:
        terms = re.findall(r"[\wÀ-ÿ]{3,}", query.casefold())[:12]
        if not terms:
            return []
        with self._connect() as db:
            if self._has_fts:
                match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                rows = db.execute("""SELECT d.id,d.title,d.body,d.source_url,d.license,
                    d.attribution,d.created_at,bm25(knowledge_fts) AS rank
                    FROM knowledge_fts f JOIN knowledge_docs d ON d.id=CAST(f.doc_id AS INTEGER)
                    WHERE knowledge_fts MATCH ? AND d.namespace=?
                    ORDER BY rank ASC LIMIT ?""", (match, namespace, limit)).fetchall()
            else:
                rows = db.execute("""SELECT id,title,body,source_url,license,attribution,created_at
                    FROM knowledge_docs WHERE namespace=?""", (namespace,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            searchable = (item["title"] + " " + item["body"]).casefold()
            score = sum(searchable.count(term) for term in terms)
            if score:
                item["body"] = item["body"][:1600]
                item["passage"] = item["body"]
                item["lexical_score"] = score
                result.append(item)
        result.sort(key=lambda item: item["lexical_score"], reverse=True)
        return result[:limit]

    def search(self, namespace: str, query: str, limit: int = 5) -> list[dict]:
        return self._lexical_search(namespace, query, max(1, min(int(limit), 10)))

    def search_hybrid(self, namespace: str, query: str, query_vector: list[float] | None,
                      model_id: str, limit: int = 5) -> list[dict]:
        limit = max(1, min(int(limit), 10))
        lexical = self._lexical_search(namespace, query, limit * 4)
        semantic = []
        if query_vector:
            with self._connect() as db:
                rows = db.execute("""SELECT d.id,d.title,d.body,d.source_url,d.license,
                    d.attribution,d.created_at,v.dimension,v.passage,v.vector
                    FROM knowledge_vectors v JOIN knowledge_docs d ON d.id=v.doc_id
                    WHERE d.namespace=? AND v.model_id=?""",
                    (namespace, model_id)).fetchall()
            best_by_doc = {}
            for row in rows:
                dimension = int(row["dimension"])
                if dimension != len(query_vector):
                    continue
                vector = struct.unpack(f"<{dimension}f", row["vector"])
                score = sum(float(a) * float(b) for a, b in zip(query_vector, vector))
                key = int(row["id"])
                if key not in best_by_doc or score > best_by_doc[key]["semantic_score"]:
                    best_by_doc[key] = {**dict(row), "semantic_score": score}
            semantic = sorted(best_by_doc.values(),
                              key=lambda item: item["semantic_score"], reverse=True)[:limit * 4]

        fused = {}
        lexical_ids = {int(item["id"]) for item in lexical}
        for rank, item in enumerate(lexical, 1):
            key = int(item["id"])
            fused[key] = {**item, "hybrid_score": 1.0 / (60 + rank),
                          "retrieval": "lexical"}
        for rank, item in enumerate(semantic, 1):
            key = int(item["id"])
            current = fused.setdefault(key, {**item, "hybrid_score": 0.0})
            current["hybrid_score"] += 1.0 / (60 + rank)
            current["retrieval"] = "hybrid" if key in lexical_ids else "semantic"
            current["semantic_score"] = item["semantic_score"]
            current["passage"] = item["passage"]
        results = sorted(fused.values(), key=lambda item: item["hybrid_score"],
                         reverse=True)[:limit]
        for item in results:
            item["body"] = item.get("passage", item["body"][:1600])
            item.pop("vector", None)
            item.pop("dimension", None)
            item.pop("rank", None)
        return results
