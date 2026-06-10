from .module_manager import ModuleManager
from .lyse_script_runner import run_lyse_script


def run_multi_module(registry: dict, name: str, dataframe, params=None):
    manager = ModuleManager(registry)
    cfg = manager.modules("multi_modules").get(name)
    if cfg and cfg.get("mode") == "lyse_script":
        script_path = manager.resolve_path(cfg.get("path"))
        result = run_lyse_script(
            script_path,
            mode="multi",
            dataframe=dataframe,
            meta_h5_path=cfg.get("meta_h5_path", ""),
            params=params or cfg.get("params", {}),
        )
        return result.get("results", result)
    module, cfg = manager.load("multi_modules", name)
    result = module.run(dataframe, params or cfg.get("params", {}))
    if not isinstance(result, dict):
        raise TypeError("multi lyse module run() must return a dict")
    return result


def run_enabled_multi_modules(registry: dict, dataframe):
    manager = ModuleManager(registry)
    out = {}
    for name, cfg in manager.sorted_modules("multi_modules", enabled_only=True):
        out[name] = run_multi_module(registry, name, dataframe, params=cfg.get("params", {}))
    return out
