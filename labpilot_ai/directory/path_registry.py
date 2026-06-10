from pathlib import Path


DIRECTORY_FIELDS = [
    {
        "key": "sequence_dir",
        "label": "Sequence folder",
        "kind": "dir",
        "meaning": "Folder containing labscript sequence Python files.",
        "source": "runmanager/manual",
    },
    {
        "key": "active_sequence_file",
        "label": "Active sequence file",
        "kind": "file",
        "meaning": "The sequence file Co-Sequence may edit.",
        "source": "runmanager/manual",
    },
    {
        "key": "connection_table",
        "label": "Connection table",
        "kind": "file",
        "meaning": "Labscript connection table used by runmanager/BLACS.",
        "source": "runmanager/manual",
    },
    {
        "key": "active_connection_table",
        "label": "Active connection table",
        "kind": "file",
        "meaning": "The connection table file Co-Sequence may edit.",
        "source": "BLACS/manual",
    },
    {
        "key": "runmanager_globals_path",
        "label": "Runmanager globals",
        "kind": "file",
        "meaning": "Optional path to a runmanager globals file or exported snapshot.",
        "source": "runmanager/manual",
        "optional": True,
    },
    {
        "key": "blacs_connection_context_path",
        "label": "BLACS connection context",
        "kind": "file",
        "meaning": "Optional file used as BLACS connection/device context.",
        "source": "BLACS/manual",
        "optional": True,
    },
    {
        "key": "h5_output_dir",
        "label": "H5 output folder",
        "kind": "dir",
        "meaning": "Folder containing labscript/lyse H5 shot outputs.",
        "source": "lyse/manual",
    },
    {
        "key": "lyse_results_dir",
        "label": "Lyse result folder",
        "kind": "dir",
        "meaning": "Folder for exported merged lyse results and reports.",
        "source": "lyse/manual",
    },
    {
        "key": "single_modules_dir",
        "label": "Lyse single modules",
        "kind": "dir",
        "meaning": "Folder containing optional single-shot lyse modules.",
        "source": "lyse/manual",
    },
    {
        "key": "multi_modules_dir",
        "label": "Lyse multi modules",
        "kind": "dir",
        "meaning": "Folder containing optional multi-shot lyse modules.",
        "source": "lyse/manual",
    },
    {
        "key": "labscript_source_dir",
        "label": "Labscript source folder",
        "kind": "dir",
        "meaning": "Local labscript suite source reference for AI context.",
        "source": "manual",
        "optional": True,
    },
    {
        "key": "manual_dir",
        "label": "Manual folder",
        "kind": "dir",
        "meaning": "Local manuals and lab notes indexed into Knowledge.",
        "source": "manual",
    },
    {
        "key": "paper_dir",
        "label": "Paper folder",
        "kind": "dir",
        "meaning": "Papers and protocol references indexed into Knowledge.",
        "source": "manual",
        "optional": True,
    },
    {
        "key": "knowledge_db_path",
        "label": "Knowledge database",
        "kind": "sqlite",
        "meaning": "SQLite FTS database used by Knowledge search.",
        "source": "LabPilot",
    },
    {
        "key": "co_sequence_log_dir",
        "label": "Co-Sequence logs",
        "kind": "dir",
        "meaning": "Folder for sequence/connection-table code change logs.",
        "source": "LabPilot",
    },
    {
        "key": "experiment_log_dir",
        "label": "Experiment logs",
        "kind": "dir",
        "meaning": "Folder for generated daily experiment logs.",
        "source": "LabPilot",
    },
    {
        "key": "command_log_dir",
        "label": "Command logs",
        "kind": "dir",
        "meaning": "Folder for natural-language command records.",
        "source": "LabPilot",
    },
]


DEFAULT_PATHS = {
    "single_modules_dir": "plugins/single_modules",
    "multi_modules_dir": "plugins/multi_modules",
    "manual_dir": "manual",
    "knowledge_db_path": "labpilot_outputs/knowledge/labpilot_knowledge.sqlite",
    "lyse_results_dir": "labpilot_outputs/lyse_results",
    "co_sequence_log_dir": "labpilot_outputs/co_sequence_logs",
    "experiment_log_dir": "labpilot_outputs/experiment_logs",
    "command_log_dir": "labpilot_outputs/command_logs",
}


def resolve_path(value, project_dir=None):
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = Path(project_dir or Path.cwd()) / path
    return path


def default_directory_settings(settings=None, project_dir=None):
    merged = dict(DEFAULT_PATHS)
    merged.update(settings or {})
    if not merged.get("active_sequence_file") and merged.get("sequence_dir"):
        seq_dir = resolve_path(merged["sequence_dir"], project_dir=project_dir) or Path(merged["sequence_dir"])
        candidates = sorted(seq_dir.glob("*.py")) if seq_dir.exists() and seq_dir.is_dir() else []
        if candidates:
            merged["active_sequence_file"] = str(candidates[0])
    if not merged.get("active_connection_table") and merged.get("connection_table"):
        merged["active_connection_table"] = merged["connection_table"]
    return merged


def validate_directory_settings(settings, project_dir=None):
    settings = default_directory_settings(settings, project_dir=project_dir)
    messages = []
    for field in DIRECTORY_FIELDS:
        key = field["key"]
        value = settings.get(key, "")
        optional = bool(field.get("optional"))
        if not value:
            if not optional:
                messages.append({"key": key, "level": "warning", "message": "Path is empty."})
            continue
        path = resolve_path(value, project_dir=project_dir)
        kind = field["kind"]
        exists = bool(path and path.exists())
        if not exists:
            messages.append({"key": key, "level": "warning", "message": f"Path does not exist: {path}"})
            continue
        if kind == "dir" and not path.is_dir():
            messages.append({"key": key, "level": "error", "message": f"Expected a folder: {path}"})
        elif kind in {"file", "sqlite"} and not path.is_file():
            messages.append({"key": key, "level": "error", "message": f"Expected a file: {path}"})
    return messages
