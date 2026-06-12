from labpilot_ai.ai.error_advisor import advise_error
from labpilot_ai.ai.prompt_builder import build_command_prompt
from labpilot_ai.config.registry_editor import parse_bool
from labpilot_ai.experiment_log.generator import generate_experiment_log
from labpilot_ai.safety.validator import normalize_bool


def test_core_dependencies_do_not_claim_labscript_suite_packages():
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with open("pyproject.toml", "rb") as stream:
        pyproject = tomllib.load(stream)
    dependencies = pyproject["project"]["dependencies"]
    normalized = [item.lower().replace("_", "-") for item in dependencies]
    blocked_defaults = ["labscript-suite", "labscript ", "runmanager", "blacs", "lyse", "labscript-utils"]

    assert not any(any(dep.startswith(name) for name in blocked_defaults) for dep in normalized)
    assert any(dep.startswith("numpy") and "<3" in dep for dep in normalized)
    assert any(dep.startswith("pandas") and "<3" in dep for dep in normalized)
    assert any(dep.startswith("pyqt5") and "<6" in dep for dep in normalized)
    assert "labscript" in pyproject["project"]["optional-dependencies"]


def test_bool_parsing_supports_clear_english_and_chinese_terms():
    for value in ["true", "on", "enable", "打开", "开启", "启用", "是"]:
        assert normalize_bool(value) is True
        assert parse_bool(value) is True
    for value in ["false", "off", "disable", "关闭", "禁用", "否"]:
        assert normalize_bool(value) is False
        assert parse_bool(value) is False


def test_command_prompt_uses_current_type_schema():
    prompt = build_command_prompt({"do_Rabi": {"type": "bool"}}, project_context="Rabi sequence context")
    assert '"type": "set_global"' in prompt
    assert "Every action must use the field name \"type\"" in prompt
    assert '"action": "set_global"' not in prompt
    assert "Rabi sequence context" in prompt


def test_experiment_log_includes_active_paths_and_h5_folder():
    text = generate_experiment_log(
        {
            "date": "2026-06-10",
            "sequence_path": "E:/lab/sequence.py",
            "connection_table_path": "E:/lab/connection_table.py",
            "h5_output_dir": "E:/lab/data",
            "knowledge_context": "Rabi snippet",
        },
        output_format="markdown",
        length_mode="full",
    )
    assert "Active sequence" in text
    assert "Active connection table" in text
    assert "H5 output folder" in text
    assert "E:/lab/data" in text


def test_error_advisor_explains_encoding_and_dependency_failures():
    advice = advise_error("UnicodeDecodeError: utf-8 codec failed")
    assert "encoding" in advice.lower() or "utf-8" in advice.lower()
    advice = advise_error("ModuleNotFoundError: No module named 'pypdf'")
    assert "missing optional dependency" in advice or "pypdf" in advice
