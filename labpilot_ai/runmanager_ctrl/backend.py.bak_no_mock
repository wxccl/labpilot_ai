import numpy as np


class RunmanagerBackend:
    def __init__(self, mock=True, timeout=10):
        self.mock = mock
        self.timeout = timeout
        self._client = None
        self._mock_globals = {}
        self._run_shots = False
        self._last_snapshot = {}

    def connect(self):
        if self.mock:
            return "mock-runmanager: ok"

        # labscript_utils.h5_lock must be imported before h5py/runmanager.
        # Keep this import local so Mock mode still works on development PCs.
        from labpilot_ai.bootstrap_labscript import install_h5_lock
        install_h5_lock(verbose=False)

        import runmanager.remote
        self._client = runmanager.remote.Client(timeout=self.timeout)
        return self._client.say_hello()

    @property
    def client(self):
        if self.mock:
            return None
        if self._client is None:
            self.connect()
        return self._client

    def get_globals(self):
        if self.mock:
            return dict(self._mock_globals)
        return self.client.get_globals()

    def set_globals(self, values: dict):
        self._last_snapshot = self.snapshot_values(values.keys())
        if self.mock:
            self._mock_globals.update(values)
            return True
        return self.client.set_globals(values)

    def snapshot_values(self, names):
        current = self.get_globals()
        return {name: current.get(name) for name in names}

    def preview_diff(self, values: dict):
        current = self.get_globals()
        return {
            name: {"old": current.get(name), "new": value, "changed": current.get(name) != value}
            for name, value in values.items()
        }

    def rollback_last(self):
        if not self._last_snapshot:
            return {}
        values = dict(self._last_snapshot)
        if self.mock:
            self._mock_globals.update(values)
        else:
            self.client.set_globals(values)
        self._last_snapshot = {}
        return values

    def n_shots(self):
        if self.mock:
            n = 1
            for v in self._mock_globals.values():
                if isinstance(v, np.ndarray):
                    n *= max(1, len(v))
            return n
        return self.client.n_shots()

    def set_run_shots(self, value: bool):
        if self.mock:
            self._run_shots = bool(value)
            return True
        return self.client.set_run_shots(bool(value))

    def engage(self):
        if self.mock:
            return {"mock_engaged": True, "n_shots": self.n_shots()}
        return self.client.engage()
