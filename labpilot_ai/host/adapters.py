"""Packaged simulator and official localhost Runmanager adapter."""

import ast
import hashlib
import math
from pathlib import Path

from .protocol import Refused, RUN_ACTIONS, canonical, require_snapshot, snapshot


FLAGS = {"run": "run_shots", "view": "view_shots", "shuffle": "shuffle"}
SIM_RUN = {"globals": {"dummy": 0}, "globals_raw": {"dummy": "0"}, "sequence": "simulated.py",
           "output": "simulated_output", "flags": {"run": True, "view": False, "shuffle": False},
           "n_shots": 1, "errors": False, "simulated": True}
SIM_CHANNELS = {"ao0": {"kind": "AO", "unit": "V", "limits": [-10, 10]},
                "port0/line0": {"kind": "DO", "unit": "logical boolean"}}
SIM_BLACS = {"device": "sim_daq", "values": {"ao0": 0.0, "port0/line0": False},
             "channels": SIM_CHANNELS, "simulated": True, "manual": True}


def action_values(params, *, empty=False):
    values = params.get("values", {})
    if type(values) is not dict or (not values and not empty):
        raise Refused("A nonempty values object is required")
    return values


def run_values(action, params, before, max_shots):
    values = action_values(params, empty=action == "engage")
    if action == "engage":
        shots = params.get("expected_n_shots")
        if (values or type(shots) is not int or shots != before["n_shots"] or
                not 1 <= shots <= max_shots or before["errors"]):
            raise Refused("Engage requires the exact current positive shot count and valid globals")
    elif action == "set_globals":
        if set(values) - set(before["globals_raw"]):
            raise Refused("Only currently active Runmanager globals can be set")
    elif action == "set_flags":
        if set(values) - set(FLAGS) or any(type(value) is not bool for value in values.values()):
            raise Refused("Flags are booleans named run, view or shuffle")
    elif action in {"set_sequence", "set_output"}:
        field = "sequence" if action == "set_sequence" else "output"
        if set(values) != {field} or type(values[field]) is not str or not values[field].strip():
            raise Refused(f"A single {field} path is required")
    return values


def blacs_values(params, before):
    values = action_values(params)
    for channel, value in values.items():
        info = before["channels"].get(channel, {})
        if info.get("kind") in {"DO", "DDS.gate"}:
            if type(value) is not bool:
                raise Refused(f"{channel} requires a JSON boolean")
        elif info.get("kind") in {"AO", "DDS.freq", "DDS.amp", "DDS.phase"}:
            limits = info.get("limits")
            if (type(value) not in (int, float) or not math.isfinite(value) or
                    not limits or not limits[0] <= value <= limits[1]):
                raise Refused(f"{channel} requires a finite value within reported base-unit limits")
        else:
            raise Refused(f"{channel} has no supported typed control")
    return values


class Simulator:
    def __init__(self, target, journal):
        self.target = target
        self.journal = journal
        self.default = SIM_RUN if target == "runmanager" else SIM_BLACS

    def discover(self):
        return {"available": True, "simulated": True,
                "actions": sorted(RUN_ACTIONS) if self.target == "runmanager" else ["set_manual"],
                "devices": [] if self.target == "runmanager" else ["sim_daq"]}

    def _check(self, params):
        if self.target == "blacs" and params.get("device") != "sim_daq":
            raise Refused("The simulator device is sim_daq")

    def snapshot(self, params):
        self._check(params)
        return snapshot(self.journal.simulated_state(self.target, self.default))

    def execute(self, params):
        self._check(params)
        action = params.get("action")
        if action not in self.discover()["actions"]:
            raise Refused("Unsupported simulated action")
        evidence = {"simulated": True}

        def change(state):
            before = snapshot(state)
            require_snapshot(params, before)
            evidence["config_digest"] = before["snapshot_sha256"]
            if self.target == "blacs":
                return {**state, "values": {**state["values"], **blacs_values(params, before)}}
            values = run_values(action, params, before, 10000)
            if action == "engage":
                count = before["n_shots"]
                evidence["compiled_count"] = count
                if before["flags"]["run"]:
                    evidence.update(queued_count=count, executed_count=count, analyzed_count=count,
                                    quality="UNKNOWN", terminal="COMPLETED")
                return state
            if action == "set_globals":
                merged = {**state["globals"], **values}
                return {**state, "globals": merged, "globals_raw": {key: repr(value) for key, value in merged.items()},
                        "n_shots": math.prod(len(value) for value in merged.values() if isinstance(value, list))}
            if action == "set_flags":
                return {**state, "flags": {**state["flags"], **values}}
            return {**state, **values}

        state = self.journal.simulated_state(self.target, self.default, change)
        return {"after": snapshot(state), "evidence": evidence}


def evaluated(value):
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else {"nonfinite": str(value)}
    if type(value) in (list, tuple):
        return [evaluated(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: evaluated(item) for key, item in value.items()}
    if type(value).__module__.startswith("numpy") and hasattr(value, "tolist"):
        return evaluated(value.tolist())
    return {"unsupported_type": type(value).__name__}


def file_sha256(path):
    try:
        with Path(path).open("rb") as stream:
            result = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(block)
        return result.hexdigest()
    except OSError:
        return None


def native_ack(method, *args, **kwargs):
    result = method(*args, **kwargs)
    if isinstance(result, BaseException):
        raise RuntimeError(f"Runmanager returned {type(result).__name__}: {result}")
    if result is not None:
        raise RuntimeError("Unexpected Runmanager mutation response")


def verified_globals(before, after, requested):
    old = before["globals_raw"]
    new = after["globals_raw"]
    if old.keys() != new.keys() or any(new[name] != old[name] for name in old.keys() - requested.keys()):
        return False
    try:
        # literal_eval handles a trailing preserved Python comment without evaluating code.
        return all(canonical(ast.literal_eval(new[name])) == canonical(value)
                   and canonical(after["globals"][name]) == canonical(value) for name, value in requested.items())
    except (KeyError, TypeError, ValueError, SyntaxError):
        return False


class Runmanager:
    def __init__(self, profile, client=None):
        self.profile = profile
        self.config = profile.runmanager
        self.client = client

    def _connect(self):
        if not self.config.get("enabled"):
            raise Refused("Runmanager is disabled in the host profile")
        if self.client is None:
            import labscript_utils.h5_lock  # Load before Runmanager and h5py.
            from runmanager.remote import Client

            self.client = Client(host="127.0.0.1", port=self.config.get("port"), timeout=5)
        return self.client

    def discover(self):
        if not self.config.get("enabled"):
            return {"available": False, "actions": []}
        version = self._connect().get_version()
        if not isinstance(version, str):
            raise RuntimeError("Unexpected Runmanager version response")
        return {"available": True, "actions": sorted(self.config["allow"]), "version": version, "endpoint": "localhost"}

    def snapshot(self, params):
        rm = self._connect()
        raw = rm.get_globals(raw=True)
        if not isinstance(raw, dict) or any(type(value) is not str for value in raw.values()):
            raise RuntimeError("Unexpected raw globals response from Runmanager")
        sequence = rm.get_labscript_file()
        output = rm.get_shot_output_folder()
        count = rm.n_shots()
        flags = {key: getattr(rm, f"get_{method}")() for key, method in FLAGS.items()}
        errors = rm.error_in_globals()
        values = rm.get_globals()
        if (not isinstance(sequence, str) or not isinstance(output, str) or type(count) is not int
                or type(errors) is not bool or any(type(flag) is not bool for flag in flags.values())
                or not isinstance(values, dict)):
            raise RuntimeError("Unexpected configuration response from Runmanager")
        value = {"globals_raw": raw, "globals": evaluated(values), "sequence": sequence,
                 "sequence_sha256": file_sha256(sequence) if sequence else None,
                 "output": output, "n_shots": count, "flags": flags, "errors": errors}
        if rm.get_globals(raw=True) != raw:
            raise Refused("Runmanager globals changed during readback")
        return snapshot(value)

    def _path(self, field, value):
        root = self.config.get(f"{field}_root")
        if root is None:
            raise Refused(f"Set the allowed {field}_root in the host profile")
        root = self.profile.resolve(root)
        path = self.profile.resolve(value)
        if not path.is_relative_to(root):
            raise Refused(f"{field} path is outside the configured root")
        if field == "sequence" and (path.suffix.lower() != ".py" or not path.is_file()):
            raise Refused("Expected an existing Labscript Python sequence")
        if field == "output" and (not root.is_dir() or path.exists() and not path.is_dir()):
            raise Refused("Expected a directory path within an existing output root")
        return str(path)

    def execute(self, params):
        action = params.get("action")
        if action not in self.config["allow"]:
            raise Refused("Runmanager action is disabled in the host profile")
        rm = self._connect()
        before = self.snapshot(params)
        require_snapshot(params, before)
        values = run_values(action, params, before, self.config.get("max_shots", 10000))
        evidence = {"config_digest": before["snapshot_sha256"], "physical_execution_verified": False}
        if action == "engage":
            if not before["sequence_sha256"] or not before["output"]:
                raise Refused("Engage requires a readable sequence and an output path")
            self._path("sequence", before["sequence"])
            self._path("output", before["output"])
            if self.snapshot(params)["snapshot_sha256"] != before["snapshot_sha256"]:
                raise Refused("Runmanager changed just before Engage")
            native_ack(rm.engage)
            return {"evidence": {**evidence, "native_acknowledged": True}, "expected_n_shots": before["n_shots"]}
        if action == "set_globals":
            native_ack(rm.set_globals, values, raw=False)
        elif action == "set_flags":
            for key, value in values.items():
                native_ack(getattr(rm, f"set_{FLAGS[key]}"), value)
        else:
            field = "sequence" if action == "set_sequence" else "output"
            value = self._path(field, values[field])
            setter = rm.set_labscript_file if field == "sequence" else rm.set_shot_output_folder
            native_ack(setter, value)
        try:
            after = self.snapshot(params)
        except Refused as exc:
            raise RuntimeError("Runmanager configuration changed after effect") from exc
        if action == "set_globals":
            if not verified_globals(before, after, values):
                raise RuntimeError("Runmanager globals readback differs from the requested values")
        elif action == "set_flags":
            if after["flags"] != {**before["flags"], **values}:
                raise RuntimeError("Runmanager flags readback differs from the requested values")
        elif after[field] != value:
            raise RuntimeError("Runmanager path readback differs from the requested value")
        return {"after": after, "evidence": {**evidence, "configuration_readback": True}}
