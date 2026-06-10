from __future__ import annotations

import argparse
import contextlib
import json
import os
import runpy
import sys
import traceback
import types
from pathlib import Path

import pandas as pd

from labpilot_ai.bootstrap_labscript import install_h5_lock
from labpilot_ai.utils.json_utils import to_jsonable


class WorkerRun:
    def __init__(self, h5_path, script_name, results):
        self.h5_path = str(h5_path or "")
        self.script_name = script_name
        self.results = results

    def save_result(self, name, value, *args, **kwargs):
        self.results[str(name)] = to_jsonable(value)
        if self.h5_path:
            _write_result_to_h5(self.h5_path, self.script_name, str(name), value)

    def save_result_array(self, name, value, *args, **kwargs):
        self.save_result(name, value, *args, **kwargs)

    def get_result(self, name, default=None):
        return self.results.get(str(name), default)


def _write_result_to_h5(h5_path, script_name, name, value):
    install_h5_lock(verbose=False)
    import h5py

    path = Path(h5_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "a") as handle:
        group = handle.require_group("results").require_group(script_name)
        if name in group:
            del group[name]
        try:
            group.create_dataset(name, data=value)
        except TypeError:
            group.attrs[name] = json.dumps(to_jsonable(value), ensure_ascii=False)


def _load_dataframe(dataframe_json):
    if not dataframe_json:
        return pd.DataFrame()
    payload = json.loads(dataframe_json)
    return pd.DataFrame(**payload)


def _make_lyse_module(path_value, dataframe, script_name, results):
    module = types.ModuleType("lyse")
    module.path = str(path_value or "")
    module.routine_storage = {}

    def data(*args, **kwargs):
        return dataframe.copy()

    def run_factory(h5_path=None, *args, **kwargs):
        return WorkerRun(h5_path or module.path, script_name, results)

    module.data = data
    module.Run = run_factory
    module.save_result = lambda name, value, *args, **kwargs: WorkerRun(module.path, script_name, results).save_result(name, value)
    module.save_result_array = lambda name, value, *args, **kwargs: WorkerRun(module.path, script_name, results).save_result_array(name, value)
    return module


def _write_payload(path, payload):
    Path(path).write_text(json.dumps(to_jsonable(payload), ensure_ascii=False), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--mode", choices=["single", "multi"], required=True)
    parser.add_argument("--h5-path", default="")
    parser.add_argument("--meta-h5-path", default="")
    parser.add_argument("--dataframe-json", default="")
    parser.add_argument("--params-json", default="{}")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args(argv)

    script = Path(args.script).resolve()
    script_name = script.stem
    path_value = args.h5_path if args.mode == "single" else args.meta_h5_path
    dataframe = _load_dataframe(args.dataframe_json)
    results = {}
    payload = {"ok": False, "results": results, "script": str(script)}

    try:
        lyse_module = _make_lyse_module(path_value, dataframe, script_name, results)
        sys.modules["lyse"] = lyse_module
        sys.path.insert(0, str(script.parent))
        globals_for_script = {
            "path": str(path_value or ""),
            "params": json.loads(args.params_json or "{}"),
        }
        old_cwd = Path.cwd()
        try:
            os.chdir(script.parent)
            with contextlib.redirect_stdout(sys.stderr):
                runpy.run_path(str(script), init_globals=globals_for_script, run_name="__main__")
        finally:
            os.chdir(old_cwd)
        payload.update({"ok": True, "results": results})
    except Exception as exc:
        payload.update({"ok": False, "error": repr(exc), "traceback": traceback.format_exc(), "results": results})
    finally:
        _write_payload(args.result_json, payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
