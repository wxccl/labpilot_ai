from .h5_loader import read_shot_summary
from .lyse_script_runner import run_lyse_script
from .module_manager import ModuleManager
from .private_inputs import PrivateInputs


def run_single_module(registry: dict, name: str, h5_path, params=None):
    manager = ModuleManager(registry)
    cfg = manager.modules("single_modules").get(name)
    if cfg and cfg.get("mode") == "lyse_script":
        script_path = manager.resolve_path(cfg.get("path"))
        result = run_lyse_script(script_path, mode="single", h5_path=h5_path, params=params or cfg.get("params", {}),
                                 routine_sha256=cfg.get("routine_sha256"), timeout_s=cfg.get("timeout_s", 300))
        return result.get("results", result)
    module, cfg = manager.load("single_modules", name)
    with PrivateInputs() as inputs:
        path = inputs.shot(h5_path)
        shot_context = {"path": path, "summary": read_shot_summary(path), "config": cfg}
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
