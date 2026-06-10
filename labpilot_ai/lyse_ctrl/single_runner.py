from .h5_loader import read_shot_summary
from .module_manager import ModuleManager


def run_single_module(registry: dict, name: str, h5_path, params=None):
    manager = ModuleManager(registry)
    module, cfg = manager.load("single_modules", name)
    shot_context = {"path": str(h5_path), "summary": read_shot_summary(h5_path), "config": cfg}
    result = module.run(shot_context, params or {})
    if not isinstance(result, dict):
        raise TypeError("single lyse module run() must return a dict")
    return result


def run_enabled_single_modules(registry: dict, h5_path):
    manager = ModuleManager(registry)
    out = {}
    for name, cfg in manager.sorted_modules("single_modules", enabled_only=True):
        module, _ = manager.load("single_modules", name)
        result = module.run({"path": str(h5_path), "summary": read_shot_summary(h5_path), "config": cfg}, cfg.get("params", {}))
        out[name] = result
    return out
