class OptimizationSession:
    def __init__(self, name="optimization", objective=None, mode="maximize", method="grid"):
        self.name = name
        self.objective = objective
        self.mode = mode
        self.method = method
        self.history = []
        self.status = "idle"
        self.pending_params = None

    def add_result(self, params, value, metadata=None):
        self.history.append({"params": params, "value": value, "metadata": metadata or {}})

    def best(self):
        if not self.history:
            return None
        reverse = self.mode == "maximize"
        return sorted(self.history, key=lambda r: r["value"], reverse=reverse)[0]

    def as_dict(self):
        return {
            "name": self.name,
            "objective": self.objective,
            "mode": self.mode,
            "method": self.method,
            "status": self.status,
            "pending_params": self.pending_params,
            "history": list(self.history),
            "best": self.best(),
        }
