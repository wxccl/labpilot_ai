"""Durable Runmanager and BLACS evidence for exactly one managed batch."""

from datetime import datetime
import hashlib
from pathlib import Path

from .protocol import Journal, Refused, canonical, digest, loads


BATCH_PROTOCOL = "labpilot-native-batch/1"


def source_text_hash(path):
    with open(path) as source:  # Match labscript's script text and universal-newline handling.
        return hashlib.sha256(source.read().encode("utf-8")).hexdigest()


def _h5():
    import labscript_utils.h5_lock  # Must precede h5py in the stock suite.
    import h5py

    return h5py


def _string(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise ValueError("Expected native H5 text metadata")


def _integer(value):
    from numbers import Integral

    if not isinstance(value, Integral) or isinstance(value, bool):
        raise ValueError("Expected native H5 integer metadata")
    return int(value)


def _identity(h5, batch):
    attrs = h5.attrs
    index = _integer(attrs["run number"])
    count = _integer(attrs["n_runs"])
    if count != batch["expected_n_shots"] or not 0 <= index < count:
        raise ValueError("Shot index or count differs from the reserved batch")
    if _integer(attrs.get("run repeat", 0)) != 0:
        raise ValueError("Repeated shots do not belong to the original execution")
    script = _string(attrs["script_basename"])
    sequence_id = _string(attrs["sequence_id"])
    date = _string(attrs["sequence_date"])
    sequence_index = _integer(attrs["sequence_index"])
    if script != batch["script_basename"] or not sequence_id or not date or sequence_index < 0:
        raise ValueError("Shot sequence metadata differs from the reserved script")
    raw = {}
    for group in h5["globals"].values():
        for name, expression in group.attrs.items():
            if name in raw:
                raise ValueError("Duplicate global names in native H5 groups")
            raw[name] = _string(expression)
    if digest(raw) != batch["globals_sha256"]:
        raise ValueError("Shot raw globals differ from the reserved configuration")
    return index, canonical([sequence_id, date, sequence_index, script])


def inspect_shot(path, batch, *, compiled=False, completed=False, content_hash=False):
    if path.is_symlink() or path.resolve().parent != Path(batch["batch_root"]):
        raise ValueError("Shot lies outside the exact batch directory")
    with _h5().File(path, "r") as h5:
        index, sequence = _identity(h5, batch)
        if compiled or completed:
            script = h5["script"]
            script_text = _string(script[()])
            if (_string(script.attrs["name"]) != batch["sequence_name"] or
                    hashlib.sha256(script_text.encode("utf-8")).hexdigest() != batch["sequence_text_sha256"] or
                    "devices" not in h5 or "connection table" not in h5):
                raise ValueError("Compiled shot source differs from the reserved sequence")
        run_time = None
        if completed:
            run_time = _string(h5.attrs["run time"])
            try:
                datetime.strptime(run_time, "%Y%m%dT%H%M%S.%f%z")
            except ValueError:
                datetime.strptime(run_time, "%Y%m%dT%H%M%S.%f")
            if "data" not in h5:
                raise ValueError("Completed shot has no BLACS run timestamp or data group")
        sha256 = None
        if content_hash:
            value = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(block)
            sha256 = value.hexdigest()
    return index, sequence, run_time, sha256


class NativeBatches:
    def __init__(self, profile):
        self.profile = profile
        self.journal = Journal(profile.state_db)
        value = profile.runmanager.get("batch_root")
        self.root = profile.resolve(value) if value else None

    def _tables(self, db):
        db.execute("CREATE TABLE IF NOT EXISTS native_batches (id TEXT PRIMARY KEY, data TEXT NOT NULL, "
                   "phase TEXT NOT NULL, ambiguity TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS native_shots (batch TEXT, idx INTEGER, path TEXT UNIQUE, "
                   "sequence TEXT, compiled INTEGER DEFAULT 0, queued INTEGER DEFAULT 0, "
                   "run_time TEXT, PRIMARY KEY (batch, idx))")

    def reserve(self, params, current):
        key = params["request_id"]
        if self.root is None or not self.root.is_dir():
            raise Refused("The managed batch_root must be an existing directory")
        output = self.profile.runmanager.get("output_root")
        if output is None or not self.root.is_relative_to(self.profile.resolve(output)):
            raise Refused("Managed batch_root must be inside the approved output_root")
        if str(self.root).startswith(("\\\\", "//")):
            raise Refused("Use a same-machine batch_root accessible to Runmanager and BLACS")
        sequence_path = Path(current["sequence"])
        batch = {"batch_id": key, "config_digest": current["snapshot_sha256"],
                 "batch_root": str(self.root / key), "expected_n_shots": current["n_shots"],
                 "script_basename": sequence_path.stem, "sequence_name": sequence_path.name,
                 "sequence_text_sha256": source_text_hash(sequence_path),
                 "globals_sha256": digest(current["globals_raw"])}
        with self.journal._connect() as db:
            self._tables(db)
            db.execute("BEGIN IMMEDIATE")
            intent = db.execute("SELECT target,hash,result FROM operations WHERE id=?", (key,)).fetchone()
            if intent != ("runmanager", digest(params), None):
                raise Refused("The managed operation has no matching pending host intent")
            if db.execute("SELECT 1 FROM native_batches WHERE id=?", (key,)).fetchone():
                raise Refused("The managed batch is already reserved")
            try:
                (self.root / key).mkdir()
            except FileExistsError as exc:
                raise Refused("The dedicated batch directory already exists") from exc
            db.execute("INSERT INTO native_batches VALUES (?, ?, 'RESERVED', NULL)", (key, canonical(batch)))
        return batch

    def phase(self, key, phase):
        with self.journal._connect() as db:
            self._tables(db)
            db.execute("UPDATE native_batches SET phase=? WHERE id=?", (phase, key))

    def _get(self, db, key):
        self._tables(db)
        row = db.execute("SELECT data,phase,ambiguity FROM native_batches WHERE id=?", (key,)).fetchone()
        return (loads(row[0]), row[1], row[2]) if row else (None, None, None)

    def _match_path(self, raw_path):
        if self.root is None:
            return None, None
        raw = Path(raw_path)
        if raw.suffix.lower() != ".h5" or raw.is_symlink():
            return None, None
        path = raw.resolve()
        if path.parent.parent != self.root:
            return None, None
        return path.parent.name, path

    def _ambiguous(self, key, detail):
        with self.journal._connect() as db:
            self._tables(db)
            db.execute("UPDATE native_batches SET ambiguity=COALESCE(ambiguity, ?) WHERE id=?", (detail, key))

    def generated(self, batch, raw_paths):
        key = batch["batch_id"]
        try:
            for raw_path in raw_paths:
                matched, path = self._match_path(raw_path)
                if matched != key or path is None:
                    raise ValueError("Runmanager generated a path outside the reserved batch")
                index, sequence, _, _ = inspect_shot(path, batch)
                with self.journal._connect() as db:
                    self._tables(db)
                    db.execute("BEGIN IMMEDIATE")
                    other = db.execute("SELECT sequence FROM native_shots WHERE batch=? LIMIT 1", (key,)).fetchone()
                    if other and other[0] != sequence:
                        raise ValueError("Runmanager generated more than one native sequence identity")
                    db.execute("INSERT INTO native_shots (batch,idx,path,sequence) VALUES (?,?,?,?)",
                               (key, index, str(path), sequence))
                yield str(path)
        except Exception as exc:
            self._ambiguous(key, f"Invalid generated shot: {exc}")
            raise

    def manages_path(self, raw_path):
        key, path = self._match_path(raw_path)
        if path is None or not self.journal.path.is_file():
            return False
        with self.journal._connect() as db:
            batch, _, _ = self._get(db, key)
            return batch is not None

    def record(self, raw_path, stage):
        key, path = self._match_path(raw_path)
        if path is None or not self.journal.path.is_file():
            return
        with self.journal._connect() as db:
            batch, _, ambiguity = self._get(db, key)
        if batch is None or ambiguity:
            return
        try:
            index, sequence, run_time, _ = inspect_shot(path, batch, compiled=True, completed=stage == "executed")
            with self.journal._connect() as db:
                self._tables(db)
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT path,sequence,compiled,queued,run_time FROM native_shots WHERE batch=? AND idx=?",
                                 (key, index)).fetchone()
                if row is None or row[:2] != (str(path), sequence):
                    raise ValueError("Callback does not match the exact original generated shot")
                if stage == "compiled" and row[2] == 0:
                    db.execute("UPDATE native_shots SET compiled=1 WHERE batch=? AND idx=?", (key, index))
                elif stage == "queued" and row[2:4] == (1, 0):
                    db.execute("UPDATE native_shots SET queued=1 WHERE batch=? AND idx=?", (key, index))
                elif stage == "executed" and row[2:] == (1, 1, None):
                    db.execute("UPDATE native_shots SET run_time=? WHERE batch=? AND idx=?", (run_time, key, index))
                else:
                    raise ValueError(f"Duplicate or out-of-order {stage} callback")
        except Exception as exc:
            self._ambiguous(key, f"Invalid {stage} evidence: {exc}")
            raise

    def observe(self, key):
        if self.root is None or not self.journal.path.is_file():
            return {}
        with self.journal._connect() as db:
            batch, phase, ambiguity = self._get(db, key)
            if batch is None:
                return {}
            shots = db.execute("SELECT idx,path,sequence,compiled,queued,run_time FROM native_shots "
                               "WHERE batch=? ORDER BY idx", (key,)).fetchall()
        public = {name: batch[name] for name in ("batch_id", "batch_root", "config_digest", "expected_n_shots")}
        result = {**public, "native_batch_phase": phase, "compiled_count": sum(row[3] for row in shots),
                  "queued_count": sum(row[4] for row in shots), "executed_count": sum(bool(row[5]) for row in shots)}
        if ambiguity:
            return {**result, "batch_ambiguity": ambiguity}
        if phase != "ACCEPTED_AND_RESTORED" or result["executed_count"] != batch["expected_n_shots"]:
            return result
        exact = []
        try:
            for index, name, sequence, compiled, queued, completed in shots:
                current = inspect_shot(Path(name), batch, completed=True, content_hash=True)
                if current[:3] != (index, sequence, completed):
                    raise ValueError("Current H5 identity differs from the BLACS completion callback")
                exact.append({"index": index, "path": name, "sha256": current[3]})
        except (OSError, KeyError, ValueError, ImportError) as exc:
            return {**result, "batch_ambiguity": str(exc)}
        with self.journal._connect() as db:
            _, latest_phase, latest_ambiguity = self._get(db, key)
        if latest_phase != phase or latest_ambiguity:
            return {**result, "batch_ambiguity": latest_ambiguity or "Batch state changed during H5 verification"}
        return {**result, "batch_execution_complete": True, "blacs_execution_verified": True,
                "physical_execution_verified": False,
                "shot_manifest": {**public, "shots": exact}}
