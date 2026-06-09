class BayesianOptimizerPlaceholder:
    """Placeholder for Bayesian optimization.

    Later replace with scikit-optimize, Optuna, or BoTorch backend.
    """
    def __init__(self, bounds):
        self.bounds = bounds
        self.history = []

    def ask(self):
        # Starter: midpoint of each bound.
        return {k: (v[0] + v[1]) / 2 for k, v in self.bounds.items()}

    def tell(self, params, value):
        self.history.append((params, value))
