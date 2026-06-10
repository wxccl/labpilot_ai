import random


class BayesianOptimizer:
    """Small ask/tell optimizer with optional scikit-optimize backend.

    If scikit-optimize is unavailable, this falls back to deterministic random
    exploration after the midpoint. It keeps the public contract stable for the
    UI and tests, while allowing a stronger backend in lab environments.
    """

    def __init__(self, bounds, mode="maximize", seed=3):
        self.bounds = {k: (float(v[0]), float(v[1])) for k, v in bounds.items()}
        self.mode = mode
        self.history = []
        self._rng = random.Random(seed)
        self._names = list(self.bounds)
        self._skopt = None
        self._opt = None
        try:
            from skopt import Optimizer

            dimensions = [self.bounds[name] for name in self._names]
            self._opt = Optimizer(dimensions=dimensions, random_state=seed)
            self._skopt = True
        except Exception:
            self._skopt = False

    def ask(self):
        if self._skopt:
            values = self._opt.ask()
            return dict(zip(self._names, values))
        if not self.history:
            return {k: (lo + hi) / 2 for k, (lo, hi) in self.bounds.items()}
        return {k: self._rng.uniform(lo, hi) for k, (lo, hi) in self.bounds.items()}

    def tell(self, params, value):
        value = float(value)
        self.history.append((dict(params), value))
        if self._skopt:
            x = [float(params[name]) for name in self._names]
            y = -value if self.mode == "maximize" else value
            self._opt.tell(x, y)


BayesianOptimizerPlaceholder = BayesianOptimizer
