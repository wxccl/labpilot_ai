"""Local, provider-independent LabPilot automation entry point."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .local_control.transport import load_json

ACTION_NAMES = {
    "runmanager": {"set_globals", "set_sequence", "set_output", "set_flags", "engage"},
    "blacs": {"set_manual"},
}


class HostClient:
    def __init__(self, profile, python, simulate, profile_sha256, timeout=30):
        self.profile = profile
        self.python = python
        self.simulate = simulate
        self.profile_sha256 = profile_sha256
        self.timeout = timeout

    def call(self, method, params):
        return self._invoke([], {"method": method, "params": params}, params.get("request_id"), method == "execute")

    def configuration(self, action, labconfig=None, apply=False):
        command = [action]
        if labconfig:
            command.extend(["--labconfig", str(labconfig)])
        if apply:
            command.append("--apply")
        return self._invoke(command, None)

    def _invoke(self, arguments, envelope, request_id=None, effect=False):
        from . import host

        # Running the packaged script by its absolute path works in an existing
        # Labscript Python without installing LabPilot's desktop dependencies.
        script = Path(host.__file__).with_name("__main__.py").resolve()
        command = [str(self.python), "-X", "utf8", str(script), "--profile", str(self.profile),
                   "--expect-profile-sha256", self.profile_sha256]
        if self.simulate:
            command.append("--simulate")
        command.extend(arguments)
        try:
            process = subprocess.run(
                command, input=json.dumps(envelope, allow_nan=False) if envelope is not None else "",
                encoding="utf-8", errors="replace", capture_output=True,
                timeout=self.timeout, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            prefix = "LABPILOT_HOST_JSON:"
            replies = [line[len(prefix):] for line in process.stdout.splitlines() if line.startswith(prefix)]
            if process.returncode not in {0, 2} or len(replies) != 1 or len(replies[0]) > 4 * 1024 * 1024:
                raise RuntimeError(f"Host process returned {process.returncode} with {len(replies)} result frames")
            reply = load_json(replies[0])
            if not isinstance(reply, dict) or reply.get("schema") != "labpilot-host-result/1":
                raise ValueError("Host reply does not match the supported protocol")
            if effect and reply.get("request_id") != request_id:
                raise ValueError("Host reply does not identify the submitted request")
            return reply
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            return {"schema": "labpilot-host-result/1", "state": "UNKNOWN",
                    "reason": str(exc), "request_id": request_id}

    def execute(self, params):
        return self.call("execute", params)

    def observe(self, params):
        return self.call("observe", params)


def path_setting(profile, value):
    path = Path(value).expanduser()
    return (profile.parent / path).resolve()


class Automation:
    def __init__(self, profile):
        from .tasks import TaskService, TaskStore

        self.profile = Path(profile).expanduser().resolve(strict=True)
        with self.profile.open("rb") as stream:
            source = stream.read(1024 * 1024 + 1)
        if len(source) > 1024 * 1024:
            raise ValueError("Profile exceeds 1 MiB")
        config = load_json(source.decode("utf-8-sig"))
        if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
            raise ValueError("Expected a JSON profile with schema_version 1")
        if type(config.get("simulate", False)) is not bool:
            raise ValueError("simulate must be a boolean")
        simulate = config.get("simulate", False)
        if not simulate and not config.get("python"):
            raise ValueError("Set python to the existing Labscript interpreter")
        python = path_setting(self.profile, config.get("python", sys.executable))
        if not python.is_file():
            raise ValueError(f"Labscript interpreter does not exist: {python}")
        self.simulate = simulate
        self.host = HostClient(self.profile, python, simulate, hashlib.sha256(source).hexdigest())
        mode = "simulation" if simulate else "live"
        db = path_setting(self.profile, config.get("state_db", self.profile.stem + ".tasks.sqlite3"))
        # A changed host profile must not execute plans approved for another configuration.
        binding = hashlib.sha256(
            json.dumps({"mode": mode, "python": str(python), "host": config.get("host", {})},
                       sort_keys=True, ensure_ascii=True, allow_nan=False).encode("ascii")
        ).hexdigest()
        db = db.with_name(f"{db.stem}.{mode}.{binding[:16]}{db.suffix}")
        self.store = TaskStore(db)
        self.service = TaskService(self.store, self.host)
        root = config.get("project_root")
        self.project_root = path_setting(self.profile, root) if root else None

    def dispatch(self, operation, args):
        if operation == "status":
            return self.store.get(args["task_id"])
        if operation in {"discover", "snapshot"}:
            return self.host.call(operation, args)
        if operation != "prepare":
            raise ValueError(f"Unknown operation: {operation}")
        target = args["target"]
        action = args["action"]
        if not isinstance(target, str) or not isinstance(action, str) or action not in ACTION_NAMES.get(target, ()):
            raise ValueError("Unsupported host target or action")
        if set(args) - {"target", "action", "values", "device", "expected_n_shots", "policy_id"}:
            raise ValueError("Unexpected field in task preparation")
        params = {"target": target}
        if "device" in args:
            params["device"] = args["device"]
        observed = self.host.call("snapshot", params)
        snapshot = observed.get("value")
        if observed["state"] != "OBSERVED" or not isinstance(snapshot, dict) or not snapshot.get("snapshot_sha256"):
            raise RuntimeError(observed.get("reason") or "Host snapshot unavailable")
        shots = args.get("expected_n_shots", 0)
        batch = target == "runmanager" and action == "engage"
        if batch and (type(shots) is not int or shots < 1 or shots != snapshot.get("n_shots")):
            raise ValueError("Engage requires an explicit positive shot count matching the live snapshot")
        if not batch and shots != 0:
            raise ValueError("expected_n_shots is only valid for Engage")
        values = args.get("values", {})
        if not isinstance(values, dict) or (batch and values):
            raise ValueError("values must be an object, and Engage takes no configuration changes")
        return self.store.submit({
            "kind": "batch" if batch else "short", "action": action, "request_id": uuid.uuid4().hex,
            "params": {**params, "values": values}, "expected_config_digest": snapshot["snapshot_sha256"],
            "expected_shots": shots, **({"policy_id": args["policy_id"]} if args.get("policy_id") else {}),
        })


def default_profile():
    return os.environ.get("LABPILOT_PROFILE", "labpilot.json")
