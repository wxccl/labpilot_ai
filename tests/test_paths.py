from labpilot_ai.utils.paths import app_icon_path


def test_app_icon_path_points_to_label_png():
    path = app_icon_path()
    assert path.name == "label.png"
    assert path.exists()
