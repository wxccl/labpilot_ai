import json
import sqlite3
from pathlib import Path

from labpilot_ai.utils.json_utils import to_jsonable


class LabPilotDatabase:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.init_schema()

    def init_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS optimization_sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS optimization_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                params TEXT NOT NULL,
                objective_value REAL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS error_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                user_text TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS code_change_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_log_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                log_date TEXT NOT NULL,
                output_format TEXT NOT NULL,
                path TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def log_event(self, kind: str, payload: dict):
        text = json.dumps(to_jsonable(payload), ensure_ascii=False)
        self.conn.execute("INSERT INTO events(kind, payload) VALUES(?, ?)", (kind, text))
        self.conn.commit()

    def upsert_optimization_session(self, session_id: str, status: str, payload: dict):
        text = json.dumps(to_jsonable(payload), ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO optimization_sessions(id, status, payload)
            VALUES(?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at=CURRENT_TIMESTAMP,
                status=excluded.status,
                payload=excluded.payload
            """,
            (str(session_id), str(status), text),
        )
        self.conn.commit()

    def log_optimization_point(self, session_id: str, iteration: int, status: str, params: dict, objective_value, payload: dict):
        params_text = json.dumps(to_jsonable(params or {}), ensure_ascii=False)
        payload_text = json.dumps(to_jsonable(payload), ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO optimization_points(session_id, iteration, status, params, objective_value, payload)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                str(session_id),
                int(iteration),
                str(status),
                params_text,
                None if objective_value is None else float(objective_value),
                payload_text,
            ),
        )
        self.conn.commit()

    def list_optimization_points(self, session_id: str):
        rows = self.conn.execute(
            "SELECT iteration, status, params, objective_value, payload FROM optimization_points WHERE session_id=? ORDER BY id",
            (str(session_id),),
        ).fetchall()
        return [
            {
                "iteration": row[0],
                "status": row[1],
                "params": json.loads(row[2]),
                "objective_value": row[3],
                "payload": json.loads(row[4]),
            }
            for row in rows
        ]

    def log_error_record(self, record: dict):
        payload = json.dumps(to_jsonable(record or {}), ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO error_records(kind, severity, title, message, payload)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                str((record or {}).get("kind", "ui")),
                str((record or {}).get("severity", "error")),
                str((record or {}).get("title", "")),
                str((record or {}).get("message", "")),
                payload,
            ),
        )
        self.conn.commit()

    def list_error_records(self, limit=100):
        rows = self.conn.execute(
            """
            SELECT created_at, kind, severity, title, message, payload
            FROM error_records
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [
            {
                "created_at": row[0],
                "kind": row[1],
                "severity": row[2],
                "title": row[3],
                "message": row[4],
                "payload": json.loads(row[5]),
            }
            for row in rows
        ]

    def log_command_record(self, status: str, user_text: str, payload: dict):
        text = json.dumps(to_jsonable(payload or {}), ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO command_records(status, user_text, payload) VALUES(?, ?, ?)",
            (str(status), str(user_text or ""), text),
        )
        self.conn.commit()

    def list_command_records(self, date_text=None, limit=500):
        where = ""
        params = []
        if date_text:
            where = "WHERE created_at LIKE ?"
            params.append(f"{date_text}%")
        params.append(int(limit))
        rows = self.conn.execute(
            f"""
            SELECT created_at, status, user_text, payload
            FROM command_records
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "created_at": row[0],
                "status": row[1],
                "user_text": row[2],
                "payload": json.loads(row[3]),
            }
            for row in rows
        ]

    def log_code_change_record(self, status: str, summary: str, payload: dict):
        text = json.dumps(to_jsonable(payload or {}), ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO code_change_records(status, summary, payload) VALUES(?, ?, ?)",
            (str(status), str(summary or ""), text),
        )
        self.conn.commit()

    def list_code_change_records(self, date_text=None, limit=500):
        where = ""
        params = []
        if date_text:
            where = "WHERE created_at LIKE ?"
            params.append(f"{date_text}%")
        params.append(int(limit))
        rows = self.conn.execute(
            f"""
            SELECT created_at, status, summary, payload
            FROM code_change_records
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "created_at": row[0],
                "status": row[1],
                "summary": row[2],
                "payload": json.loads(row[3]),
            }
            for row in rows
        ]

    def log_experiment_log_record(self, log_date: str, output_format: str, path: str, payload: dict):
        text = json.dumps(to_jsonable(payload or {}), ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO experiment_log_records(log_date, output_format, path, payload) VALUES(?, ?, ?, ?)",
            (str(log_date), str(output_format), str(path), text),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
