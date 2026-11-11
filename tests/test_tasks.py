from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest

from labpilot_ai.tasks import TaskService, TaskStore, plan_digest, policy_scope_digest


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = NOW + timedelta(minutes=5)
CONFIG = "a" * 64


def specification(*, batch=False, **overrides):
    spec = {"kind": "batch" if batch else "short", "action": "engage" if batch else "set_manual",
            "request_id": uuid4().hex, "expected_config_digest": CONFIG, "expected_shots": 4 if batch else 0,
            "params": {"target": "runmanager"} if batch else {"target": "blacs", "value": 1.0}}
    return {**spec, **overrides}


def response(request, state, **fields):
    return {"schema": "labpilot-host-result/1", "request_id": request["request_id"], "state": state, **fields}


class Host:
    def __init__(self):
        self.executions = []
        self.observations = []
        self.state = "APPLIED"
        self.evidence = {}

    def execute(self, params):
        self.executions.append(params)
        return response(params, self.state)

    def observe(self, params):
        self.observations.append(params)
        return response(params, "OBSERVED", value={"evidence": {"config_digest": CONFIG, **self.evidence}})


def approve(store, spec):
    task = store.submit(spec)
    return store.approve(task["task_id"], task["plan_digest"], "owner", END)


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.sqlite3", clock=lambda: NOW)


def test_a2_freezes_reviewed_plan_and_dispatches_exact_bindings(store):
    host = Host()
    service = TaskService(store, host)
    spec = specification()
    task = store.submit(spec)
    spec["params"]["value"] = 99
    assert task["status"] == "PENDING_APPROVAL"
    assert service.run_next() is None
    with pytest.raises(ValueError, match="frozen plan"):
        store.approve(task["task_id"], plan_digest(spec), "owner", END)
    with pytest.raises(ValueError, match="different task"):
        store.submit(spec)
    store.approve(task["task_id"], task["plan_digest"], "owner", END)
    assert service.run_next()["status"] == "COMPLETED"
    assert service.run_next() is None
    assert host.executions == [{"target": "blacs", "value": 1.0, "action": "set_manual",
                                "request_id": task["request_id"], "expected_snapshot_sha256": CONFIG}]
    assert [event["kind"] for event in store.events(task["task_id"])] == [
        "SUBMITTED", "APPROVED", "EFFECT_INTENT", "EFFECT_RECEIPT"
    ]


def test_expired_a2_is_not_dispatched(tmp_path):
    clock = [NOW]
    store = TaskStore(tmp_path / "tasks.sqlite3", clock=lambda: clock[0])
    host = Host()
    task = approve(store, specification())
    clock[0] = END
    assert TaskService(store, host).run_next() is None
    assert store.get(task["task_id"])["status"] == "PENDING_APPROVAL"
    assert not host.executions


def test_expiry_between_claim_and_dispatch_stops_effect(tmp_path, monkeypatch):
    clock = [NOW]
    store = TaskStore(tmp_path / "tasks.sqlite3", clock=lambda: clock[0])
    approve(store, specification())
    host = Host()
    claim = store._claim

    def claim_at_expiry():
        result = claim()
        clock[0] = END
        return result

    monkeypatch.setattr(store, "_claim", claim_at_expiry)
    result = TaskService(store, host).run_next()
    assert result["status"] == "FAILED"
    assert result["receipt"]["reason"] == "Approval expired before host dispatch"
    assert not host.executions


def test_competing_runners_share_one_effect_claim(store):
    started = Event()
    finish = Event()

    class WaitingHost(Host):
        def execute(self, params):
            started.set()
            assert finish.wait(10)
            return super().execute(params)

    host = WaitingHost()
    other = TaskStore(store.path, clock=lambda: NOW)
    first = approve(store, specification())
    second = approve(other, specification())
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(TaskService(store, host).run_next)
        try:
            assert started.wait(10)
            assert TaskService(other, host).run_next() is None
            assert store.get(first["task_id"])["status"] == "EXECUTING"
            assert store.get(second["task_id"])["status"] == "READY"
            assert TaskService(other, host).observe(first["task_id"])["status"] == "UNKNOWN"
            with pytest.raises(RuntimeError, match="dispatch is active"):
                other.close_unresolved(first["task_id"], "operator", "External session ended")
        finally:
            finish.set()
        assert pending.result(10)["status"] == "COMPLETED"
    assert len(host.executions) == 1
    assert TaskService(other, host).run_next()["task_id"] == second["task_id"]


def test_crash_after_effect_before_ack_only_observes_on_restart(store):
    class Crash(BaseException):
        pass

    class LostAck(Host):
        def execute(self, params):
            super().execute(params)
            raise Crash

    host = LostAck()
    spec = specification(batch=True)
    task = approve(store, spec)
    with pytest.raises(Crash):
        TaskService(store, host).run_next()
    reopened = TaskStore(store.path, clock=lambda: NOW)
    recovered = TaskService(reopened, host)
    assert reopened.submit(spec)["status"] == "EXECUTING"
    assert recovered.run_next() is None
    assert recovered.observe(task["task_id"])["status"] == "UNKNOWN"
    host.evidence = {"compiled_count": 2, "queued_count": 1}
    assert recovered.observe(task["task_id"])["status"] == "OBSERVING"
    assert len(host.executions) == 1
    assert host.executions[0]["expected_n_shots"] == 4
    assert host.observations == [{"target": "runmanager", "request_id": task["request_id"]}] * 2


def test_batch_ack_and_files_do_not_establish_completion(store):
    host = Host()
    task = approve(store, specification(batch=True))
    service = TaskService(store, host)
    assert service.run_next()["status"] == "OBSERVING"
    host.evidence = {"file_count": 4, "terminal": "COMPLETED"}
    assert service.observe(task["task_id"])["status"] == "UNKNOWN"
    host.evidence = {"compiled_count": 4, "queued_count": 4, "executed_count": 2, "analyzed_count": 1}
    current = service.observe(task["task_id"])
    assert current["status"] == "OBSERVING"
    assert current["evidence"]["executed_count"] == 2
    host.evidence = {"config_digest": "b" * 64, "executed_count": 4, "terminal": "COMPLETED"}
    current = service.observe(task["task_id"])
    assert current["status"] == "UNKNOWN"
    assert current["evidence"]["executed_count"] == 2
    host.evidence = {"executed_count": 4, "terminal": "COMPLETED", "quality": "UNKNOWN"}
    assert service.observe(task["task_id"])["status"] == "COMPLETED"
    host.evidence = {"analyzed_count": 4, "quality": "PASS"}
    assert service.observe(task["task_id"])["evidence"]["quality"] == "PASS"
    host.evidence = {"analyzed_count": 3}
    assert service.observe(task["task_id"])["evidence"]["analyzed_count"] == 4
    assert len(host.executions) == 1


def test_cancel_only_prevents_unsubmitted_effects_and_keeps_partial_evidence(store):
    host = Host()
    cancelled = approve(store, specification())
    assert store.cancel(cancelled["task_id"])["status"] == "CANCELLED"
    task = approve(store, specification(batch=True))
    service = TaskService(store, host)
    assert service.run_next()["task_id"] == task["task_id"]
    observed = store.cancel(task["task_id"])
    assert observed["status"] == "OBSERVING"
    assert observed["cancel_requested"] is True
    assert service.run_next() is None
    host.evidence = {"compiled_count": 4, "queued_count": 3, "executed_count": 1, "terminal": "CANCELLED"}
    observed = service.observe(task["task_id"])
    assert observed["status"] == "CANCELLED"
    assert observed["evidence"]["executed_count"] == 1
    assert len(host.executions) == 1


def test_active_list_and_identical_observation_do_not_append_events(store):
    host = Host()
    service = TaskService(store, host)
    task = approve(store, specification(batch=True))
    approve(store, specification())
    assert store.list_active() == []
    assert service.run_next()["status"] == "OBSERVING"
    assert [row["task_id"] for row in store.list_active()] == [task["task_id"]]
    host.evidence = {"compiled_count": 1}
    service.observe(task["task_id"])
    events = store.events(task["task_id"])
    service.observe(task["task_id"])
    assert store.events(task["task_id"]) == events


def test_a3_allows_fresh_request_ids_in_exact_scope_and_atomically_debits_before_effect(store):
    first = specification(batch=True)
    second = {**first, "request_id": uuid4().hex}
    assert plan_digest(first) != plan_digest(second)
    assert policy_scope_digest(first) == policy_scope_digest(second)
    store.create_policy({"policy_id": "series", "approver": "owner", "expires_at": END,
                         "scope_digests": [policy_scope_digest(first)], "max_actions": 3, "max_shots": 5})
    task1 = store.submit({**first, "policy_id": "series"})
    task2 = store.submit(second)
    assert store.authorize_policy(task2["task_id"], "series")["status"] == "READY"
    outside = {**second, "request_id": uuid4().hex, "expected_config_digest": "b" * 64}
    with pytest.raises(ValueError, match="scope"):
        store.submit({**outside, "policy_id": "series"})

    class Uncertain(Host):
        def execute(self, params):
            assert store.get_policy("series")["used_actions"] == 1
            assert store.get_policy("series")["used_shots"] == 4
            self.executions.append(params)
            raise TimeoutError

    host = Uncertain()
    service = TaskService(store, host)
    assert service.run_next()["status"] == "UNKNOWN"
    assert service.run_next() is None
    assert store.get(task2["task_id"])["status"] == "READY"
    host.evidence = {"terminal": "FAILED", "compiled_count": 1}
    assert service.observe(task1["task_id"])["status"] == "FAILED"
    assert service.run_next() is None
    assert store.get(task2["task_id"])["status"] == "PENDING_APPROVAL"
    assert store.get_policy("series")["used_shots"] == 4


def test_unbound_receipt_does_not_resolve_effect(store):
    class Unbound(Host):
        def execute(self, params):
            return {"schema": "labpilot-host-result/1", "state": "APPLIED"}

    task = approve(store, specification())
    service = TaskService(store, Unbound())
    assert service.run_next()["status"] == "UNKNOWN"
    assert service.run_next() is None
    assert store.get(task["task_id"])["receipt"]["state"] == "UNKNOWN"


@pytest.mark.parametrize("state,kind,expected", [
    ("APPLIED", "short", "COMPLETED"), ("APPLIED", "batch", "OBSERVING"), ("REFUSED", "batch", "FAILED")
])
def test_recovery_consumes_host_journal_without_replaying_lost_client_result(store, state, kind, expected):
    class LostClientResult(Host):
        def execute(self, params):
            self.executions.append(params)
            raise TimeoutError

        def observe(self, params):
            return response(params, "OBSERVED", value={"receipt": response(params, state), "evidence": {}})

    task = approve(store, specification(batch=kind == "batch"))
    host = LostClientResult()
    service = TaskService(store, host)
    assert service.run_next()["status"] == "UNKNOWN"
    assert service.observe(task["task_id"])["status"] == expected
    assert service.run_next() is None
    assert len(host.executions) == 1


def test_operator_closes_unverified_after_external_run_stops_and_keeps_evidence(store):
    host = Host()
    service = TaskService(store, host)
    batch = approve(store, specification(batch=True))
    waiting = approve(store, specification())
    assert service.run_next()["status"] == "OBSERVING"
    host.evidence = {"compiled_count": 2, "queued_count": 2}
    observed = service.observe(batch["task_id"])
    with pytest.raises(ValueError, match="nonempty"):
        store.close_unresolved(batch["task_id"], "operator", "")
    closed = store.close_unresolved(batch["task_id"], "operator", "Queue ended; execution logs unavailable")
    assert closed["status"] == "UNVERIFIED"
    assert closed["evidence"] == observed["evidence"]
    assert store.events(batch["task_id"])[-1]["detail"] == {
        "operator": "operator", "reason": "Queue ended; execution logs unavailable"
    }
    assert service.run_next()["task_id"] == waiting["task_id"]
    assert store.submit({name: batch[name] for name in (
        "kind", "action", "request_id", "params", "expected_config_digest", "expected_shots"
    )})["status"] == "UNVERIFIED"
    assert len(host.executions) == 2


def test_policy_window_and_revocation_check_at_claim(store):
    first = specification()
    store.create_policy({"policy_id": "later", "approver": "owner", "starts_at": NOW + timedelta(minutes=1),
                         "expires_at": END, "scope_digests": [policy_scope_digest(first)],
                         "max_actions": 1, "max_shots": 0})
    task = store.submit({**first, "policy_id": "later"})
    host = Host()
    service = TaskService(store, host)
    assert service.run_next() is None
    assert store.get(task["task_id"])["status"] == "READY"
    store.revoke_policy("later")
    assert service.run_next() is None
    assert store.get(task["task_id"])["status"] == "PENDING_APPROVAL"
    assert store.get_policy("later")["used_actions"] == 0
