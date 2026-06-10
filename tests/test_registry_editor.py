from pathlib import Path

from labpilot_ai.config.registry_editor import (
    PROJECT_PATH_FIELDS,
    build_blacs_registry,
    build_global_registry,
    build_lyse_registry,
    flatten_lyse_registry,
    validate_blacs_registry,
    validate_global_registry,
    validate_lyse_registry,
)
from labpilot_ai.config.settings_manager import SettingsManager
from labpilot_ai.safety.validator import SafetyValidator
from labpilot_ai.voice.lexicon import VoiceLexicon


def test_registry_yaml_roundtrip_and_runtime_refresh_inputs(tmp_path):
    settings = SettingsManager(project_dir=tmp_path)
    global_registry = build_global_registry(
        [
            {
                "name": "tof_ms",
                "type": "float",
                "min": "0",
                "max": "20",
                "allow_array": "true",
                "max_points": "10",
                "risk": "low",
                "aliases": "TOF, 飞行时间",
                "description": "time of flight",
            }
        ]
    )
    blacs_registry = build_blacs_registry(
        [
            {
                "name": "bias_v",
                "type": "float",
                "device": "NI",
                "channel": "ao0",
                "min": "-1",
                "max": "1",
                "risk": "medium",
                "aliases": "bias",
            }
        ]
    )
    single = tmp_path / "single.py"
    single.write_text("def analyze(h5_path, params=None):\n    return {'N_total': 1}\n", encoding="utf-8")
    lyse_registry = build_lyse_registry(
        [
            {
                "group": "single",
                "name": "count_atoms",
                "path": str(single),
                "enabled_by_default": "true",
                "order": "5",
                "outputs": "N_total",
            }
        ]
    )

    settings.save_global_registry(global_registry)
    settings.save_global_registry(global_registry)
    settings.save_blacs_registry(blacs_registry)
    settings.save_lyse_registry(lyse_registry)

    assert (tmp_path / "configs" / "global_registry.yaml.bak").exists()
    loaded_globals = settings.load_global_registry()
    loaded_blacs = settings.load_blacs_registry()
    loaded_lyse = settings.load_lyse_registry()
    assert loaded_globals["tof_ms"]["aliases"] == ["TOF", "飞行时间"]
    assert loaded_globals["tof_ms"]["allow_array"] is True
    assert loaded_lyse["single_modules"]["count_atoms"]["order"] == 5

    validator = SafetyValidator(loaded_globals, loaded_blacs, loaded_lyse)
    safe = validator.validate_command({"actions": [{"type": "set_global", "name": "tof_ms", "value": 3.0}]})
    assert safe["actions"][0]["name"] == "tof_ms"
    lexicon = VoiceLexicon.from_registries(loaded_globals, loaded_blacs, loaded_lyse)
    assert "TOF" in lexicon.prompt()


def test_registry_validation_errors(tmp_path):
    missing = tmp_path / "missing.py"
    errors = validate_global_registry({"bad": {"type": "complex", "min": 2, "max": 1, "risk": "wild"}})
    assert any("unknown type" in error for error in errors)
    assert any("min is greater" in error for error in errors)
    assert any("risk" in error for error in errors)

    blacs_errors = validate_blacs_registry({"bad": {"type": "float", "device": "", "channel": ""}})
    assert any("device and channel" in error for error in blacs_errors)

    lyse_errors = validate_lyse_registry(
        {"single_modules": {"bad": {"path": str(missing), "order": "first"}}, "multi_modules": {}},
        base_dir=tmp_path,
    )
    assert any("order must be an integer" in error for error in lyse_errors)
    assert any("module path does not exist" in error for error in lyse_errors)


def test_lyse_flatten_roundtrip(tmp_path):
    module = tmp_path / "multi.py"
    module.write_text("def analyze(dataframe, params=None):\n    return {}\n", encoding="utf-8")
    registry = {
        "single_modules": {},
        "multi_modules": {
            "m": {
                "path": str(module),
                "enabled_by_default": False,
                "order": 3,
                "params": {"bin": 10},
                "outputs": ["mean_N"],
            }
        },
    }
    rebuilt = build_lyse_registry(flatten_lyse_registry(registry))
    assert rebuilt["multi_modules"]["m"]["outputs"] == ["mean_N"]
    assert rebuilt["multi_modules"]["m"]["params"] == {"bin": 10}


def test_template_copy_does_not_overwrite_existing_config(tmp_path):
    settings = SettingsManager(project_dir=tmp_path)
    local = tmp_path / "configs" / "project_settings.yaml"
    local.parent.mkdir(parents=True)
    local.write_text("custom: true\n", encoding="utf-8")

    copied = settings.ensure_project_templates(include_manual=False)
    assert local.read_text(encoding="utf-8") == "custom: true\n"
    assert (tmp_path / "configs" / "global_registry.yaml").exists()
    assert all(Path(path).name != "project_settings.yaml" for path in copied)


def test_project_path_fields_include_knowledge_sources():
    for field in [
        "sequence_dir",
        "active_sequence_file",
        "connection_table",
        "active_connection_table",
        "co_sequence_log_dir",
        "experiment_log_dir",
        "command_log_dir",
        "labscript_source_dir",
        "manual_dir",
        "paper_dir",
        "knowledge_db_path",
        "knowledge_context_enabled",
    ]:
        assert field in PROJECT_PATH_FIELDS
