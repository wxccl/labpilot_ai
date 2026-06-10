from .base import OptimizationSession
from .bayesian import BayesianOptimizer
from .grid_search import grid_from_specs
from .objective import SafeObjective


class OptimizerLoop:
    def __init__(self, spec: dict):
        self.spec = spec
        self.session = OptimizationSession(
            name=spec.get("name", "optimization"),
            objective=spec["objective"],
            mode=spec.get("mode", "maximize"),
            method=spec.get("method", "grid"),
        )
        self.objective = SafeObjective(spec["objective"])
        self._index = 0
        self._asked = 0
        self._max_iterations = int(spec.get("max_iterations", 1))
        self._grid = []
        self._bayes = None
        if self.session.method == "grid":
            self._grid = grid_from_specs(spec["parameters"])
        else:
            bounds = {k: (v["min"], v["max"]) for k, v in spec["parameters"].items()}
            self._bayes = BayesianOptimizer(bounds, mode=self.session.mode)
        self.session.status = "ready"

    def ask(self):
        if self._asked >= self._max_iterations:
            self.session.status = "complete"
            return None
        if self.session.method == "grid":
            if self._index >= len(self._grid):
                self.session.status = "complete"
                return None
            params = self._grid[self._index]
            self._index += 1
        else:
            params = self._bayes.ask()
        self._asked += 1
        self.session.pending_params = params
        self.session.status = "running"
        return params

    def tell(self, params, result_values: dict, metadata=None):
        value = self.objective.evaluate(result_values)
        self.session.add_result(params, value, metadata=metadata)
        if self._bayes:
            self._bayes.tell(params, value)
        self.session.pending_params = None
        return value

    def best(self):
        return self.session.best()
