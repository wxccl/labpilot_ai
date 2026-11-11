"""Local SQLite task queue, approvals, and durable mutation intent."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4


ACTIVE = ("EXECUTING", "OBSERVING", "UNKNOWN")
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "UNVERIFIED")
SPEC_FIELDS = {"kind", "action", "request_id", "expected_config_digest", "expected_shots", "params"}
PARAM_BINDINGS = {"action", "request_id", "expected_snapshot_sha256", "expected_n_shots"}
HEX_32 = re.compile(r"[0-9a-f]{32}")
HEX_64 = re.compile(r"[0-9a-f]{64}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    spec TEXT NOT NULL,
    used_actions INTEGER NOT NULL DEFAULT 0,
    used_shots INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    plan_digest TEXT NOT NULL,
    spec TEXT NOT NULL,
    policy_id TEXT REFERENCES policies(policy_id),
    status TEXT NOT NULL,
    approval TEXT,
    claim_token TEXT,
    receipt TEXT,
    observation TEXT,
    evidence TEXT NOT NULL DEFAULT '{}',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_task ON tasks((1))
WHERE status IN ('EXECUTING', 'OBSERVING', 'UNKNOWN');
CREATE TABLE IF NOT EXISTS task_events (
    event_id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    kind TEXT NOT NULL,
    at TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS task_events_by_task ON task_events(task_id, event_id);
"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _label(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{name} must be a nonempty string of at most 200 characters")
    return value


def _count(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise ValueError(f"{name} must be an integer from {minimum} to {2**63 - 1}")
    return value


def _sha(value, pattern, name):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"Invalid {name}")
    return value


def _spec(spec):
    if not isinstance(spec, dict) or not SPEC_FIELDS <= spec.keys() or spec.keys() - SPEC_FIELDS - {"task_id", "policy_id"}:
        raise ValueError("Expected a complete task specification")
    if spec["kind"] not in ("short", "batch"):
        raise ValueError("Task kind must be short or batch")
    _label(spec["action"], "action")
    _sha(spec["request_id"], HEX_32, "request ID")
    _sha(spec["expected_config_digest"], HEX_64, "expected configuration digest")
    count = _count(spec["expected_shots"], "expected_shots")
    if (spec["kind"] == "batch") != (count > 0):
        raise ValueError("A batch requires a positive shot count and a short task requires zero shots")
    if spec["params"] is None or not isinstance(spec["params"], dict) or PARAM_BINDINGS & spec["params"].keys():
        raise ValueError("params must be an object without server-owned request bindings")
    _label(spec["params"].get("target"), "params.target")
    # A mislabeled Engage would consume no shot budget and release the writer on ACK.
    if spec["action"] == "engage" and spec["kind"] != "batch":
        raise ValueError("Engage must be a batch task")
    return {name: spec[name] for name in SPEC_FIELDS}


def plan_digest(spec):
    """Bind review to the exact parameters, configuration, count, and request ID."""
    return hashlib.sha256(_json(_spec(spec)).encode("utf-8")).hexdigest()


def policy_scope_digest(spec):
    """A3 scope covers a reviewed effect regardless of its one-time request ID."""
    fields = _spec(spec)
    del fields["request_id"]
    return hashlib.sha256(_json(fields).encode("utf-8")).hexdigest()


class TaskStore:
    """One task database per site. Claims and policy debits share a transaction."""

    def __init__(self, path, *, clock=None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _write(self):
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _now(self):
        return _time(self.clock())

    @contextmanager
    def _effect_lease(self):
        # The OS releases the lock if a process dies. The committed SQLite
        # intent survives, so another process can observe without resubmitting.
        lock_path = self.path.with_name(self.path.name + ".writer.lock")
        with lock_path.open("a+b") as stream:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                yield False
                return
            yield True

    @staticmethod
    def _row(connection, task_id):
        row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        return row

    @staticmethod
    def _task(row):
        result = dict(row)
        spec = json.loads(result.pop("spec"))
        result.update(spec)
        result["scope_digest"] = policy_scope_digest(spec)
        result.pop("claim_token")
        for field in ("approval", "receipt", "observation", "evidence"):
            if result[field] is not None:
                result[field] = json.loads(result[field])
        result["cancel_requested"] = bool(result["cancel_requested"])
        return result

    @staticmethod
    def _event(connection, task_id, kind, now, detail):
        connection.execute(
            "INSERT INTO task_events (task_id, kind, at, detail) VALUES (?, ?, ?, ?)",
            (task_id, kind, now, _json(detail)),
        )

    def get(self, task_id):
        with closing(self._connect()) as connection:
            return self._task(self._row(connection, task_id))

    def list(self):
        with closing(self._connect()) as connection:
            return [self._task(row) for row in connection.execute("SELECT * FROM tasks ORDER BY rowid")]

    def list_active(self):
        with closing(self._connect()) as connection:
            return [self._task(row) for row in connection.execute(
                "SELECT * FROM tasks WHERE status IN ('EXECUTING','OBSERVING','UNKNOWN') ORDER BY rowid"
            )]

    def events(self, task_id):
        with closing(self._connect()) as connection:
            self._row(connection, task_id)
            return [dict(row, detail=json.loads(row["detail"])) for row in connection.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY event_id", (task_id,)
            )]

    def submit(self, spec):
        frozen = _json(_spec(spec))
        digest = plan_digest(spec)
        request_id = spec["request_id"]
        task_id = _label(spec.get("task_id", request_id), "task_id")
        policy_id = spec.get("policy_id")
        now = self._now()
        with self._write() as connection:
            previous = connection.execute("SELECT * FROM tasks WHERE request_id = ?", (request_id,)).fetchone()
            if previous is not None:
                if (previous["spec"], previous["task_id"]) != (frozen, task_id) or (
                    policy_id is not None and previous["policy_id"] != policy_id
                ):
                    raise ValueError("Request ID already belongs to a different task")
                return self._task(previous)
            status = "PENDING_APPROVAL"
            if policy_id is not None:
                policy = self._policy(connection, policy_id)
                if policy_scope_digest(spec) not in policy["scope_digests"]:
                    raise ValueError("A3 policy does not authorize this scope")
                status = "READY"
            connection.execute(
                "INSERT INTO tasks(task_id, request_id, plan_digest, spec, policy_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, request_id, digest, frozen, policy_id, status, now, now),
            )
            self._event(connection, task_id, "SUBMITTED", now, {"plan_digest": digest, "policy_id": policy_id})
            return self._task(self._row(connection, task_id))

    def approve(self, task_id, plan_digest, approver, expires_at):
        expires = _time(expires_at)
        approval = {"mode": "A2", "approver": _label(approver, "approver"), "expires_at": expires,
                    "plan_digest": _sha(plan_digest, HEX_64, "plan digest")}
        with self._write() as connection:
            now = self._now()
            task = self._row(connection, task_id)
            if expires <= now or task["plan_digest"] != plan_digest:
                raise ValueError("Approval must be unexpired and match the frozen plan")
            if task["status"] not in ("PENDING_APPROVAL", "READY"):
                raise ValueError("Only unclaimed tasks may be approved")
            connection.execute(
                "UPDATE tasks SET approval = ?, status = 'READY', version = version + 1, updated_at = ? WHERE task_id = ?",
                (_json(approval), now, task_id),
            )
            self._event(connection, task_id, "APPROVED", now, approval)
            return self._task(self._row(connection, task_id))

    @staticmethod
    def _policy(connection, policy_id):
        row = connection.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown policy: {policy_id}")
        return dict(json.loads(row["spec"]), used_actions=row["used_actions"], used_shots=row["used_shots"],
                    revoked=bool(row["revoked"]))

    def create_policy(self, policy):
        now = self._now()
        if not isinstance(policy, dict):
            raise ValueError("Expected an A3 policy object")
        fields = {"policy_id", "approver", "expires_at", "scope_digests", "max_actions", "max_shots"}
        if not fields <= policy.keys() or policy.keys() - fields - {"starts_at"}:
            raise ValueError("A3 needs reviewed scope digests, a time window, and budgets")
        policy = dict(policy)
        policy_id = _label(policy["policy_id"], "policy_id")
        _label(policy["approver"], "approver")
        if not isinstance(policy["scope_digests"], list) or not policy["scope_digests"]:
            raise ValueError("A3 needs a nonempty list of reviewed scope digests")
        policy["scope_digests"] = sorted({_sha(value, HEX_64, "scope digest") for value in policy["scope_digests"]})
        policy["starts_at"] = _time(policy.get("starts_at", now))
        policy["expires_at"] = _time(policy["expires_at"])
        if policy["expires_at"] <= max(policy["starts_at"], now):
            raise ValueError("A3 policy must have an unexpired time window")
        _count(policy["max_actions"], "max_actions", 1)
        _count(policy["max_shots"], "max_shots")
        with self._write() as connection:
            connection.execute("INSERT INTO policies(policy_id, spec) VALUES (?, ?)", (policy_id, _json(policy)))
            return self._policy(connection, policy_id)

    def get_policy(self, policy_id):
        with closing(self._connect()) as connection:
            return self._policy(connection, policy_id)

    def authorize_policy(self, task_id, policy_id):
        """Attach an already approved A3 scope to an unclaimed task."""
        with self._write() as connection:
            task = self._task(self._row(connection, task_id))
            now = self._now()
            policy = self._policy(connection, policy_id)
            if task["status"] not in ("PENDING_APPROVAL", "READY"):
                raise ValueError("Only unclaimed tasks may use a policy")
            if policy["revoked"] or policy["expires_at"] <= now or task["scope_digest"] not in policy["scope_digests"]:
                raise ValueError("A3 policy is revoked, expired, or outside the reviewed scope")
            connection.execute(
                "UPDATE tasks SET policy_id = ?, approval = NULL, status = 'READY', version = version + 1, "
                "updated_at = ? WHERE task_id = ?", (policy_id, now, task_id),
            )
            self._event(connection, task_id, "POLICY_ATTACHED", now,
                        {"policy_id": policy_id, "scope_digest": task["scope_digest"]})
            return self._task(self._row(connection, task_id))

    def revoke_policy(self, policy_id):
        with self._write() as connection:
            self._policy(connection, policy_id)
            connection.execute("UPDATE policies SET revoked = 1 WHERE policy_id = ?", (policy_id,))
            return self._policy(connection, policy_id)

    def cancel(self, task_id):
        with self._write() as connection:
            task = self._row(connection, task_id)
            if task["cancel_requested"] or task["status"] in TERMINAL:
                return self._task(task)
            now = self._now()
            status = "CANCELLED" if task["status"] not in ACTIVE else task["status"]
            connection.execute(
                "UPDATE tasks SET status = ?, cancel_requested = 1, version = version + 1, updated_at = ? WHERE task_id = ?",
                (status, now, task_id),
            )
            self._event(connection, task_id, "CANCEL_REQUESTED", now, {"status": status})
            return self._task(self._row(connection, task_id))

    def close_unresolved(self, task_id, operator, reason):
        """Record operator closure after confirming the external run has ended."""
        detail = {"operator": _label(operator, "operator"), "reason": _label(reason, "reason")}
        with self._effect_lease() as available:
            if not available:
                raise RuntimeError("Cannot close a task while a host dispatch is active")
            with self._write() as connection:
                task = self._row(connection, task_id)
                if task["status"] not in ("OBSERVING", "UNKNOWN"):
                    raise ValueError("Only observing or unknown tasks can be closed without verification")
                now = self._now()
                connection.execute(
                    "UPDATE tasks SET status = 'UNVERIFIED', version = version + 1, updated_at = ? WHERE task_id = ?",
                    (now, task_id),
                )
                self._event(connection, task_id, "CLOSED_UNVERIFIED", now, detail)
                return self._task(self._row(connection, task_id))

    def _claim(self):
        with self._write() as connection:
            if connection.execute("SELECT 1 FROM tasks WHERE status IN ('EXECUTING','OBSERVING','UNKNOWN')").fetchone():
                return None
            now = self._now()
            for row in connection.execute("SELECT * FROM tasks WHERE status = 'READY' ORDER BY rowid").fetchall():
                task = self._task(row)
                authority, reason = self._authority(connection, task, now)
                if authority is None:
                    if reason != "POLICY_NOT_STARTED":
                        connection.execute(
                            "UPDATE tasks SET approval = NULL, status = 'PENDING_APPROVAL', version = version + 1, "
                            "updated_at = ? WHERE task_id = ?", (now, task["task_id"]),
                        )
                        self._event(connection, task["task_id"], "APPROVAL_REQUIRED", now, {"reason": reason})
                    continue
                token = uuid4().hex
                connection.execute(
                    "UPDATE tasks SET status = 'EXECUTING', claim_token = ?, version = version + 1, "
                    "updated_at = ? WHERE task_id = ?", (token, now, task["task_id"]),
                )
                self._event(connection, task["task_id"], "EFFECT_INTENT", now, {**authority,
                            "request_id": task["request_id"], "plan_digest": task["plan_digest"],
                            "expected_config_digest": task["expected_config_digest"], "expected_shots": task["expected_shots"]})
                return self._task(self._row(connection, task["task_id"])), token, authority["expires_at"]
        return None

    def _authority(self, connection, task, now):
        approval = task["approval"]
        if approval:
            if approval["expires_at"] > now and approval["plan_digest"] == task["plan_digest"]:
                return approval, None
            return None, "A2_EXPIRED_OR_MISMATCH"
        if task["policy_id"] is None:
            return None, "MISSING_APPROVAL"
        policy = self._policy(connection, task["policy_id"])
        shots = task["expected_shots"]
        if policy["revoked"] or policy["expires_at"] <= now or task["scope_digest"] not in policy["scope_digests"]:
            return None, "A3_REVOKED_EXPIRED_OR_MISMATCH"
        if now < policy["starts_at"]:
            return None, "POLICY_NOT_STARTED"
        if policy["used_actions"] >= policy["max_actions"] or shots > policy["max_shots"] - policy["used_shots"]:
            return None, "A3_BUDGET_EXHAUSTED"
        connection.execute("UPDATE policies SET used_actions = used_actions + 1, used_shots = used_shots + ? WHERE policy_id = ?",
                           (shots, policy["policy_id"]))
        return {"mode": "A3", "approver": policy["approver"], "policy_id": policy["policy_id"],
                "expires_at": policy["expires_at"]}, None

    def _record_receipt(self, task_id, token, status, receipt):
        with self._write() as connection:
            row = self._row(connection, task_id)
            if row["claim_token"] != token or row["receipt"] is not None:
                raise RuntimeError("Receipt does not match the outstanding durable claim")
            if row["status"] in TERMINAL:
                status = row["status"]
            elif row["status"] == "OBSERVING" and status == "UNKNOWN":
                status = "OBSERVING"
            now = self._now()
            connection.execute(
                "UPDATE tasks SET status = ?, receipt = ?, version = version + 1, updated_at = ? WHERE task_id = ?",
                (status, _json(receipt), now, task_id),
            )
            self._event(connection, task_id, "EFFECT_RECEIPT", now, {"status": status, "receipt": receipt})
            return self._task(self._row(connection, task_id))

    def _record_observation(self, task, status, observation, evidence):
        with self._write() as connection:
            row = self._row(connection, task["task_id"])
            if row["version"] != task["version"]:
                return self._task(row)
            raw_observation = _json(observation)
            raw_evidence = _json(evidence)
            if (row["status"], row["observation"], row["evidence"]) == (status, raw_observation, raw_evidence):
                return self._task(row)
            now = self._now()
            connection.execute(
                "UPDATE tasks SET status = ?, observation = ?, evidence = ?, version = version + 1, "
                "updated_at = ? WHERE task_id = ?", (status, raw_observation, raw_evidence, now, task["task_id"]),
            )
            previous = json.loads(row["observation"] or "{}")
            signal_changed = any(observation.get(field) != previous.get(field) for field in ("state", "reason"))
            if status != row["status"] or raw_evidence != row["evidence"] or signal_changed:
                self._event(connection, task["task_id"], "OBSERVED", now, {"status": status, "evidence": evidence,
                            "observation_state": observation.get("state"), "reason": observation.get("reason")})
            return self._task(self._row(connection, task["task_id"]))
