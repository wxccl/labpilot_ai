import importlib.util
from pathlib import Path

from labpilot_ai.utils.paths import project_root


class LyseModuleError(RuntimeError):
    pass


class ModuleManager:
    def __init__(self, registry: dict, base_dirs=None):
        self.registry = registry or {}
        root = project_root()
        self.base_dirs = [Path.cwd(), root]
        if base_dirs:
            self.base_dirs.extend(Path(p) for p in base_dirs)

    def modules(self, group: str) -> dict:
        return self.registry.get(group, {}) or {}

    def sorted_modules(self, group: str, enabled_only=False):
        rows = []
        for name, cfg in self.modules(group).items():
            if enabled_only and not cfg.get("enabled_by_default", False):
                continue
            rows.append((name, cfg))
        return sorted(rows, key=lambda item: int(item[1].get("order", 1000)))

    def load(self, group: str, name: str):
        cfg = self.modules(group).get(name)
        if not cfg:
            raise LyseModuleError(f"{group} module {name!r} is not registered")
        path = self.resolve_path(cfg.get("path"))
        if not path.exists():
            raise LyseModuleError(f"{group} module path does not exist: {path}")
        module_name = f"labpilot_user_{group}_{name}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise LyseModuleError(f"cannot import module from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            raise LyseModuleError(f"{path} does not define run()")
        return module, cfg

    def resolve_path(self, path_value) -> Path:
        path = Path(str(path_value or ""))
        if path.is_absolute():
            return path
        for base in self.base_dirs:
            candidate = base / path
            if candidate.exists():
                return candidate
        return self.base_dirs[-1] / path
