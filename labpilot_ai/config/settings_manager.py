from pathlib import Path
import shutil
import yaml
from labpilot_ai.utils.paths import default_config_dir


class SettingsManager:
    def __init__(self, project_dir=None):
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.config_dir = default_config_dir()
        self.template_dir = Path(__file__).resolve().parents[1] / "templates"

    def path(self, filename: str) -> Path:
        local = self.project_dir / "configs" / filename
        if local.exists():
            return local
        dev_default = self.config_dir / filename
        if dev_default.exists():
            return dev_default
        return self.template_dir / "configs" / filename

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

    def load_project_settings(self) -> dict:
        return self.load_yaml("project_settings.yaml")

    def save_yaml(self, filename: str, values: dict, backup=True):
        path = self.project_dir / "configs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(values or {}, f, allow_unicode=True, sort_keys=False)
        return path

    def save_global_registry(self, values: dict):
        return self.save_yaml("global_registry.yaml", values)

    def save_blacs_registry(self, values: dict):
        return self.save_yaml("blacs_manual_registry.yaml", values)

    def save_lyse_registry(self, values: dict):
        return self.save_yaml("lyse_registry.yaml", values)

    def save_project_settings(self, values: dict):
        return self.save_yaml("project_settings.yaml", values)

    def init_project_templates(self, include_manual=True):
        copied = []
        for filename in [
            "project_settings.yaml",
            "global_registry.yaml",
            "blacs_manual_registry.yaml",
            "lyse_registry.yaml",
            "safety_rules.yaml",
            "voice_lexicon.yaml",
        ]:
            src = self.path(filename)
            dst = self.project_dir / "configs" / filename
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(dst)
        for group in ["single_modules", "multi_modules"]:
            src_dir = self.template_dir / "plugins" / group
            if not src_dir.exists():
                src_dir = self.project_dir / "plugins" / group
            dst_dir = self.project_dir / "plugins" / group
            if src_dir.exists():
                dst_dir.mkdir(parents=True, exist_ok=True)
                for src in src_dir.glob("*.py"):
                    dst = dst_dir / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        copied.append(dst)
        if include_manual:
            src_manual = self.template_dir / "manual"
            dst_manual = self.project_dir / "manual"
            if src_manual.exists() and not dst_manual.exists():
                shutil.copytree(src_manual, dst_manual)
                copied.append(dst_manual)
        return copied

    def ensure_project_templates(self, include_manual=True):
        return self.init_project_templates(include_manual=include_manual)
