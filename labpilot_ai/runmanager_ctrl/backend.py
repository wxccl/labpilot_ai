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
    def client(self):
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
        return self.client.get_globals()

    def get_labscript_file(self):
        if self.mock:
            return self._labscript_file
        if self._local is not None:
            return self.local_snapshot()["sequence"]
        return self.client.get_labscript_file()

    def set_labscript_file(self, value, *, prepared=None):
        value = str(value or "")
        if self._local is not None or prepared is not None:
            return self._apply_configuration("set_sequence", {"sequence": value}, prepared)
        if self.mock:
            self._labscript_file = value
            return True
        return self.client.set_labscript_file(value)

    def get_shot_output_folder(self):
        if self.mock:
            return self._shot_output_folder
        if self._local is not None:
            return self.local_snapshot()["output"]
        return self.client.get_shot_output_folder()

    def set_shot_output_folder(self, value, *, prepared=None):
        value = str(value or "")
        if self._local is not None or prepared is not None:
            return self._apply_configuration("set_output", {"output": value}, prepared)
        if self.mock:
            self._shot_output_folder = value
            return True
        return self.client.set_shot_output_folder(value)

    def prepare_configuration(self, operation, changes):
        if self._local is None:
            raise RuntimeError("Local Runmanager gateway is not selected")
        return self._local.prepare(operation, changes)

    def _apply_configuration(self, operation, changes, prepared):
        if prepared is None:
            prepared = self.prepare_configuration(operation, changes)
        if self._local is None:
            raise ValueError("Prepared configuration requests require local gateway mode")
        if prepared.get("action") != operation or prepared.get("plan", {}).get("changes") != changes:
            raise ValueError("The prepared configuration no longer matches the requested values")
        return self._local.execute(prepared)

    def prepare_globals(self, values):
        if self._local is None:
            raise RuntimeError("Local Runmanager gateway is not selected")
        return self._local.prepare_globals(values)

    def set_globals(self, values: dict, *, prepared=None):
        if self._local is not None:
            from .local_gateway import raw_expression

            if prepared is None:
                request = self.prepare_globals(values)
            else:
                requested = {name: raw_expression(value) for name, value in values.items()}
                if prepared.get("action") != "apply_globals" or prepared.get("plan", {}).get("changes") != requested:
                    raise ValueError("The prepared global changes no longer match the requested values")
                request = prepared
            self._last_local_write = None
            receipt = self._local.execute(request)
            self._last_local_write = {"request": request, "receipt": receipt}
            return receipt
        if prepared is not None:
            raise ValueError("Prepared globals requests require local gateway mode")
        self._last_snapshot = self.snapshot_values(values.keys())
        if self.mock:
            self._mock_globals.update(values)
            return True
        return self.client.set_globals(values)

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
        if self._local is not None:
            previous = self._last_local_write
            if previous is None:
                return {}
            self._last_local_write = None
            receipt = self._local._restore_globals(previous)
            return {
                name: receipt["after"]["globals_raw"][name]
                for name in previous["request"]["plan"]["changes"]
            }
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
        if self._local is not None:
            return self.local_snapshot()["n_shots"]
        return self.client.n_shots()

    def set_run_shots(self, value: bool, *, prepared=None):
        if self._local is not None or prepared is not None:
            return self._apply_configuration("set_flags", {"run": bool(value)}, prepared)
        if self.mock:
            self._run_shots = bool(value)
            return True
        return self.client.set_run_shots(bool(value))

    def prepare_engage(self):
        snapshot = self.local_snapshot()
        return self._local.prepare("engage_once", snapshot=snapshot, expected_n_shots=snapshot["n_shots"])

    def engage(self, prepared=None):
        if self.mock:
            return {"mock_engaged": True, "n_shots": self.n_shots()}
        if self._local is not None:
            if not isinstance(prepared, dict) or prepared.get("action") != "engage_once":
                raise ValueError("Prepare and review a concrete Engage request first")
            return self._local.execute(prepared)
        return self.client.engage()
