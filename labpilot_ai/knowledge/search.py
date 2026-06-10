import re
import sqlite3
from pathlib import Path

from labpilot_ai.knowledge.indexer import KnowledgeIndexer


def _terms(query, limit=8):
    terms = re.findall(r"[\w\u4e00-\u9fff]+", query or "")
    out = []
    for term in terms:
        if term not in out:
            out.append(term)
    return out[:limit]


def fts_query(query):
    terms = _terms(query)
    return " OR ".join(f'"{term}"' for term in terms)


def trim_snippet(text, max_chars=700):
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


class KnowledgeSearch:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def search(self, query, categories=None, limit=6, max_chars=700):
        if not query or not self.db_path.exists():
            return []
        categories = set(categories or [])
        match = fts_query(query)
        if not match:
            return []
        indexer = KnowledgeIndexer(self.db_path)
        with indexer.connect() as conn:
            indexer.init_schema(conn)
            try:
                rows = self._search_fts(conn, match, categories=categories, limit=limit)
            except sqlite3.Error:
                rows = self._search_like(conn, query, categories=categories, limit=limit)
        return [self._row_to_result(row, max_chars=max_chars) for row in rows]

    def _search_fts(self, conn, match, categories, limit):
        params = [match]
        category_clause = ""
        if categories:
            placeholders = ",".join("?" for _ in categories)
            category_clause = f" AND chunks.category IN ({placeholders})"
            params.extend(sorted(categories))
        params.append(int(limit))
        return conn.execute(
            f"""
            SELECT chunks.path, chunks.category, chunks.line_start, chunks.line_end,
                   chunks.summary, chunks.text, bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks ON chunks_fts.rowid = chunks.id
            WHERE chunks_fts MATCH ? {category_clause}
            ORDER BY score
            LIMIT ?
            """,
            params,
        ).fetchall()

    def _search_like(self, conn, query, categories, limit):
        params = [f"%{query}%"]
        category_clause = ""
        if categories:
            placeholders = ",".join("?" for _ in categories)
            category_clause = f" AND category IN ({placeholders})"
            params.extend(sorted(categories))
        params.append(int(limit))
        return conn.execute(
            f"""
            SELECT path, category, line_start, line_end, summary, text, 0.0 AS score
            FROM chunks
            WHERE text LIKE ? {category_clause}
            ORDER BY category, path, chunk_index
            LIMIT ?
            """,
            params,
        ).fetchall()

    def _row_to_result(self, row, max_chars=700):
        data = dict(row)
        return {
            "category": data["category"],
            "path": data["path"],
            "line_start": int(data["line_start"]),
            "line_end": int(data["line_end"]),
            "summary": data.get("summary", ""),
            "snippet": trim_snippet(data.get("text", ""), max_chars=max_chars),
            "score": float(data.get("score", 0.0) or 0.0),
        }
