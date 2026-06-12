from labpilot_ai.co_sequence.log_store import CodeChangeLogStore
from labpilot_ai.co_sequence.patch_validator import (
    apply_patch_plan,
    consistency_warnings,
    make_unified_diff,
    validate_patch_plan,
)
from labpilot_ai.directory.labscript_paths import field_file_filter, read_runmanager_autoload_paths
from labpilot_ai.directory.path_registry import DIRECTORY_FIELDS, default_directory_settings, validate_directory_settings
from labpilot_ai.experiment_log.generator import generate_experiment_log, save_experiment_log
from labpilot_ai.runmanager_ctrl.backend import RunmanagerBackend
from labpilot_ai.storage.database import LabPilotDatabase


def _plan_for(path, old_text, new_text):
    return {
        "summary": "update sequence",
        "risk_level": "low",
        "files": [{"path": str(path), "unified_diff": make_unified_diff(old_text, new_text, path)}],
        "color_tags": ["yellow: timing"],
    }


def test_co_sequence_patch_allows_only_selected_files_and_applies_with_backup(tmp_path):
    sequence = tmp_path / "rabi.py"
    connection = tmp_path / "connection_table.py"
    sequence.write_text("camera.expose()\n", encoding="utf-8")
    connection.write_text("camera = object()\n", encoding="utf-8")
    plan = _plan_for(sequence, "camera.expose()\n", "camera.expose()\nprint('done')\n")

    result = validate_patch_plan(plan, sequence, connection)
    assert result.ok
    applied = apply_patch_plan(plan, sequence, connection)
    assert "print('done')" in sequence.read_text(encoding="utf-8")
    assert applied["applied"][0]["backup_path"]

    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    bad = _plan_for(outside, "x = 1\n", "x = 2\n")
    bad_result = validate_patch_plan(bad, sequence, connection)
    assert not bad_result.ok
    assert "not one of the selected" in bad_result.errors[0]


def test_co_sequence_syntax_and_consistency_warnings(tmp_path):
    sequence = tmp_path / "seq.py"
    connection = tmp_path / "connection_table.py"
    sequence.write_text("camera.expose()\n", encoding="utf-8")
    connection.write_text("laser = object()\n", encoding="utf-8")
    assert consistency_warnings(sequence.read_text(encoding="utf-8"), connection.read_text(encoding="utf-8"))

    plan = _plan_for(sequence, "camera.expose()\n", "camera.expose(\n")
    result = validate_patch_plan(plan, sequence, connection)
    assert not result.ok
    assert any("syntax error" in error.lower() for error in result.errors)


def test_co_sequence_repairs_unique_context_insertion(tmp_path):
    sequence = tmp_path / "seq.py"
    connection = tmp_path / "connection_table.py"
    old_text = (
        "if do_cleanup:\n"
        "    rf_switch.go_low(t)\n"
        "    probe_shutter.go_low(t)\n"
        "    repump_shutter.go_low(t)\n"
        "    static_shutter.go_low()\n"
        "\n"
        "stop(t + 1e-3)\n"
    )
    sequence.write_text(old_text, encoding="utf-8")
    connection.write_text("rf_switch = object()\n", encoding="utf-8")
    # The LLM omitted the intervening static_shutter line from its context.
    # LabPilot should repair this only because the before/after anchors are unique.
    diff_text = (
        f"--- a/{sequence}\n"
        f"+++ b/{sequence}\n"
        "@@ -2,5 +2,6 @@\n"
        "     rf_switch.go_low(t)\n"
        "     probe_shutter.go_low(t)\n"
        "     repump_shutter.go_low(t)\n"
        "+    t += 10e-3\n"
        " stop(t + 1e-3)\n"
    )
    plan = {"summary": "add wait", "files": [{"path": str(sequence), "unified_diff": diff_text}]}

    result = validate_patch_plan(plan, sequence, connection)

    assert result.ok
    assert any("unique-context insertion" in warning for warning in result.warnings)
    repaired = result.previews[0]["new_text"]
    assert "static_shutter.go_low()\n\n    t += 10e-3\nstop" in repaired


def test_code_change_log_store_records_color_tags(tmp_path):
    store = CodeChangeLogStore(tmp_path / "logs")
    out = store.append({"summary": "changed Rabi timing", "status": "applied", "color_tags": ["red: hardware"]})
    assert out["summary_path"]
    records = store.records_for_date(out["record"]["created_at"][:10])
    assert records[0]["color_tags"] == ["red: hardware"]


def test_directory_defaults_and_validation(tmp_path):
    seq_dir = tmp_path / "sequences"
    seq_dir.mkdir()
    seq_file = seq_dir / "rabi.py"
    seq_file.write_text("x = 1\n", encoding="utf-8")
    settings = default_directory_settings({"sequence_dir": str(seq_dir), "connection_table": str(seq_file)})
    assert settings["active_sequence_file"].endswith("rabi.py")
    messages = validate_directory_settings(settings, project_dir=tmp_path)
    assert not any(message["level"] == "error" for message in messages)


def test_runmanager_globals_path_is_hdf5_and_ini_detection(tmp_path):
    sequence = tmp_path / "sequence.py"
    sequence.write_text("start()\nstop(1)\n", encoding="utf-8")
    globals_h5 = tmp_path / "globals.h5"
    globals_h5.write_bytes(b"fake")
    bad_globals = tmp_path / "globals.py"
    bad_globals.write_text("x = 1\n", encoding="utf-8")
    ini = tmp_path / "runmanager.ini"
    ini.write_text(
        "[runmanager_state]\n"
        f"h5_files_open = [{str(globals_h5)!r}]\n"
        "active_groups = []\n"
        f"groups_open = [({str(globals_h5)!r}, 'default')]\n"
        f"current_labscript_file = {str(sequence)!r}\n"
        "shot_output_folder = ''\n",
        encoding="utf-8",
    )

    paths, messages = read_runmanager_autoload_paths(ini)

    assert paths["active_sequence_file"] == str(sequence)
    assert paths["runmanager_globals_path"] == str(globals_h5)
    assert any("runmanager autoload" in message for message in messages)
    assert any(item["key"] == "runmanager_globals_path" and item["kind"] == "hdf5" for item in DIRECTORY_FIELDS)
    assert "*.h5" in field_file_filter("runmanager_globals_path")

    errors = validate_directory_settings({"runmanager_globals_path": str(bad_globals)}, project_dir=tmp_path)
    assert any(message["level"] == "error" and "Expected extension" in message["message"] for message in errors)


def test_runmanager_backend_mock_path_methods():
    backend = RunmanagerBackend(mock=True)
    backend.set_labscript_file("E:/lab/sequence.py")
    backend.set_shot_output_folder("E:/lab/data")
    assert backend.get_labscript_file() == "E:/lab/sequence.py"
    assert backend.get_shot_output_folder() == "E:/lab/data"


def test_experiment_log_formats_and_database_records(tmp_path):
    db = LabPilotDatabase(tmp_path / "state.sqlite")
    db.log_command_record("parse_ok", "run Rabi", {"user_text": "run Rabi"})
    db.log_code_change_record("applied", "changed sequence", {"summary": "changed sequence"})
    data = {
        "date": "2026-06-10",
        "command_records": db.list_command_records(),
        "code_change_records": db.list_code_change_records(),
        "error_records": [{"severity": "warning", "kind": "lyse", "title": "fit warning", "message": "no scipy"}],
        "knowledge_context": "Rabi snippet",
    }
    markdown = generate_experiment_log(data, output_format="markdown", length_mode="full")
    latex = generate_experiment_log(data, output_format="latex", length_mode="full")
    dokuwiki = generate_experiment_log(data, output_format="dokuwiki", length_mode="full")
    assert "# LabPilot experiment log" in markdown
    assert "\\section*" in latex
    assert "======" in dokuwiki
    path = save_experiment_log(tmp_path, "2026-06-10", markdown, "markdown")
    assert path.exists()
