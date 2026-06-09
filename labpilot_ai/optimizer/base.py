class OptimizationSession:
    def __init__(self, name="optimization", objective=None, mode="maximize"):
        self.name = name
        self.objective = objective
        self.mode = mode
        self.history = []
        self.status = "idle"

    def add_result(self, params, value, metadata=None):
        self.history.append({"params": params, "value": value, "metadata": metadata or {}})

    def best(self):
        if not self.history:
            return None
        reverse = self.mode == "maximize"
        return sorted(self.history, key=lambda r: r["value"], reverse=reverse)[0]
