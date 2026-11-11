"""Dispatch one persisted request and observe its effect without replaying it."""

from .store import ACTIVE, TERMINAL, _json


HOST_SCHEMA = "labpilot-host-result/1"
HOST_STATES = {"OBSERVED", "APPLIED", "REFUSED", "UNKNOWN"}
COUNTS = ("compiled_count", "queued_count", "executed_count", "analyzed_count")
OBSERVED_TERMINALS = ("COMPLETED", "FAILED", "CANCELLED")


def _unknown(request_id, reason):
    return {"schema": HOST_SCHEMA, "state": "UNKNOWN", "request_id": request_id, "reason": reason}


def _call(method, params):
    request_id = params["request_id"]
    try:
        reply = method(params)
        if (
            not isinstance(reply, dict)
            or reply.get("schema") != HOST_SCHEMA
            or reply.get("state") not in HOST_STATES
            or reply.get("request_id") != request_id
            or ("value" in reply and not isinstance(reply["value"], dict))
        ):
            return _unknown(request_id, "Host reply was invalid or lacked the matching request ID")
        _json(reply)
        return reply
    except Exception as exc:
        return _unknown(request_id, f"Host call failed ({type(exc).__name__}). Check the original request before continuing.")


class TaskService:
    """Run effects once after SQLite commits their intent. Recover by observing."""

    def __init__(self, store, host, *, analysis=None):
        self.store = store
        self.host = host
        self.analysis = analysis

    def run_next(self):
        with self.store._effect_lease() as available:
            return self._run_next() if available else None

    def _run_next(self):
        claim = self.store._claim()
        if claim is None:
            return None
        task, token, expires_at = claim
        current = self.store.get(task["task_id"])
        if current["cancel_requested"]:
            receipt = {"schema": HOST_SCHEMA, "state": "REFUSED", "request_id": task["request_id"],
                       "reason": "Cancelled before host dispatch"}
            return self.store._record_receipt(task["task_id"], token, "CANCELLED", receipt)
        if current["status"] in TERMINAL:
            return current
        request = {**task["params"], "action": task["action"], "request_id": task["request_id"],
                   "expected_snapshot_sha256": task["expected_config_digest"]}
        if task["kind"] == "batch":
            request["expected_n_shots"] = task["expected_shots"]
        if self.store._now() >= expires_at:
            receipt = {"schema": HOST_SCHEMA, "state": "REFUSED", "request_id": task["request_id"],
                       "reason": "Approval expired before host dispatch"}
            return self.store._record_receipt(task["task_id"], token, "FAILED", receipt)
        receipt = _call(self.host.execute, request)
        state = receipt["state"]
        if state == "APPLIED":
            status = "OBSERVING" if task["kind"] == "batch" else "COMPLETED"
        elif state == "REFUSED":
            status = "FAILED"
        else:
            status = "UNKNOWN"
        return self.store._record_receipt(task["task_id"], token, status, receipt)

    def observe(self, task_id):
        task = self.store.get(task_id)
        if task["status"] == "COMPLETED" and task["evidence"].get("analysis_state") == "COMPLETE":
            return task
        if task["status"] not in ACTIVE and not (task["kind"] == "batch" and task["status"] == "COMPLETED"):
            return task
        observation = _call(self.host.observe, {"target": task["params"]["target"], "request_id": task["request_id"]})
        status, evidence, problem = _observation_outcome(task, observation)
        if task["kind"] == "batch" and not problem and not evidence.get("simulated"):
            status, evidence, problem = self._analysis_outcome(task, observation, status, evidence)
        if problem:
            observation = {**observation, "reason": problem}
        return self.store._record_observation(task, status, observation, evidence)

    def _analysis_outcome(self, task, observation, status, evidence):
        if task["status"] in TERMINAL or status in ("FAILED", "CANCELLED"):
            return status, evidence, None
        if self.analysis is not None:
            evidence = {**evidence, "quality": "UNKNOWN"}
            if task["evidence"].get("manifest_sha256"):
                evidence["analyzed_count"] = task["evidence"].get("analyzed_count", 0)
            else:
                evidence.pop("analyzed_count", None)
        reported = observation.get("value", {}).get("evidence") if observation["state"] == "OBSERVED" else None
        if not isinstance(reported, dict) or reported.get("batch_execution_complete") is not True:
            if self.analysis is not None and status == "COMPLETED":
                evidence = {key: value for key, value in evidence.items() if key not in ("terminal", "quality")}
                return "OBSERVING", evidence, "Awaiting the verified physical batch and shot manifest"
            return status, evidence, None
        if any(evidence.get(field) != task["expected_shots"] for field in COUNTS[:3]):
            return "UNKNOWN", evidence, "Physical completion needs all compiled, queued, and executed shots"
        evidence = {**evidence, "batch_execution_complete": True}
        evidence.pop("terminal", None)
        evidence["quality"] = "UNKNOWN"
        if self.analysis is None:
            evidence["analysis_state"] = "NOT_CONFIGURED"
            return "OBSERVING", evidence, "Lyse analysis is not configured for this site profile"
        analysis = self.analysis.analyze(
            reported.get("shot_manifest"), request_id=task["request_id"],
            config_digest=task["expected_config_digest"], expected_n_shots=task["expected_shots"],
            prior_manifest_sha256=evidence.get("manifest_sha256"),
        )
        if analysis["analysis_state"] == "COMPLETE" and analysis["analyzed_count"] != task["expected_shots"]:
            return "FAILED", dict(evidence, terminal="FAILED", analysis_state="FAILED"), "Analysis did not cover all shots"
        # Retain verified partial results if a later read or analysis fails.
        if task["evidence"].get("manifest_sha256"):
            analysis["analyzed_count"] = max(analysis["analyzed_count"], task["evidence"].get("analyzed_count", 0))
        problem = analysis.pop("reason", None)
        evidence.update(analysis)
        if analysis["analysis_state"] == "COMPLETE":
            if analysis["quality"] == "PASS":
                return "COMPLETED", dict(evidence, terminal="COMPLETED"), None
            problem = "One or more shots failed the reviewed Lyse quality rules"
        elif analysis["analysis_state"] == "PENDING":
            return "OBSERVING", evidence, None
        return "FAILED", dict(evidence, terminal="FAILED"), problem or "Lyse analysis failed"


def _observation_outcome(task, observation):
    # An interrupted claim stays reserved even if the gateway has no evidence yet.
    original = task["status"]
    pending = "UNKNOWN" if original == "EXECUTING" else original
    evidence = task["evidence"]
    if observation["state"] != "OBSERVED":
        return pending, evidence, None
    value = observation.get("value", {})
    receipt = value.get("receipt")
    if isinstance(receipt, dict) and receipt.get("schema") == HOST_SCHEMA and receipt.get("request_id") == task["request_id"]:
        if receipt.get("state") == "REFUSED" and original != "COMPLETED":
            return "FAILED", evidence, None
        if receipt.get("state") == "APPLIED":
            pending = "OBSERVING" if task["kind"] == "batch" else "COMPLETED"
            if original == "COMPLETED":
                pending = original
    reported = value.get("evidence")
    if not reported:
        return pending, evidence, None
    if not isinstance(reported, dict) or reported.get("config_digest") != task["expected_config_digest"]:
        return _unverified(original), evidence, "Observed evidence lacks the expected configuration binding"
    try:
        merged = _merge_evidence(evidence, reported, task["expected_shots"])
    except ValueError as exc:
        return _unverified(original), evidence, str(exc)

    terminal = reported.get("terminal")
    if terminal == "COMPLETED" and task["kind"] == "batch" and any(
        merged.get(field) != task["expected_shots"] for field in COUNTS[:3]
    ):
        merged.pop("terminal", None)
        return _unverified(original), merged, "Batch completion needs compiled, queued, and executed counts"
    if original == "COMPLETED" and terminal in ("CANCELLED", "FAILED"):
        return original, evidence, "Observation conflicts with recorded completion"
    if terminal in OBSERVED_TERMINALS:
        return terminal, merged, None
    if original in ("EXECUTING", "UNKNOWN") and any(merged.get(field, 0) > 0 for field in COUNTS[:3]):
        return "OBSERVING", merged, None
    return pending, merged, None


def _unverified(status):
    return status if status in TERMINAL else "UNKNOWN"


def _merge_evidence(previous, reported, expected_shots):
    merged = dict(previous, config_digest=reported["config_digest"])
    for field in COUNTS:
        count = reported.get(field)
        if count is None:
            continue
        if type(count) is not int or not previous.get(field, 0) <= count <= expected_shots:
            raise ValueError(f"Invalid or regressing {field}")
        merged[field] = count
    known_counts = [merged[field] for field in COUNTS if field in merged]
    if any(left < right for left, right in zip(known_counts, known_counts[1:])):
        raise ValueError("Shot evidence counts are inconsistent")
    for field, allowed in {"quality": ("UNKNOWN", "PASS", "FAIL"), "terminal": OBSERVED_TERMINALS,
                           "simulated": (True, False)}.items():
        if field in reported and reported[field] is not None:
            if reported[field] not in allowed:
                raise ValueError(f"Invalid observation {field}")
            if field == "simulated" and (type(reported[field]) is not bool or
                                          field in previous and previous[field] is not reported[field]):
                raise ValueError("Observation simulation status changed")
            merged[field] = reported[field]
    return merged
