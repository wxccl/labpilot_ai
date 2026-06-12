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
