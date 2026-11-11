import copy
import hashlib
import json
import ntpath

import numpy as np
import pytest

from labpilot_ai.runmanager_ctrl.backend import RunmanagerBackend
from labpilot_ai.runmanager_ctrl.local_gateway import LocalRunmanager, RunmanagerGatewayError
from labpilot_ai.runmanager_ctrl.write_router import preview_runmanager_write_targets, write_runmanager_globals


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class FakeGateway:
    def __init__(self):
        self.config = {
            "globals_raw": {"power": "base_power * 2  # 保持", "base_power": "1.0", "scan": "np.arange(4)"},
            "sequence": r"D:\lab\seq.py",
            "output": r"D:\lab\data",
            "run": True,
            "view": False,
            "shuffle": False,
        }
        self.calls = []
        self.failed_state = None
        self.n_shots = 4
        self.engage_calls = 0

    def snapshot(self):
        config = copy.deepcopy(self.config)
        return dict(
            config,
            schema="unified-runmanager/1",
            config_digest=digest(config),
            snapshot_consistent=True,
            n_shots=self.n_shots,
            error_in_globals=False,
            globals_evaluated={"power": 2.0, "base_power": 1.0},
        )

    def plan(self, request):
        baseline = {name: request["baseline"][name] for name in self.config}
        target = copy.deepcopy(baseline)
        action = request["operation"]
        difference = []
        for name, value in request["changes"].items():
            if action == "apply_globals":
                old = baseline["globals_raw"][name]
                suffix = "  # 保持" if old.endswith("  # 保持") else ""
                target["globals_raw"][name] = value + suffix
                difference.append(dict(name=name, before=old, submitted_raw=value, expected_after=value + suffix))
            else:
                target[name] = ntpath.normpath(value) if name in {"sequence", "output"} else value
                difference.append(dict(name=name, before=baseline[name], expected_after=target[name]))
        plan = {
            "schema": "unified-runmanager-plan/1",
            "operation": action,
            "baseline": baseline,
            "baseline_digest": digest(baseline),
            "baseline_n_shots": request["baseline"]["n_shots"],
            "changes": request["changes"],
            "target": target,
            "diff": difference,
            "prospective_n_shots": None,
        }
        return dict(plan, plan_digest=digest(plan))

    def call(self, target, request):
        assert target == "runmanager"
        assert request["schema"] == "unified-runmanager-request/1"
        self.calls.append(copy.deepcopy(request))
        action = request["action"]
        if action == "read_all":
            return self.snapshot()
        if action == "plan":
            return self.plan(request)
        assert request["expected_endpoint"] == {"host": "localhost", "port": 42523}
        assert request["execute"] is True
        before = self.snapshot()
        receipt = dict(schema=before["schema"], operation=action, request_id=request["request_id"], before=before)
        if self.failed_state:
            return dict(receipt, state=self.failed_state, engage_calls=0)
        if action == "engage_once":
            if request["expected_config_digest"] != digest(self.config) or request["expected_n_shots"] != self.n_shots:
                return dict(receipt, state="PRECHECK_FAILED_NO_WRITE", engage_calls=0)
            self.engage_calls += 1
            return dict(receipt, state="RPC_ACK_NOT_EXECUTION_PROOF", engage_calls=1,
                        expected_n_shots=self.n_shots, compiled_count=None, executed_count=None)
        plan = request["plan"]
        if plan["baseline_digest"] != digest(self.config):
            return dict(receipt, state="PRECHECK_FAILED_NO_WRITE", engage_calls=0)
        self.config = copy.deepcopy(plan["target"])
        return dict(receipt, state="APPLIED_READBACK_VERIFIED", after=self.snapshot(), engage_calls=0)

    @property
    def actions(self):
        return [call["action"] for call in self.calls]


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.delenv("LABPILOT_RUNMANAGER_PORT", raising=False)
    return FakeGateway()


def test_globals_preview_then_apply_preserves_comments_and_scans(gateway):
    backend = RunmanagerBackend(control_mode="local_gateway", gateway=gateway)
    values = {"power": 3.25, "scan": np.array([1, 5, 10])}
    prepared = backend.prepare_globals(values)
    assert gateway.actions == ["read_all", "plan"]
    assert prepared["plan"]["changes"] == {"power": "3.25", "scan": "np.array([1, 5, 10])"}
    assert prepared["plan"]["target"]["globals_raw"]["power"] == "3.25  # 保持"
    with pytest.raises(ValueError, match="no longer match"):
        backend.set_globals({"power": 99}, prepared=prepared)
    assert gateway.actions == ["read_all", "plan"]
    receipt = backend.set_globals(values, prepared=prepared)
    assert receipt["state"] == "APPLIED_READBACK_VERIFIED"
    assert gateway.actions == ["read_all", "plan", "apply_globals"]
    assert gateway.engage_calls == 0


def test_rollback_uses_post_write_baseline_and_restores_exact_original_expression(gateway):
    backend = RunmanagerBackend(gateway=gateway)
    baseline = copy.deepcopy(gateway.config)
    backend.set_globals({"power": 3.0})
    assert backend.rollback_last() == {"power": baseline["globals_raw"]["power"]}
    assert gateway.config == baseline
    backend.set_globals({"power": 4.0})
    gateway.config["globals_raw"]["base_power"] = "7.5"
    with pytest.raises(RunmanagerGatewayError, match="PRECHECK_FAILED_NO_WRITE"):
        backend.rollback_last()
    assert gateway.config["globals_raw"]["power"] == "4.0  # 保持"


@pytest.mark.parametrize("state", ["APPLIED_GLOBALS_ERROR", "UNKNOWN_DO_NOT_RETRY"])
def test_local_router_does_not_retry_or_fall_back_to_h5_on_unverified_write(gateway, monkeypatch, state):
    from labpilot_ai.runmanager_ctrl import write_router

    def forbidden(*args, **kwargs):
        pytest.fail("Local gateway mode used the direct HDF5 fallback")

    monkeypatch.setattr(write_router, "write_runmanager_globals_h5", forbidden)
    monkeypatch.setattr(write_router, "read_runmanager_globals_h5", forbidden)
    backend = RunmanagerBackend(gateway=gateway)
    gateway.failed_state = state
    assert preview_runmanager_write_targets(backend, {"power": 1, "inactive": 2}, globals_h5_path="ignored.h5") == {
        "power": "remote", "inactive": "missing"
    }
    prepared = backend.prepare_globals({"power": 1})
    with pytest.raises(RunmanagerGatewayError) as failure:
        write_runmanager_globals(backend, {"power": 1}, globals_h5_path="ignored.h5", prepared=prepared)
    assert failure.value.receipt["state"] == state
    assert gateway.actions.count("apply_globals") == 1
    assert backend.rollback_last() == {}


def test_engage_is_explicit_count_bound_and_receipt_is_not_completion(gateway):
    adapter = LocalRunmanager(gateway)
    with pytest.raises(ValueError, match="positive explicit shot count"):
        adapter.prepare("engage_once")
    with pytest.raises(ValueError, match="does not match"):
        adapter.prepare("engage_once", expected_n_shots=999)
    prepared = adapter.prepare("engage_once", expected_n_shots=4)
    assert gateway.engage_calls == 0
    gateway.n_shots = 6
    with pytest.raises(RunmanagerGatewayError, match="PRECHECK_FAILED_NO_WRITE"):
        adapter.execute(prepared)
    assert gateway.engage_calls == 0
    prepared = adapter.prepare("engage_once", expected_n_shots=6)
    receipt = adapter.execute(prepared)
    assert receipt["state"] == "RPC_ACK_NOT_EXECUTION_PROOF"
    assert receipt["compiled_count"] is None
    assert receipt["executed_count"] is None
    assert gateway.engage_calls == 1
    gateway.config["run"] = False
    with pytest.raises(ValueError, match="Enable Run shots"):
        adapter.prepare("engage_once", expected_n_shots=6)


def test_path_and_flag_changes_use_gateway(gateway):
    backend = RunmanagerBackend(gateway=gateway)
    prepared = backend.prepare_configuration("set_sequence", {"sequence": r"D:\lab\./new.py"})
    with pytest.raises(ValueError, match="no longer matches"):
        backend.set_labscript_file(r"D:\lab\wrong.py", prepared=prepared)
    assert gateway.actions == ["read_all", "plan"]
    backend.set_labscript_file(r"D:\lab\./new.py", prepared=prepared)
    backend.set_shot_output_folder(r"D:\lab\new-data")
    backend.set_run_shots(False)
    assert backend.get_labscript_file() == r"D:\lab\new.py"
    assert backend.get_shot_output_folder() == r"D:\lab\new-data"
    assert backend.local_snapshot()["run"] is False
    assert gateway.engage_calls == 0


def test_raw_plan_accepts_data_but_rejects_other_calls(gateway):
    adapter = LocalRunmanager(gateway)
    adapter.prepare("apply_globals", {"scan": "np.array([1, 2, 3])"})
    with pytest.raises(ValueError, match="literal"):
        adapter.prepare("apply_globals", {"scan": "print('not experiment data')"})
    with pytest.raises(ValueError, match="literal"):
        adapter.prepare("apply_globals", {"scan": "np.array([print('not experiment data')])"})
    assert gateway.actions.count("plan") == 1


def test_mock_backend_keeps_existing_semantics_when_gateway_mode_is_selected(monkeypatch):
    monkeypatch.setenv("LABPILOT_CONTROL_MODE", "local_gateway")
    backend = RunmanagerBackend(mock=True)
    assert not backend.uses_local_gateway
    backend.set_globals({"scan": np.array([1, 2, 3])})
    assert backend.engage() == {"mock_engaged": True, "n_shots": 3}
