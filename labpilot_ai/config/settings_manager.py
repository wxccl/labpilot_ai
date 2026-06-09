from pathlib import Path
import yaml
from labpilot_ai.utils.paths import default_config_dir


class SettingsManager:
    def __init__(self, project_dir=None):
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.config_dir = default_config_dir()

    def path(self, filename: str) -> Path:
        local = self.project_dir / "configs" / filename
        if local.exists():
            return local
        return self.config_dir / filename

    def load_yaml(self, filename: str) -> dict:
        path = self.path(filename)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_global_registry(self) -> dict:
        return self.load_yaml("global_registry.yaml")

    def load_blacs_registry(self) -> dict:
        return self.load_yaml("blacs_manual_registry.yaml")

    def load_lyse_registry(self) -> dict:
        return self.load_yaml("lyse_registry.yaml")
