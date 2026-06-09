import itertools


def build_grid(param_values: dict):
    keys = list(param_values.keys())
    vals = [param_values[k] for k in keys]
    for combo in itertools.product(*vals):
        yield dict(zip(keys, combo))
