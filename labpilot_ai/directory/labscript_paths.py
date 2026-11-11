from __future__ import annotations

import ast
import configparser
from pathlib import Path
from typing import Any


HDF5_SUFFIXES = {".h5", ".hdf5"}
PYTHON_SUFFIXES = {".py"}


def _as_path_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return str(Path(text))


def _literal(value: str, default=None):
    try:
        return ast.literal_eval(value)
    except Exception:
        return default


def _first_path_from_group_records(records) -> str:
    if isinstance(records, dict):
        records = list(records.items())
    if not isinstance(records, (list, tuple)):
        return ""
    for item in records:
        if isinstance(item, (list, tuple)) and item:
            return _as_path_text(item[0])
        if isinstance(item, str):
            return _as_path_text(item)
    return ""


def read_labconfig_paths() -> tuple[dict[str, str], list[str]]:
    """Read stable labscript-suite path hints from LabConfig.

    The function is intentionally optional-dependency safe so the LabPilot UI can
    start on development computers without labscript installed.
    """
    out: dict[str, str] = {}
    messages: list[str] = []
    try:
        from labscript_utils.labconfig import LabConfig

        config = LabConfig()
    except Exception as exc:
        return out, [f"LabConfig unavailable: {exc}"]

    def get(section: str, option: str) -> str:
        try:
            return str(config.get(section, option, fallback="") or "").strip()
        except Exception:
            return ""

    path_map = {
        "sequence_dir": get("paths", "labscriptlib"),
        "h5_output_dir": get("paths", "experiment_shot_storage"),
        "labscript_source_dir": get("paths", "labscript_suite"),
        "single_modules_dir": get("paths", "analysislib"),
        "manual_dir": get("paths", "userlib"),
        "active_connection_table": get("paths", "connection_table_py"),
        "connection_table": get("paths", "connection_table_py"),
        "blacs_connection_context_path": get("paths", "connection_table_h5"),
        "runmanager_autoload_config_file": get("runmanager", "autoload_config_file"),
    }
    for key, value in path_map.items():
        if value:
            out[key] = _as_path_text(value)
    if out:
        messages.append("Read labscript LabConfig path hints.")
    return out, messages


def read_runmanager_autoload_paths(path: str | Path | None = None) -> tuple[dict[str, str], list[str]]:
    """Read runmanager's saved UI state for active sequence and globals H5 files."""
    out: dict[str, str] = {}
    messages: list[str] = []
    if not path:
        labconfig, lab_messages = read_labconfig_paths()
        messages.extend(lab_messages)
        path = labconfig.get("runmanager_autoload_config_file")
    if not path:
        return out, messages + ["No runmanager autoload config file configured."]

    path = Path(path)
    if not path.exists():
        return out, messages + [f"Runmanager autoload config does not exist: {path}"]

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section("runmanager_state"):
        return out, messages + [f"No [runmanager_state] section in {path}"]
    state = parser["runmanager_state"]

    current_labscript = _literal(state.get("current_labscript_file", ""), "")
    if current_labscript:
        out["active_sequence_file"] = _as_path_text(current_labscript)
        seq_dir = str(Path(out["active_sequence_file"]).parent)
        if seq_dir:
            out["sequence_dir"] = seq_dir

    shot_output = _literal(state.get("shot_output_folder", ""), "")
    if shot_output:
        out["h5_output_dir"] = _as_path_text(shot_output)

    active_groups = _literal(state.get("active_groups", ""), [])
    groups_open = _literal(state.get("groups_open", ""), [])
    h5_files_open = _literal(state.get("h5_files_open", ""), [])
    globals_path = (
        _first_path_from_group_records(active_groups)
        or _first_path_from_group_records(groups_open)
        or _first_path_from_group_records(h5_files_open)
    )
    if globals_path:
        out["runmanager_globals_path"] = globals_path
    messages.append(f"Read runmanager autoload state: {path}")
    return out, messages


def read_running_runmanager_paths(runmanager_backend) -> tuple[dict[str, str], list[str]]:
    """Read active runtime paths through runmanager.remote where supported."""
    out: dict[str, str] = {}
    messages: list[str] = []
    if runmanager_backend is None:
        return out, ["No runmanager backend available."]
    try:
        labscript_file = runmanager_backend.get_labscript_file()
        if labscript_file:
            out["active_sequence_file"] = _as_path_text(labscript_file)
            out["sequence_dir"] = str(Path(out["active_sequence_file"]).parent)
            messages.append("Read active sequence from runmanager.remote.")
    except Exception as exc:
        messages.append(f"Could not read runmanager labscript file: {exc}")
    try:
        shot_output_folder = runmanager_backend.get_shot_output_folder()
        if shot_output_folder:
            out["h5_output_dir"] = _as_path_text(shot_output_folder)
            messages.append("Read H5 output folder from runmanager.remote.")
    except Exception as exc:
        messages.append(f"Could not read runmanager shot output folder: {exc}")
    return out, messages


def detect_labscript_paths(settings=None, runmanager_backend=None, project_dir=None) -> tuple[dict[str, str], list[str]]:
    """Merge path hints from current settings, runmanager.remote, runmanager.ini and LabConfig."""
    merged = dict(settings or {})
    messages: list[str] = []

    labconfig_paths, labconfig_messages = read_labconfig_paths()
    messages.extend(labconfig_messages)
    for key, value in labconfig_paths.items():
        if key != "runmanager_autoload_config_file" and value and not merged.get(key):
            merged[key] = value

    ini_paths, ini_messages = read_runmanager_autoload_paths(labconfig_paths.get("runmanager_autoload_config_file"))
    messages.extend(ini_messages)
    for key, value in ini_paths.items():
        if value:
            merged[key] = value

    runtime_paths, runtime_messages = read_running_runmanager_paths(runmanager_backend)
    messages.extend(runtime_messages)
    for key, value in runtime_paths.items():
        if value:
            merged[key] = value

    if merged.get("active_sequence_file") and not merged.get("sequence_dir"):
        merged["sequence_dir"] = str(Path(merged["active_sequence_file"]).parent)
    if merged.get("connection_table") and not merged.get("active_connection_table"):
        merged["active_connection_table"] = merged["connection_table"]
    if merged.get("active_connection_table") and not merged.get("connection_table"):
        merged["connection_table"] = merged["active_connection_table"]

    return merged, messages


def field_file_filter(key: str, label: str = "") -> str:
    if key == "runmanager_globals_path":
        return "Runmanager globals HDF5 (*.h5 *.hdf5);;All files (*.*)"
    if key == "blacs_connection_context_path":
        return "Connection table HDF5/Python (*.h5 *.hdf5 *.py);;All files (*.*)"
    if key in {"connection_table", "active_connection_table", "active_sequence_file"}:
        return "Python files (*.py);;All files (*.*)"
    if key == "knowledge_db_path":
        return "SQLite database (*.sqlite *.db);;All files (*.*)"
    return f"{label or 'Files'} (*.*)"


def expected_suffixes_for_key(key: str) -> set[str]:
    if key == "runmanager_globals_path":
        return HDF5_SUFFIXES
    if key in {"connection_table", "active_connection_table", "active_sequence_file"}:
        return PYTHON_SUFFIXES
    if key == "blacs_connection_context_path":
        return HDF5_SUFFIXES | PYTHON_SUFFIXES
    return set()
