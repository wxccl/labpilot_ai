def test_main_window_registry_widgets_import():
    from labpilot_ai.app.main_window import MainWindow, ProjectPathsWidget, RegistryEditorWidget

    assert MainWindow is not None
    assert RegistryEditorWidget is not None
    assert ProjectPathsWidget is not None


def test_error_center_import():
    from labpilot_ai.app.error_center import ErrorCenter, ErrorRecord

    assert ErrorCenter is not None
    assert ErrorRecord is not None


def test_release_page_backends_import():
    from labpilot_ai.co_sequence import validate_patch_plan
    from labpilot_ai.directory import DIRECTORY_FIELDS
    from labpilot_ai.experiment_log import generate_experiment_log

    assert validate_patch_plan is not None
    assert DIRECTORY_FIELDS
    assert generate_experiment_log is not None


def test_main_window_llm_client_uses_ui_runtime_fields():
    from labpilot_ai.app.main_window import MainWindow

    class Edit:
        def __init__(self, value):
            self.value = value

        def text(self):
            return self.value

    window = MainWindow.__new__(MainWindow)
    window.project_settings = {"ai": {"base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash"}}
    window.runtime_api_key = ""
    window.runtime_api_key_source = "missing"
    window.api_key = Edit("sk-ui-test")
    window.base_url = Edit("https://api.example.test/v1")
    window.model = Edit("example-model")

    client = MainWindow._make_llm_client(window)

    assert client.api_key == "sk-ui-test"
    assert client.api_key_source == "UI field"
    assert client.base_url == "https://api.example.test/v1"
    assert client.model == "example-model"


def test_user_text_requests_shot_is_explicit_only():
    from labpilot_ai.app.main_window import user_text_requests_shot

    assert not user_text_requests_shot("设置 duration_tof_ms 为 17 ms")
    assert not user_text_requests_shot("打开 RF 开关")
    assert not user_text_requests_shot("set MW_power_W to 0.05")
    assert user_text_requests_shot("设置 TOF 为 17 ms 并运行一次")
    assert user_text_requests_shot("run a shot after setting TOF")
    assert not user_text_requests_shot("runmanager 参数刷新，不要运行")


def test_unrequested_engage_is_removed_from_llm_output():
    from labpilot_ai.app.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    window.log = lambda *_args, **_kwargs: None
    command = {
        "actions": [
            {"type": "set_global", "name": "duration_tof_ms", "value": 17},
            {"type": "engage"},
        ]
    }
    stripped, requested = MainWindow._strip_unrequested_engage(window, command, "设置 TOF 为 17 ms")

    assert requested is False
    assert stripped["actions"] == [{"type": "set_global", "name": "duration_tof_ms", "value": 17}]

    kept, requested = MainWindow._strip_unrequested_engage(window, command, "设置 TOF 为 17 ms 并运行一次")
    assert requested is True
    assert kept["actions"][-1]["type"] == "engage"


def test_lyse_module_action_names_fall_back_to_checked_rows():
    from PyQt5 import QtCore, QtWidgets

    from labpilot_ai.app.main_window import MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    table = QtWidgets.QTableWidget(2, 2)
    for row, name in enumerate(["single_a", "single_b"]):
        use = QtWidgets.QTableWidgetItem("")
        use.setFlags(use.flags() | QtCore.Qt.ItemIsUserCheckable)
        use.setCheckState(QtCore.Qt.Checked if row == 1 else QtCore.Qt.Unchecked)
        table.setItem(row, 0, use)
        table.setItem(row, 1, QtWidgets.QTableWidgetItem(name))
    table.clearSelection()
    window = MainWindow.__new__(MainWindow)
    window.single_modules = table
    window.multi_modules = QtWidgets.QTableWidget(0, 2)

    assert MainWindow._module_action_names(window, "single_modules") == ["single_b"]


def test_table_columns_are_user_resizable():
    from PyQt5 import QtWidgets

    from labpilot_ai.app.main_window import configure_table_columns

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    table = QtWidgets.QTableWidget(0, 3)
    configure_table_columns(table)

    assert table.horizontalHeader().sectionResizeMode(0) == QtWidgets.QHeaderView.Interactive


def test_lyse_registry_save_refreshes_module_tables(tmp_path):
    from types import SimpleNamespace

    from PyQt5 import QtWidgets

    from labpilot_ai.app.main_window import MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    module_path = tmp_path / "single_a.py"
    module_path.write_text("def run(path):\n    return {}\n", encoding="utf-8")
    saved = []
    reloads = []

    window = MainWindow.__new__(MainWindow)
    window.settings = SimpleNamespace(
        project_dir=tmp_path,
        save_lyse_registry=lambda registry: saved.append(registry.copy()),
    )
    window.lyse_registry = {
        "single_modules": {
            "single_a": {
                "path": str(module_path),
                "mode": "labpilot_module",
                "enabled_by_default": True,
                "order": 10,
            }
        },
        "multi_modules": {},
    }
    window.log = lambda *_args, **_kwargs: None
    window.reload_runtime_config = lambda: reloads.append("reloaded")
    window.single_modules = MainWindow._make_lyse_module_table(window, "single_modules")
    window.multi_modules = MainWindow._make_lyse_module_table(window, "multi_modules")

    MainWindow._save_lyse_registry_and_refresh(window, "single_modules", ["single_a"])

    assert saved
    assert reloads == ["reloaded"]
    assert window.single_modules.rowCount() == 1
    assert window.single_modules.item(0, 1).text() == "single_a"
    assert window.single_modules.currentRow() == 0
