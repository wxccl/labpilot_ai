"""Validate a physical batch manifest and evaluate pinned Lyse result rules."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess


_SHA = re.compile(r"[0-9a-f]{64}")
_REQUEST = re.compile(r"[0-9a-f]{32}")
_PREFIX = b"LABPILOT_SHOT_ANALYSIS:"
_MAX_REPLY = 256 * 1024


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode("ascii")).hexdigest()


def _absolute(value, base):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A nonempty analysis path is required")
    return (base / Path(value).expanduser()).resolve()


def _matches_type(value, kind):
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _rules(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError("Specify one to 100 typed Lyse quality rules")
    rules = {}
    for row in values:
        if not isinstance(row, dict) or set(row) - {"result", "type", "min", "max", "equals"}:
            raise ValueError("Invalid Lyse quality rule fields")
        name, kind = row.get("result"), row.get("type")
        if not isinstance(name, str) or not name or len(name) > 200 or name in rules:
            raise ValueError("Quality rules require distinct nonempty result names")
        conditions = {key: row[key] for key in ("min", "max", "equals") if key in row}
        if kind not in ("number", "integer", "boolean") or not conditions:
            raise ValueError("Each Lyse quality rule needs a type and a condition")
        if kind == "boolean" and set(conditions) != {"equals"}:
            raise ValueError("Boolean quality rules use equals")
        if not all(_matches_type(value, kind) for value in conditions.values()):
            raise ValueError("A quality threshold does not match its declared type")
        if "min" in conditions and "max" in conditions and conditions["min"] > conditions["max"]:
            raise ValueError("A quality rule's minimum exceeds its maximum")
        rules[name] = {"type": kind, **conditions}
    return rules


def _violations(results, rules):
    if not isinstance(results, dict) or results.keys() != rules.keys():
        raise ValueError("Lyse did not return all required result names")
    failed = []
    for name, rule in rules.items():
        value = results[name]
        if not _matches_type(value, rule["type"]):
            raise ValueError(f"Lyse result {name!r} did not match its required scalar type")
        if ("min" in rule and value < rule["min"] or "max" in rule and value > rule["max"] or
                "equals" in rule and value != rule["equals"]):
            failed.append(name)
    return failed


def _checked_manifest(manifest, request_id, config_digest, expected_n_shots):
    if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
        raise ValueError("Invalid analysis batch request ID")
    if not isinstance(config_digest, str) or not _SHA.fullmatch(config_digest):
        raise ValueError("Invalid analysis configuration digest")
    if type(expected_n_shots) is not int or expected_n_shots < 1:
        raise ValueError("Analysis requires a positive planned shot count")
    binding = {"batch_id": request_id, "config_digest": config_digest, "expected_n_shots": expected_n_shots}
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in binding.items()):
        raise ValueError("Shot manifest is not bound to this request, configuration, and shot count")
    if type(manifest["expected_n_shots"]) is not int:
        raise ValueError("Invalid manifest shot count")
    root = manifest.get("batch_root")
    if not isinstance(root, str) or not Path(root).is_absolute():
        raise ValueError("The shot manifest needs an absolute batch root")
    root = Path(root).resolve()
    rows = manifest.get("shots")
    if not isinstance(rows, list) or len(rows) != expected_n_shots:
        raise ValueError("Shot manifest does not cover the planned shot count")
    shots = {}
    paths = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid shot manifest row")
        index, path, sha256 = row.get("index"), row.get("path"), row.get("sha256")
        if type(index) is not int or not 0 <= index < expected_n_shots or index in shots:
            raise ValueError("Invalid or duplicate shot index")
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("A shot manifest path must be absolute")
        path = Path(path).resolve()
        if path.parent != root or path in paths or path.suffix.lower() not in (".h5", ".hdf5"):
            raise ValueError("Shot path is duplicated or outside the verified batch directory")
        if not isinstance(sha256, str) or not _SHA.fullmatch(sha256):
            raise ValueError("Invalid shot SHA-256")
        paths.add(path)
        shots[index] = {"index": index, "path": str(path), "sha256": sha256}
    return {**binding, "batch_root": str(root), "shots": [shots[i] for i in range(expected_n_shots)]}


def _write_once(path, value):
    # This is called under the batch lease. An absent marker allows analysis
    # to regenerate a report interrupted before its data reached disk.
    with path.open("w", encoding="utf-8") as stream:
        stream.write(_json(value))
        stream.flush()
        os.fsync(stream.fileno())
    with path.with_suffix(".ok").open("xb") as marker:
        os.fsync(marker.fileno())


def _committed(path):
    return path.with_suffix(".ok").is_file()


def _report_path(path):
    value = str(path)
    if os.name != "nt" or len(value) < 220 or value.startswith("\\\\?\\"):
        return path
    return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)


@contextmanager
def _analysis_lease(directory):
    with (directory / ".analysis.lock").open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

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


class LyseBatchAnalysis:
    """Execute one site-approved routine against copies of verified shot files."""

    def __init__(self, python, config, *, base_dir, state_dir=None):
        if not isinstance(config, dict) or set(config) - {
            "routine", "routine_sha256", "quality_rules", "timeout_s", "shots_per_observation", "max_shot_bytes"
        }:
            raise ValueError("Invalid Lyse analysis profile fields")
        base = Path(base_dir).resolve()
        self.python = Path(python).resolve()
        self.routine = _absolute(config.get("routine"), base)
        self.routine_sha256 = config.get("routine_sha256")
        if self.routine.suffix.lower() != ".py" or not isinstance(self.routine_sha256, str) or not _SHA.fullmatch(self.routine_sha256):
            raise ValueError("Lyse analysis requires a pinned Python routine SHA-256")
        self.rules = _rules(config.get("quality_rules"))
        self.timeout = config.get("timeout_s", 60)
        if not _matches_type(self.timeout, "number") or not 1 <= self.timeout <= 900:
            raise ValueError("Lyse timeout_s must be between 1 and 900 seconds")
        self.step = config.get("shots_per_observation", 4)
        if type(self.step) is not int or not 1 <= self.step <= 64:
            raise ValueError("shots_per_observation must be between 1 and 64")
        self.max_shot_bytes = config.get("max_shot_bytes", 512 * 1024 * 1024)
        if type(self.max_shot_bytes) is not int or self.max_shot_bytes < 1:
            raise ValueError("max_shot_bytes must be a positive integer")
        self.state_dir = Path(state_dir).resolve() if state_dir is not None else base / ".labpilot-analysis"
        self.profile_sha256 = _digest({"routine": str(self.routine), "routine_sha256": self.routine_sha256,
                                      "quality_rules": self.rules})

    def analyze(self, manifest, *, request_id, config_digest, expected_n_shots, prior_manifest_sha256=None):
        result = {"analysis_state": "FAILED", "quality": "UNKNOWN", "analyzed_count": 0,
                  "routine_sha256": self.routine_sha256, "analysis_profile_sha256": self.profile_sha256,
                  "result_group": self.routine.stem}
        try:
            checked = _checked_manifest(manifest, request_id, config_digest, expected_n_shots)
            manifest_sha256 = _digest(checked)
            if prior_manifest_sha256 is not None and prior_manifest_sha256 != manifest_sha256:
                raise ValueError("The completed-shot manifest changed after analysis started")
            result["manifest_sha256"] = manifest_sha256
            directory = _report_path(self.state_dir / request_id)
            directory.mkdir(parents=True, exist_ok=True)
            result["report_dir"] = str(directory)
            with _analysis_lease(directory) as available:
                if available:
                    manifest_path = directory / "manifest.json"
                    if _committed(manifest_path):
                        with manifest_path.open("rb") as stream:
                            if _digest(json.load(stream)) != manifest_sha256:
                                raise ValueError("The stored completed-shot manifest changed")
                    else:
                        _write_once(manifest_path, checked)
                    self._analyze_shots(checked, directory, result)
                else:
                    result["analysis_state"] = "PENDING"
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result.update(analysis_state="FAILED", quality="UNKNOWN", reason=str(exc))
        return result

    def _analyze_shots(self, manifest, directory, result):
        remaining = self.step
        failed_shots = 0
        sequence = None
        lyse_version = None
        for shot in manifest["shots"]:
            path = directory / f"shot_{shot['index']:06d}.json"
            cached = _committed(path)
            binding = {
                "request_id": manifest["batch_id"], "config_digest": manifest["config_digest"],
                "manifest_sha256": result["manifest_sha256"], "analysis_profile_sha256": self.profile_sha256,
                "routine_sha256": self.routine_sha256, "source_sha256": shot["sha256"],
                "index": shot["index"], "result_group": self.routine.stem,
            }
            if cached:
                with path.open("rb") as stream:
                    report = json.loads(stream.read(_MAX_REPLY + 1))
                self._validate_report(report, binding)
            elif remaining:
                payload = self._run_shot(manifest, shot, binding)
                report = {**payload, "violations": _violations(payload["results"], self.rules)}
                report["report_sha256"] = _digest(report)
            else:
                break
            if sequence is not None and report["sequence_id"] != sequence:
                raise ValueError("Shots do not share a native Labscript sequence ID")
            if lyse_version is not None and report["lyse_version"] != lyse_version:
                raise ValueError("Lyse version changed within the batch")
            if not cached:
                _write_once(path, report)
                remaining -= 1
            sequence = report["sequence_id"]
            lyse_version = report["lyse_version"]
            result["lyse_version"] = lyse_version
            result["analyzed_count"] += 1
            failed_shots += bool(report["violations"])
            result["failed_shots"] = failed_shots
        if result["analyzed_count"] < manifest["expected_n_shots"]:
            result["analysis_state"] = "PENDING"
            return
        result.update(analysis_state="COMPLETE", quality="FAIL" if failed_shots else "PASS")

    def _validate_report(self, report, binding):
        if (not isinstance(report, dict) or report.get("status") != "COMPLETE" or
                any(report.get(key) != value for key, value in binding.items())):
            raise ValueError("Stored Lyse report has a different shot or routine binding")
        body = {key: value for key, value in report.items() if key != "report_sha256"}
        if (report.get("report_sha256") != _digest(body) or not isinstance(report.get("sequence_id"), str) or
                not report["sequence_id"] or not isinstance(report.get("lyse_version"), str) or not report["lyse_version"] or
                report.get("violations") != _violations(report.get("results"), self.rules)):
            raise ValueError("Stored Lyse report failed its provenance check")

    def _run_shot(self, manifest, shot, binding):
        worker = Path(__file__).with_name("worker.py")
        params = {"shot": shot, "batch_root": manifest["batch_root"], "expected_n_shots": manifest["expected_n_shots"],
                  "routine": str(self.routine), "result_names": sorted(self.rules), "binding": binding,
                  "max_shot_bytes": self.max_shot_bytes}
        env = dict(os.environ, MPLBACKEND="Agg")
        env.pop("READTHEDOCS", None)
        completed = subprocess.run([str(self.python), "-I", "-X", "utf8", str(worker)],
                                   input=_json(params).encode("ascii"), capture_output=True, env=env,
                                   timeout=self.timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        replies = [line[len(_PREFIX):] for line in completed.stdout.splitlines() if line.startswith(_PREFIX)]
        if len(replies) != 1 or len(replies[0]) > _MAX_REPLY:
            raise RuntimeError("Lyse analysis worker returned no valid receipt")
        reply = json.loads(replies[0])
        if completed.returncode or not isinstance(reply, dict) or reply.get("status") != "COMPLETE":
            reason = reply.get("reason") if isinstance(reply, dict) else None
            raise RuntimeError(reason or "Lyse analysis worker failed")
        if (any(reply.get(key) != value for key, value in binding.items()) or
                not isinstance(reply.get("sequence_id"), str) or not reply["sequence_id"] or
                not isinstance(reply.get("lyse_version"), str) or not reply["lyse_version"]):
            raise RuntimeError("Lyse analysis worker receipt is not bound to the shot and routine")
        return reply
