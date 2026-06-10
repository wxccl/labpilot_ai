import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TEXT_EXTENSIONS = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".ini", ".cfg", ".labscript"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS


@dataclass(frozen=True)
class SourceSpec:
    category: str
    path: Path
    recursive: bool = True


def resolve_project_path(path, project_dir=None):
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = Path(project_dir or Path.cwd()) / p
    return p


def project_db_path(settings, project_dir=None):
    default = "labpilot_outputs/knowledge/labpilot_knowledge.sqlite"
    return resolve_project_path((settings or {}).get("knowledge_db_path", default), project_dir=project_dir)


def discover_source_specs(settings, project_dir=None):
    settings = settings or {}
    specs = []
    mappings = [
        ("sequence", settings.get("sequence_dir"), True),
        ("sequence", settings.get("active_sequence_file"), False),
        ("connection_table", settings.get("connection_table"), False),
        ("connection_table", settings.get("active_connection_table"), False),
        ("single_lyse", settings.get("single_modules_dir"), True),
        ("multi_lyse", settings.get("multi_modules_dir"), True),
        ("labscript_source", settings.get("labscript_source_dir"), True),
        ("manual", settings.get("manual_dir"), True),
        ("paper", settings.get("paper_dir"), True),
    ]
    for category, raw_path, recursive in mappings:
        p = resolve_project_path(raw_path, project_dir=project_dir)
        if p:
            specs.append(SourceSpec(category, p, recursive=recursive))
    config_dir = Path(project_dir or Path.cwd()) / "configs"
    if config_dir.exists():
        specs.append(SourceSpec("registry", config_dir, recursive=True))
    return specs


def iter_supported_files(path, recursive=True):
    path = Path(path)
    if not path.exists():
        return
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path
        return
    iterator = path.rglob("*") if recursive else path.glob("*")
    for candidate in iterator:
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield candidate


def discover_source_files(settings, project_dir=None):
    seen = set()
    out = []
    for spec in discover_source_specs(settings, project_dir=project_dir):
        for path in iter_supported_files(spec.path, recursive=spec.recursive):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append({"category": spec.category, "path": resolved})
    return out


def source_counts(settings, project_dir=None):
    counts = {}
    for item in discover_source_files(settings, project_dir=project_dir):
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return counts


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_pdf_text(path):
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("PDF indexing requires labpilot-ai[docs] or `pip install pypdf`.") from exc
    reader = PdfReader(str(path))
    parts = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"[PDF page {index}]\n{text.strip()}")
    return "\n\n".join(parts)


def read_source_text(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return f"Image file: {path.name}\nPath: {path}\nNo OCR is performed in this version."
    if suffix in PDF_EXTENSIONS:
        return read_pdf_text(path)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def summarize_text(text, max_chars=220):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    summary = " ".join(lines[:4])
    return summary[:max_chars]


def chunk_text(text, chunk_chars=1200):
    lines = (text or "").splitlines()
    chunks = []
    current = []
    current_len = 0
    start_line = 1
    for line_no, line in enumerate(lines, start=1):
        line_len = len(line) + 1
        if current and current_len + line_len > chunk_chars:
            chunks.append((start_line, line_no - 1, "\n".join(current)))
            current = []
            current_len = 0
            start_line = line_no
        current.append(line)
        current_len += line_len
    if current:
        chunks.append((start_line, len(lines), "\n".join(current)))
    if not chunks and text:
        chunks.append((1, 1, text[:chunk_chars]))
    return chunks


class KnowledgeIndexer:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self, conn):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                category TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                summary TEXT NOT NULL,
                text TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(category, path, summary, text)
            """
        )
        conn.commit()

    def clear(self, conn):
        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM files")
        conn.commit()

    def index_project(self, settings, project_dir=None, rebuild=False, chunk_chars=1200):
        sources = discover_source_files(settings, project_dir=project_dir)
        stats = {"indexed": 0, "skipped": 0, "failed": 0, "discovered": len(sources), "db_path": str(self.db_path)}
        with self.connect() as conn:
            self.init_schema(conn)
            if rebuild:
                self.clear(conn)
            for item in sources:
                result = self.index_file(conn, item["path"], item["category"], chunk_chars=chunk_chars)
                stats[result] = stats.get(result, 0) + 1
            conn.commit()
        return stats

    def index_file(self, conn, path, category, chunk_chars=1200):
        path = Path(path)
        path_text = str(path)
        try:
            stat = path.stat()
            sha = file_sha256(path)
            existing = conn.execute("SELECT sha256, mtime, status FROM files WHERE path=?", (path_text,)).fetchone()
            if existing and existing["sha256"] == sha and float(existing["mtime"]) == float(stat.st_mtime):
                return "skipped"
            self._delete_file_chunks(conn, path_text)
            text = read_source_text(path)
            chunks = chunk_text(text, chunk_chars=chunk_chars)
            for index, (line_start, line_end, chunk) in enumerate(chunks):
                summary = summarize_text(chunk)
                cur = conn.execute(
                    """
                    INSERT INTO chunks(path, category, chunk_index, line_start, line_end, summary, text)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (path_text, category, index, line_start, line_end, summary, chunk),
                )
                chunk_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO chunks_fts(rowid, category, path, summary, text) VALUES(?, ?, ?, ?, ?)",
                    (chunk_id, category, path_text, summary, chunk),
                )
            conn.execute(
                """
                INSERT OR REPLACE INTO files(path, category, mtime, size, sha256, indexed_at, status, error)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (path_text, category, float(stat.st_mtime), int(stat.st_size), sha, datetime.now().isoformat(timespec="seconds"), "indexed", None),
            )
            return "indexed"
        except Exception as exc:
            self._delete_file_chunks(conn, path_text)
            try:
                stat = path.stat()
                sha = file_sha256(path) if path.exists() else ""
                size = int(stat.st_size)
                mtime = float(stat.st_mtime)
            except Exception:
                sha = ""
                size = 0
                mtime = 0.0
            conn.execute(
                """
                INSERT OR REPLACE INTO files(path, category, mtime, size, sha256, indexed_at, status, error)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (path_text, category, mtime, size, sha, datetime.now().isoformat(timespec="seconds"), "failed", repr(exc)),
            )
            return "failed"

    def _delete_file_chunks(self, conn, path_text):
        rows = conn.execute("SELECT id FROM chunks WHERE path=?", (path_text,)).fetchall()
        for row in rows:
            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (row["id"],))
        conn.execute("DELETE FROM chunks WHERE path=?", (path_text,))

    def list_files(self):
        with self.connect() as conn:
            self.init_schema(conn)
            rows = conn.execute("SELECT path, category, mtime, status, error FROM files ORDER BY category, path").fetchall()
            return [dict(row) for row in rows]

    def export_json(self):
        return json.dumps(self.list_files(), ensure_ascii=False, indent=2)
