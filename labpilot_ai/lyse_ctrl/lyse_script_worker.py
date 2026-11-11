from __future__ import annotations

import argparse
import contextlib
import importlib.util
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

    def get_image(self, orientation, label, image):
        if not self.h5_path:
            raise FileNotFoundError("No H5 path is available for lyse Run.get_image().")
        install_h5_lock(verbose=False)
        import h5py

        with h5py.File(self.h5_path, "r") as handle:
            path = f"/images/{orientation}/{label}/{image}"
            if path not in handle:
                raise KeyError(f"Image not found in H5: {path}")
            return handle[path][()]


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


def _with_lyse_tuple_columns(dataframe):
    if dataframe is None or dataframe.empty:
        return pd.DataFrame()
    out = dataframe.copy()
    additions = {}
    for column in list(out.columns):
        if not isinstance(column, str):
            continue
        if column.startswith("results."):
            parts = column.split(".", 2)
            if len(parts) == 3:
                additions[(parts[1], parts[2], "", "")] = out[column]
        elif column.startswith("globals."):
            parts = column.split(".", 2)
            if len(parts) == 3:
                additions[("globals", parts[2], "", "")] = out[column]
                bare_name = parts[2].split(".")[-1]
                if bare_name and bare_name not in out.columns:
                    additions[bare_name] = out[column]
            elif len(parts) == 2:
                bare_name = parts[1].split(".")[-1]
                if bare_name and bare_name not in out.columns:
                    additions[bare_name] = out[column]
    for column, values in additions.items():
        if column not in out.columns:
            out[column] = values
    return out


def _install_runtime_control_fallback():
    try:
        if importlib.util.find_spec("lyse_runtime_control.lyse_runtime_config") is not None:
            return
    except ModuleNotFoundError:
        pass

    package = types.ModuleType("lyse_runtime_control")
    config = types.ModuleType("lyse_runtime_control.lyse_runtime_config")

    def load_runtime_config():
        return {}

    def get_analysis_switches(_runtime_config):
        return {
            "do_SG_F1_masked": False,
            "update_centers_json": False,
            "do_Gaussian_fit_MOT_shape": False,
            "do_double_Gaussian_fit_MOT_shape": False,
            "do_save_OD_roi": False,
            "do_circular": False,
        }

    def get_physics(_runtime_config):
        return {
            "sigma_0": 1.938e-13,
            "detuning": 0,
            "magnification": 1.0,
            "gamma": 6,
            "quantum_efficiency": 0.24,
            "pixel_size": 5.86e-6,
            "gain_in_dB": 0,
            "ratio_fluorescence": 1,
        }

    def get_andor_fl(_runtime_config):
        return {
            "Andor_FL_img_mini_count": 489,
            "Andor_FL_img_sigma": 2.4,
            "Andor_FL_img_truncate": 5.0,
            "Andor_FL_img_threshold": 0.0,
        }

    def get_flir_abs(_runtime_config):
        return {"scale": 1}

    def build_roi(_runtime_config, np_module=None):
        np_module = np_module or __import__("numpy")
        return {
            "Flir": np_module.array([1024, 1024, 2048, 2048]),
            "Andor": np_module.array([1024, 1024, 2048, 2048]),
        }

    def build_od_plots(_runtime_config, _profile, images, np_module=None):
        return [(value, key, None, None) for key, value in dict(images or {}).items()]

    def get_center_config_path(_runtime_config, profile):
        return f"labpilot_runtime_{profile}_centers.json"

    def get_plot_cmap(_runtime_config, _profile, default="viridis"):
        return default

    def get_spin_parameters(_runtime_config, _profile, data, np_module=None, **_kwargs):
        np_module = np_module or __import__("numpy")
        od = (data or {}).get("OD_corrected")
        if od is None:
            od = np_module.zeros((10, 10))
        return {
            "filter_OD": od,
            "filter_OD_threshold": 0,
            "fit_mod": "CM",
            "minima_fit_displacement": 0,
            "select_mode": "origin",
            "vmin": None,
            "vmax": None,
            "vmin2": None,
            "vmax2": None,
            "vmin3": None,
            "vmax3": None,
            "vmin4": None,
            "vmax4": None,
            "y_scale": 1,
            "radius": 10,
            "fit_hw": 10,
            "n_fit_threshold": 0,
            "pm_x_scale": 1,
            "pm_x_pixel": 0,
        }

    for name, value in {
        "load_runtime_config": load_runtime_config,
        "get_analysis_switches": get_analysis_switches,
        "get_physics": get_physics,
        "get_andor_fl": get_andor_fl,
        "get_flir_abs": get_flir_abs,
        "build_roi": build_roi,
        "build_od_plots": build_od_plots,
        "get_center_config_path": get_center_config_path,
        "get_plot_cmap": get_plot_cmap,
        "get_spin_parameters": get_spin_parameters,
    }.items():
        setattr(config, name, value)

    package.lyse_runtime_config = config
    sys.modules.setdefault("lyse_runtime_control", package)
    sys.modules.setdefault("lyse_runtime_control.lyse_runtime_config", config)


def _make_lyse_module(path_value, dataframe, script_name, results):
    module = types.ModuleType("lyse")
    module.path = str(path_value or "")
    module.routine_storage = {}

    def data(*args, **kwargs):
        return _with_lyse_tuple_columns(dataframe)

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
    parser.add_argument("--dataframe-json-file", default="")
    parser.add_argument("--params-json", default="{}")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args(argv)

    script = Path(args.script).resolve()
    script_name = script.stem
    path_value = args.h5_path if args.mode == "single" else args.meta_h5_path
    dataframe_json = args.dataframe_json
    if args.dataframe_json_file:
        dataframe_json = Path(args.dataframe_json_file).read_text(encoding="utf-8")
    dataframe = _load_dataframe(dataframe_json)
    results = {}
    payload = {"ok": False, "results": results, "script": str(script)}

    try:
        _install_runtime_control_fallback()
        lyse_module = _make_lyse_module(path_value, dataframe, script_name, results)
        sys.modules["lyse"] = lyse_module
        sys.path.insert(0, str(script.parent))
        install_h5_lock(verbose=False)
        import h5py
        globals_for_script = {
            "path": str(path_value or ""),
            "params": json.loads(args.params_json or "{}"),
            "h5py": h5py,
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
