"""Profile, validation, and durable request receipts for the packaged host."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3


MAX_BYTES = 4 * 1024 * 1024
RESULT_SCHEMA = "labpilot-host-result/1"
RUN_ACTIONS = {"set_globals", "set_sequence", "set_output", "set_flags", "engage"}


class Refused(ValueError):
    """A checked pre-effect refusal."""


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise Refused(f"Duplicate JSON field: {name}")
        result[name] = value
    return result


def _constant(value):
    raise Refused(f"Invalid JSON number: {value}")


def loads(raw):
    if len(raw) > MAX_BYTES:
        raise Refused("JSON message exceeds the size limit")
    result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    canonical(result)  # Reject overflowed floats as well as literal NaN/Infinity.
    return result


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def snapshot(value):
    return {**value, "snapshot_sha256": digest(value)}


def receipt(state, *, value=None, reason=None, request_id=None):
    result = {"schema": RESULT_SCHEMA, "state": state}
    if value is not None:
        result["value"] = value
    if reason is not None:
        result["reason"] = reason
    if request_id is not None:
        result["request_id"] = request_id
    if state == "UNKNOWN":
        result["no_automatic_retry"] = True
    return result


def request_id(params):
    value = params.get("request_id")
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise Refused("A request_id of 1 to 80 letters, digits, underscores or hyphens is required")
    return value


def require_snapshot(params, observed):
    if params.get("expected_snapshot_sha256") != observed["snapshot_sha256"]:
        raise Refused("Snapshot changed. Prepare a new request from a fresh observation.")


def read_json(path):
    with Path(path).open("rb") as stream:
        return loads(stream.read(MAX_BYTES + 1).decode("utf-8-sig"))


class Profile:
    def __init__(self, path, *, simulate=False, expected_sha256=None):
        self.path = Path(path).expanduser().resolve() if path else None
        if self.path:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            self.sha256 = hashlib.sha256(raw).hexdigest()
            if expected_sha256 is not None and expected_sha256 != self.sha256:
                raise Refused("Host profile changed since the client loaded it")
            source = loads(raw.decode("utf-8-sig"))
        elif expected_sha256 is not None:
            raise Refused("A profile path is required when pinning profile bytes")
        else:
            self.sha256 = None
            source = {"schema_version": 1}
        if (type(source) is not dict or type(source.get("schema_version", 1)) is not int
                or source.get("schema_version", 1) != 1):
            raise Refused("Expected a version 1 LabPilot profile")
        if type(source.get("simulate", False)) is not bool:
            raise Refused("simulate must be a JSON boolean")
        self.simulate = simulate or source.get("simulate", False)
        self.host = source.get("host", {})
        if type(self.host) is not dict:
            raise Refused("host must be a JSON object")
        self.runmanager = self._section("runmanager", [])
        self.blacs = self._section("blacs", {})
        rm_allow = self.runmanager.get("allow", [])
        blacs_allow = self.blacs.get("allow", {})
        if (type(rm_allow) is not list or any(type(action) is not str or action not in RUN_ACTIONS for action in rm_allow)
                or type(blacs_allow) is not dict or any(type(channels) is not list or
                    any(type(channel) is not str or not channel for channel in channels)
                    for channels in blacs_allow.values())):
            raise Refused("Invalid host action allowlist")
        port = self.runmanager.get("port")
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise Refused("Invalid local Runmanager port")
        limit = self.runmanager.get("max_shots", 10000)
        if type(limit) is not int or limit <= 0:
            raise Refused("max_shots must be a positive integer")
        self.state_db = self.resolve(self.host.get("state_db", ".labpilot-host.sqlite3"))
        self.spool = self.resolve(self.blacs.get("spool", ".labpilot-blacs-spool"))

    def _section(self, name, allow):
        section = self.host.get(name, {})
        if type(section) is not dict or type(section.get("enabled", False)) is not bool:
            raise Refused(f"Invalid {name} host configuration")
        return {"allow": allow, **section}

    def resolve(self, value):
        if type(value) is not str or not value.strip():
            raise Refused("Expected a nonempty filesystem path")
        path = Path(value).expanduser()
        if not path.is_absolute() and self.path is not None:
            path = self.path.parent / path
        return path.resolve()


class Journal:
    def __init__(self, path, *, simulate=False):
        self.path = path
        self.mode = "simulation" if simulate else "native"

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=5)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS host_mode (id INTEGER PRIMARY KEY CHECK (id=1), mode TEXT)")
            with conn:
                conn.execute("INSERT OR IGNORE INTO host_mode VALUES (1, ?)", (self.mode,))
            if conn.execute("SELECT mode FROM host_mode WHERE id=1").fetchone()[0] != self.mode:
                raise Refused("Simulation and native mode require separate host state databases")
            conn.execute("CREATE TABLE IF NOT EXISTS operations ("
                         "id TEXT PRIMARY KEY, target TEXT, hash TEXT, result TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS simulator (target TEXT PRIMARY KEY, state TEXT)")
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def exclusive_effect(self):
        with self.path.with_suffix(self.path.suffix + ".effect-lock").open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Refused("Another host effect is already in progress") from exc
            yield

    def reserve(self, key, target, params):
        identity = digest(params)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT hash,result FROM operations WHERE id=?", (key,)).fetchone()
            if row:
                if row[0] != identity:
                    raise Refused("Request ID is already bound to different parameters")
                return loads(row[1]) if row[1] else receipt("UNKNOWN", request_id=key,
                                                             reason="Prior effect outcome is unresolved")
            db.execute("INSERT INTO operations VALUES (?, ?, ?, NULL)", (key, target, identity))
        return None

    def store(self, key, result):
        with self._connect() as db:
            db.execute("UPDATE operations SET result=? WHERE id=?", (canonical(result), key))

    def observe(self, key, target):
        if not self.path.is_file():
            return None
        with self._connect() as db:
            row = db.execute("SELECT result FROM operations WHERE id=? AND target=?", (key, target)).fetchone()
        if row is None:
            return None
        return loads(row[0]) if row[0] else receipt("UNKNOWN", request_id=key, reason="Effect is unresolved")

    def simulated_state(self, target, default, update=None):
        if update is None and not self.path.is_file():
            return default
        with self._connect() as db:
            if update is not None:
                db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM simulator WHERE target=?", (target,)).fetchone()
            state = loads(row[0]) if row else default
            if update is not None:
                state = update(state)
                db.execute("INSERT OR REPLACE INTO simulator VALUES (?, ?)", (target, canonical(state)))
        return state
