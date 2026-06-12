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
