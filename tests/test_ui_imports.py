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
