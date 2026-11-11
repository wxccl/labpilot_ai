"""Isolated worker for an operator-pinned single-shot Lyse routine."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType


PREFIX = "LABPILOT_SHOT_ANALYSIS:"


def _copy_shot(h5py, params, staging):
    shot = params["shot"]
    original = Path(shot["path"])
    resolved = original.resolve(strict=True)
    if resolved != original or resolved.parent != Path(params["batch_root"]):
        raise ValueError("Shot path changed after the manifest was checked")
    digest = hashlib.sha256()
    length = 0
    # Keep Labscript's shared read lock for the entire byte-for-byte copy.
    with h5py.File(str(resolved), "r"), resolved.open("rb") as source, staging.open("xb") as copy:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            length += len(block)
            if length > params["max_shot_bytes"]:
                raise ValueError("Verified shot exceeds the configured analysis size limit")
            digest.update(block)
            copy.write(block)
    if digest.hexdigest() != shot["sha256"]:
        raise ValueError("Shot bytes differ from the completed-shot manifest")


def _scalar(value):
    if type(value).__module__.startswith("numpy") and getattr(value, "shape", None) == ():
        value = value.item()
    if type(value) in (bool, int, str) or type(value) is float and math.isfinite(value):
        return value
    raise ValueError("A Lyse result or identity attribute is not a finite scalar")


def _prepare_copy(h5py, params, staging):
    with h5py.File(str(staging), "r+") as file:
        sequence = file.attrs.get("sequence_id")
        if isinstance(sequence, bytes):
            sequence = sequence.decode("utf-8")
        if not isinstance(sequence, str) or not sequence:
            raise ValueError("Shot lacks a native Labscript sequence ID")
        index = _scalar(file.attrs.get("run number"))
        count = _scalar(file.attrs.get("n_runs"))
        if type(index) is not int or type(count) is not int or (index, count) != (
            params["shot"]["index"], params["expected_n_shots"]
        ):
            raise ValueError("Native Labscript shot index or count does not match the manifest")
        if "results" in file:
            if not isinstance(file.get("results", getlink=True), h5py.HardLink) or not isinstance(file["results"], h5py.Group):
                raise ValueError("The copied results path is not a local HDF5 group")
            results = file["results"]
            group = params["binding"]["result_group"]
            if group in results:
                del results[group]
        return sequence


def _run_routine(lyse, routine, source, staging):
    previous_main = sys.modules["__main__"]
    previous_argv = sys.argv
    previous_path = lyse.path
    previous_cwd = Path.cwd()
    namespace = ModuleType("__main__")
    namespace.__file__ = str(routine)
    try:
        sys.modules["__main__"] = namespace
        sys.argv = [str(routine), str(staging)]
        lyse.path = str(staging)
        os.chdir(staging.parent)
        with open(os.devnull, "w", encoding="utf-8") as discard, redirect_stdout(discard), redirect_stderr(discard):
            exec(compile(source, str(routine), "exec"), namespace.__dict__)
    finally:
        os.chdir(previous_cwd)
        lyse.path = previous_path
        sys.argv = previous_argv
        sys.modules["__main__"] = previous_main


def analyze(params):
    # Ordering matters. Lyse shares the installed Labscript HDF5 lock.
    import labscript_utils.h5_lock as lock
    import h5py
    import lyse

    if h5py.File is not lock.File:
        raise RuntimeError("Labscript HDF5 locking is not active")
    routine = Path(params["routine"])
    if routine.resolve(strict=True) != routine:
        raise ValueError("Lyse routine path changed after review")
    with routine.open("rb") as stream:
        source = stream.read(2 * 1024 * 1024 + 1)
    if len(source) > 2 * 1024 * 1024 or hashlib.sha256(source).hexdigest() != params["binding"]["routine_sha256"]:
        raise ValueError("Lyse routine bytes differ from the pinned SHA-256")
    group = params["binding"]["result_group"]
    with TemporaryDirectory(prefix="labpilot_shot_analysis_") as directory:
        staging = Path(directory) / Path(params["shot"]["path"]).name
        _copy_shot(h5py, params, staging)
        sequence = _prepare_copy(h5py, params, staging)
        _run_routine(lyse, routine, source, staging)
        run = lyse.Run(str(staging), no_write=True)
        results = {name: _scalar(run.get_result(group, name)) for name in params["result_names"]}
    return {**params["binding"], "status": "COMPLETE", "results": results, "sequence_id": sequence,
            "lyse_version": str(lyse.__version__)}


def main():
    try:
        raw = sys.stdin.buffer.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ValueError("Lyse analysis worker request is too large")
        result = analyze(json.loads(raw))
    except (Exception, SystemExit) as exc:
        result = {"status": "FAILED", "reason": f"{type(exc).__name__}: {str(exc)[:1000]}"}
    print(PREFIX + json.dumps(result, ensure_ascii=True, allow_nan=False), flush=True)
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
