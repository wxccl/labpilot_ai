from .h5_loader import read_shot_summary
from .lyse_script_runner import run_lyse_script
from .module_manager import ModuleManager


def run_single_module(registry: dict, name: str, h5_path, params=None):
    manager = ModuleManager(registry)
    cfg = manager.modules("single_modules").get(name)
    if cfg and cfg.get("mode") == "lyse_script":
        script_path = manager.resolve_path(cfg.get("path"))
        result = run_lyse_script(script_path, mode="single", h5_path=h5_path, params=params or cfg.get("params", {}))
        return result.get("results", result)
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
        out[name] = run_single_module(registry, name, h5_path, params=cfg.get("params", {}))
    return out
