import os

import numpy as np


class RunmanagerBackend:
    def __init__(self, mock=False, timeout=10, *, control_mode=None, gateway=None):
        self.mock = mock
        self.timeout = timeout
        self._client = None
        self._mock_globals = {}
        self._run_shots = False
        self._last_snapshot = {}
        self._labscript_file = ""
        self._shot_output_folder = ""
        self._local = None
        self._last_local_write = None
        if not mock:
            mode = control_mode if control_mode is not None else os.environ.get("LABPILOT_CONTROL_MODE", "")
            mode = mode.strip().lower()
            if gateway is not None or mode == "local_gateway":
                from .local_gateway import LocalRunmanager

                self._local = LocalRunmanager(gateway)
            elif mode not in ("", "legacy"):
                raise ValueError(f"Unknown LabPilot control mode: {mode}")

    @property
    def uses_local_gateway(self):
        return self._local is not None

    def local_snapshot(self):
        if self._local is None:
            raise RuntimeError("Local Runmanager gateway is not selected")
        return self._local.read_all()

    def connect(self):
        if self.mock:
            return "mock-runmanager: ok"
        if self._local is not None:
            self.local_snapshot()
            return "local Runmanager gateway: ok"

        # labscript_utils.h5_lock must be imported before h5py/runmanager.
        # Keep this import local so Mock mode still works on development PCs.
        from labpilot_ai.bootstrap_labscript import install_h5_lock
        install_h5_lock(verbose=False)

        import runmanager.remote
        self._client = runmanager.remote.Client(timeout=self.timeout)
        return self._client.say_hello()

    @property
    def _read_client(self):
        if self.mock:
            return None
        if self._local is not None:
            raise RuntimeError("Local gateway mode only uses the reviewed gateway")
        if self._client is None:
            self.connect()
        return self._client

    def get_globals(self):
        if self.mock:
            return dict(self._mock_globals)
        if self._local is not None:
            from .local_gateway import evaluated_globals

            return evaluated_globals(self.local_snapshot())
        return self._read_client.get_globals()

    def get_labscript_file(self):
        if self.mock:
            return self._labscript_file
        if self._local is not None:
            return self.local_snapshot()["sequence"]
        return self._read_client.get_labscript_file()

    def set_labscript_file(self, value, *, prepared=None):
        if self.mock is not True:
            raise PermissionError("Live Runmanager writes require a managed labpilot A2/A3 task")
        self._labscript_file = str(value or "")
        return True

    def get_shot_output_folder(self):
        if self.mock:
            return self._shot_output_folder
        if self._local is not None:
            return self.local_snapshot()["output"]
        return self._read_client.get_shot_output_folder()

    def set_shot_output_folder(self, value, *, prepared=None):
        if self.mock is not True:
            raise PermissionError("Live Runmanager writes require a managed labpilot A2/A3 task")
        self._shot_output_folder = str(value or "")
        return True

    def prepare_configuration(self, operation, changes):
        if self._local is None:
            raise RuntimeError("Local Runmanager gateway is not selected")
        return self._local.prepare(operation, changes)

    def prepare_globals(self, values):
        if self._local is None:
            raise RuntimeError("Local Runmanager gateway is not selected")
        return self._local.prepare_globals(values)

    def set_globals(self, values: dict, *, prepared=None):
        if self.mock is not True:
            raise PermissionError("Live Runmanager writes require a managed labpilot A2/A3 task")
        self._last_snapshot = self.snapshot_values(values.keys())
        self._mock_globals.update(values)
        return True

    def snapshot_values(self, names):
        current = self.get_globals()
        return {name: current.get(name) for name in names}

    def preview_diff(self, values: dict):
        if self._local is not None:
            plan = self._local.prepare_globals(values)["plan"]
            return {
                item["name"]: {
                    "old": item["before"],
                    "new": item["expected_after"],
                    "changed": item["before"] != item["expected_after"],
                }
                for item in plan["diff"]
            }
        current = self.get_globals()
        return {
            name: {"old": current.get(name), "new": value, "changed": current.get(name) != value}
            for name, value in values.items()
        }

    def rollback_last(self):
        if self.mock is not True:
            raise PermissionError("Live Runmanager writes require a managed labpilot A2/A3 task")
        values = self._last_snapshot
        self._mock_globals.update(values)
        self._last_snapshot = {}
        return values

    def n_shots(self):
        if self.mock:
            n = 1
            for v in self._mock_globals.values():
                if isinstance(v, np.ndarray):
                    n *= max(1, len(v))
            return n
        if self._local is not None:
            return self.local_snapshot()["n_shots"]
        return self._read_client.n_shots()

    def set_run_shots(self, value: bool, *, prepared=None):
        if self.mock is not True:
            raise PermissionError("Live Runmanager writes require a managed labpilot A2/A3 task")
        self._run_shots = bool(value)
        return True

    def prepare_engage(self):
        snapshot = self.local_snapshot()
        return self._local.prepare("engage_once", snapshot=snapshot, expected_n_shots=snapshot["n_shots"])

    def engage(self, prepared=None):
        if self.mock is not True:
            raise PermissionError("Live Runmanager writes require a managed labpilot A2/A3 task")
        return {"mock_engaged": True, "n_shots": self.n_shots()}
