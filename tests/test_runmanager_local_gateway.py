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


@pytest.mark.parametrize("mode", ["legacy", "", "local_gateway"])
def test_desktop_runmanager_is_read_only_in_every_live_mode(gateway, mode):
    backend = RunmanagerBackend(control_mode=mode, gateway=gateway if mode == "local_gateway" else None)
    operations = [lambda: backend.engage(), lambda: backend.engage(prepared={"action":"engage_once"}),
                  lambda: backend.set_globals({"power": 3}), lambda: backend.set_run_shots(True),
                  lambda: backend.set_labscript_file("x.py"), lambda: backend.set_shot_output_folder("somewhere"),
                  backend.rollback_last]
    for operation in operations:
        with pytest.raises(PermissionError, match="A2/A3"):
            operation()
    assert not gateway.actions


def test_gateway_can_preview_but_not_execute_outside_task_store(gateway):
    adapter = LocalRunmanager(gateway)
    prepared = adapter.prepare_globals({"power": 3.25, "scan": np.array([1, 5, 10])})
    assert prepared["plan"]["changes"] == {"power": "3.25", "scan": "np.array([1, 5, 10])"}
    with pytest.raises(PermissionError, match="A2/A3"):
        adapter.execute(prepared)
    engage = adapter.prepare("engage_once", expected_n_shots=4)
    with pytest.raises(PermissionError, match="A2/A3"):
        adapter.execute(engage)
    assert gateway.actions == ["read_all", "plan", "read_all"]
    assert not gateway.engage_calls


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
