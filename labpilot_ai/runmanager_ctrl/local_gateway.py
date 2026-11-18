"""Same-machine client for the installed, source-bound Runmanager gateway."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import numpy as np


REQUEST_SCHEMA = "unified-runmanager-request/1"
SNAPSHOT_SCHEMA = "unified-runmanager/1"
PLAN_SCHEMA = "unified-runmanager-plan/1"
CONFIG_FIELDS = ("globals_raw", "sequence", "output", "run", "view", "shuffle")
CONFIG_ACTIONS = {"apply_globals", "set_sequence", "set_output", "set_flags"}
APPLIED = "APPLIED_READBACK_VERIFIED"
ENGAGE_ACK = "RPC_ACK_NOT_EXECUTION_PROOF"


class RunmanagerGatewayError(RuntimeError):
    """Keep the complete gateway receipt for reconciliation."""

    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def _digest(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _config(snapshot):
    return {key: snapshot[key] for key in CONFIG_FIELDS}


def _checked_snapshot(snapshot):
    try:
        valid = (
            snapshot["schema"] == SNAPSHOT_SCHEMA
            and snapshot["snapshot_consistent"] is True
            and isinstance(snapshot["globals_raw"], dict)
            and all(type(k) is str and type(v) is str for k, v in snapshot["globals_raw"].items())
            and all(type(snapshot[field]) is str for field in ("sequence", "output"))
            and all(type(snapshot[field]) is bool for field in ("run", "view", "shuffle"))
            and type(snapshot["error_in_globals"]) is bool
            and snapshot["config_digest"] == _digest(_config(snapshot))
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RunmanagerGatewayError("Runmanager snapshot unavailable, inconsistent or malformed", snapshot)
    return snapshot


def _literal_data(value, depth=0):
    if depth > 16:
        raise ValueError("Runmanager value nesting exceeds 16 levels")
    if isinstance(value, np.generic):
        return _literal_data(value.item(), depth + 1)
    if type(value) in (type(None), bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_literal_data(item, depth + 1) for item in value]
    if type(value) is tuple:
        return tuple(_literal_data(item, depth + 1) for item in value)
    raise ValueError("Runmanager writes accept finite literal values and arrays")


def raw_expression(value):
    """Format typed values as data for the native raw-globals API."""
    if isinstance(value, np.ndarray):
        return f"np.array({_literal_data(value.tolist())!r})"
    return repr(_literal_data(value))


def _check_raw_expression(text):
    if type(text) is not str or not text.strip():
        raise ValueError("A nonempty raw expression string is required")
    try:
        expression = ast.parse(text, mode="eval").body
        if isinstance(expression, ast.Call):
            method = expression.func
            if not (
                isinstance(method, ast.Attribute)
                and isinstance(method.value, ast.Name)
                and method.value.id == "np"
                and method.attr == "array"
                and len(expression.args) == 1
                and not expression.keywords
            ):
                raise ValueError("Unsupported Runmanager call")
            expression = expression.args[0]
        _literal_data(ast.literal_eval(expression))
    except (SyntaxError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError("Use a literal value or np.array(literal) in LabPilot plans") from exc


def evaluated_globals(snapshot):
    values = snapshot.get("globals_evaluated")
    if not isinstance(values, dict):
        raise RunmanagerGatewayError("Runmanager did not return evaluated globals", snapshot)
    return values


class LocalRunmanager:
    """Read state and preview changes using the legacy local gateway."""

    def __init__(self, gateway=None, port=None):
        self._gateway = gateway
        self.port = int(port if port is not None else os.environ.get("LABPILOT_RUNMANAGER_PORT", "42523"))
        if not 1 <= self.port <= 65535:
            raise ValueError("Invalid Runmanager port")

    @property
    def gateway(self):
        if self._gateway is None:
            from labpilot_ai.local_control.transport import LocalGateway

            self._gateway = LocalGateway.from_env()
        return self._gateway

    @property
    def endpoint(self):
        return {"host": "localhost", "port": self.port}

    def _call(self, action, **fields):
        return self.gateway.call("runmanager", {"schema": REQUEST_SCHEMA, "action": action, **fields})

    def read_all(self):
        return _checked_snapshot(self._call("read_all"))

    def prepare_globals(self, values, *, snapshot=None):
        if not isinstance(values, dict) or any(type(name) is not str for name in values):
            raise ValueError("Runmanager globals must be an object with string names")
        return self.prepare(
            "apply_globals", {name: raw_expression(value) for name, value in values.items()}, snapshot=snapshot
        )

    def prepare_engage(self, expected_n_shots, *, snapshot=None):
        return self.prepare("engage_once", snapshot=snapshot, expected_n_shots=expected_n_shots)

    def prepare(self, operation, changes=None, *, snapshot=None, expected_n_shots=None):
        return self._prepare(operation, changes, snapshot=snapshot, expected_n_shots=expected_n_shots)

    def _prepare(self, operation, changes=None, *, snapshot=None, expected_n_shots=None, restore=False):
        if operation not in CONFIG_ACTIONS | {"engage_once"}:
            raise ValueError(f"Unsupported Runmanager operation: {operation}")
        snapshot = self.read_all() if snapshot is None else _checked_snapshot(snapshot)
        request = {
            "schema": REQUEST_SCHEMA,
            "action": operation,
            "execute": True,
            "request_id": uuid4().hex,
            "expected_endpoint": self.endpoint,
        }
        if operation == "engage_once":
            if changes is not None:
                raise ValueError("Prepare configuration changes separately from Engage")
            if type(expected_n_shots) is not int or expected_n_shots <= 0:
                raise ValueError("Engage requires a positive explicit shot count")
            if expected_n_shots != snapshot["n_shots"] or snapshot["error_in_globals"]:
                raise ValueError("The requested shot count does not match valid Runmanager globals")
            if snapshot["run"] is not True:
                raise ValueError("Enable Run shots in Runmanager, then review the Engage request again")
            request.update(expected_config_digest=snapshot["config_digest"], expected_n_shots=expected_n_shots)
        else:
            if not isinstance(changes, dict) or not changes or any(type(key) is not str for key in changes):
                raise ValueError("A nonempty changes mapping is required")
            if operation == "apply_globals":
                missing = changes.keys() - snapshot["globals_raw"].keys()
                if missing:
                    raise ValueError("Unknown or inactive Runmanager globals: " + ", ".join(sorted(missing)))
                if not restore:
                    for expression in changes.values():
                        _check_raw_expression(expression)
            plan = self._call("plan", baseline=snapshot, operation=operation, changes=changes)
            if not isinstance(plan, dict) or not (
                plan.get("schema") == PLAN_SCHEMA
                and plan.get("operation") == operation
                and plan.get("baseline_digest") == snapshot["config_digest"]
                and plan.get("baseline") == _config(snapshot)
                and plan.get("changes") == changes
                and plan.get("plan_digest") == _digest({k: v for k, v in plan.items() if k != "plan_digest"})
            ):
                raise RunmanagerGatewayError("Runmanager gateway did not return a matching plan", plan)
            request["plan"] = plan
        request["expires_at_utc"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        return request

    def execute(self, request):
        raise PermissionError("Legacy Runmanager plans cannot execute; use a managed labpilot A2/A3 task")
