import itertools
import numpy as np


def build_grid(param_values: dict):
    keys = list(param_values.keys())
    vals = [param_values[k] for k in keys]
    for combo in itertools.product(*vals):
        yield dict(zip(keys, combo))


def grid_from_specs(specs: dict):
    values = {}
    for name, spec in specs.items():
        points = int(spec.get("points", 1))
        if points <= 1:
            values[name] = [float(spec.get("min", spec.get("max", 0.0)))]
        else:
            values[name] = np.linspace(float(spec["min"]), float(spec["max"]), points).tolist()
    return list(build_grid(values))
