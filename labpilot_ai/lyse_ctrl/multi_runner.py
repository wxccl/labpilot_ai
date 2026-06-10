from .module_manager import ModuleManager


def run_multi_module(registry: dict, name: str, dataframe, params=None):
    manager = ModuleManager(registry)
    module, cfg = manager.load("multi_modules", name)
    result = module.run(dataframe, params or cfg.get("params", {}))
    if not isinstance(result, dict):
        raise TypeError("multi lyse module run() must return a dict")
    return result


def run_enabled_multi_modules(registry: dict, dataframe):
    manager = ModuleManager(registry)
    out = {}
    for name, cfg in manager.sorted_modules("multi_modules", enabled_only=True):
        module, _ = manager.load("multi_modules", name)
        out[name] = module.run(dataframe, cfg.get("params", {}))
    return out
