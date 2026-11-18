from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from .lyse_results_reader import read_results_group
from .h5_loader import _get_h5py
from .private_inputs import PrivateInputs
from .routine_source import checked_source


class LyseScriptError(RuntimeError):
    def __init__(self, message, *, stdout="", stderr="", traceback_text=""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr
        self.traceback_text = traceback_text


def _dataframe_payload(dataframe):
    if dataframe is None:
        dataframe = pd.DataFrame()
    return json.dumps(
        {
            "data": dataframe.to_dict(orient="list"),
        },
        ensure_ascii=False,
    )


def run_lyse_script(script_path, *, mode, h5_path=None, dataframe=None, meta_h5_path=None, params=None, timeout_s=300,
                    routine_sha256=None):
    _, digest = checked_source(script_path, routine_sha256)
    if type(timeout_s) not in (int, float) or not 0 < timeout_s <= 600:
        raise ValueError("Lyse subprocess timeout must be positive and at most 600 seconds")
    with PrivateInputs() as inputs:
        return _run_staged(script_path, mode=mode, h5_path=inputs.shot(h5_path) if h5_path else None,
                           dataframe=inputs.frame(dataframe), meta_h5_path=inputs.shot(meta_h5_path) if meta_h5_path else None,
                           params=params, timeout_s=timeout_s, digest=digest)


def _run_staged(script_path, *, mode, h5_path, dataframe, meta_h5_path, params, timeout_s, digest):
    script = Path(script_path).expanduser().resolve()
    if not script.exists():
        raise LyseScriptError(f"lyse script does not exist: {script}")
    if mode == "single" and h5_path:
        with _get_h5py().File(h5_path, "r+") as private:
            group_name = "results/" + script.stem
            if group_name in private:
                del private[group_name]

    with tempfile.TemporaryDirectory(prefix="labpilot_lyse_script_") as temp_dir:
        result_json = Path(temp_dir) / "result.json"
        dataframe_json = Path(temp_dir) / "dataframe.json"
        dataframe_json.write_text(_dataframe_payload(dataframe), encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "labpilot_ai.lyse_ctrl.lyse_script_worker",
            "--script",
            str(script),
            "--routine-sha256", digest,
            "--mode",
            str(mode),
            "--h5-path",
            str(h5_path or ""),
            "--meta-h5-path",
            str(meta_h5_path or ""),
            "--dataframe-json-file",
            str(dataframe_json),
            "--params-json",
            json.dumps(params or {}, ensure_ascii=False),
            "--result-json",
            str(result_json),
        ]
        env = {
            **dict(os.environ),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "MPLBACKEND": "Agg",
        }
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_s,
        )
        payload = {}
        if result_json.exists():
            payload = json.loads(result_json.read_text(encoding="utf-8"))
        if completed.returncode != 0 or not payload.get("ok"):
            raise LyseScriptError(
                payload.get("error") or f"lyse script failed with exit code {completed.returncode}",
                stdout=completed.stdout,
                stderr=completed.stderr,
                traceback_text=payload.get("traceback", ""),
            )

    result = dict(payload.get("results", {}) or {})
    if mode == "single" and h5_path:
        result.update(read_results_group(h5_path, script_name=script.stem))
    return {
        "status": "ok",
        "mode": mode,
        "script": str(script),
        "results": result,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
