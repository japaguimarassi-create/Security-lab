import hashlib
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_LICENSES = {
    "ODC-By-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0",
    "MIT", "Apache-2.0", "Public-Domain"
}

class KnowledgeStore:
    def __init__(self, path: str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
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
            try:
                db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                    USING fts5(doc_id UNINDEXED, title, body,
                    tokenize='unicode61 remove_diacritics 2')""")
                self._has_fts = True
            except sqlite3.OperationalError:
                self._has_fts = False

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
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

    def put(self, namespace: str, title: str, body: str, source_url: str,
            license_id: str, attribution: str) -> dict:
        self._validate_source(source_url, license_id, attribution)
        title = title.strip()
        body = body.strip()
        if not namespace.strip() or not title or len(body) < 80:
            raise ValueError("namespace/title are required and body must contain at least 80 characters")
        if len(body) > 100000:
            raise ValueError("body exceeds 100000 characters")
        digest = hashlib.sha256(body.casefold().encode("utf-8")).hexdigest()
        with self._connect() as db:
            existing = db.execute(
                "SELECT id FROM knowledge_docs WHERE namespace=? AND content_hash=?",
                (namespace, digest)
            ).fetchone()
            if existing:
                return {"id": existing["id"], "duplicate": True, "content_hash": digest}
            cursor = db.execute("""INSERT INTO knowledge_docs
                (namespace,title,body,source_url,license,attribution,content_hash)
                VALUES(?,?,?,?,?,?,?)""",
                (namespace, title, body, source_url, license_id, attribution, digest))
            doc_id = cursor.lastrowid
            if self._has_fts:
                db.execute("INSERT INTO knowledge_fts(doc_id,title,body) VALUES(?,?,?)",
                           (str(doc_id), title, body))
        return {"id": doc_id, "duplicate": False, "content_hash": digest}

    def search(self, namespace: str, query: str, limit: int = 5) -> list[dict]:
        terms = re.findall(r"[\wÀ-ÿ]{3,}", query.casefold())[:12]
        if not terms:
            return []
        limit = max(1, min(int(limit), 10))
        with self._connect() as db:
            if self._has_fts:
                match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                rows = db.execute("""SELECT d.id,d.title,d.body,d.source_url,d.license,
                    d.attribution,d.created_at,bm25(knowledge_fts) AS rank
                    FROM knowledge_fts f JOIN knowledge_docs d ON d.id=CAST(f.doc_id AS INTEGER)
                    WHERE knowledge_fts MATCH ? AND d.namespace=?
                    ORDER BY rank ASC LIMIT ?""", (match, namespace, limit)).fetchall()
            else:
                rows = db.execute("SELECT id,title,body,source_url,license,attribution,created_at "
                    "FROM knowledge_docs WHERE namespace=?", (namespace,)).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["body"] = item["body"][:1600]
            item.pop("rank", None)
            results.append(item)
        return results
