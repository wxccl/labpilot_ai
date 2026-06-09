from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_dir() -> Path:
    # During editable development, configs live at repo_root/configs.
    return project_root() / "configs"
